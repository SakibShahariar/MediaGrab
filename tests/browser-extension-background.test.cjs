const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");
const STORAGE_KEY = "mediagrabDetectedCandidates";

function makeEvent() {
  const listeners = [];
  return {
    listeners,
    addListener(listener) { listeners.push(listener); },
    fire(...args) { return listeners.map((listener) => listener(...args)); }
  };
}

function loadBackground(browserName) {
  const session = {};
  const menus = [];
  const sentMessages = [];
  const errors = [];
  const webRequestEvent = makeEvent();
  const tabsUpdated = makeEvent();
  const tabsRemoved = makeEvent();
  const permissionRemoved = makeEvent();
  const installed = makeEvent();
  const startup = makeEvent();
  const menuClicked = makeEvent();
  let webRequestRegistration = null;

  const api = {
    storage: {session: {
      async get(key) { return {[key]: session[key]}; },
      async set(values) { Object.assign(session, values); },
      async remove(key) { delete session[key]; }
    }},
    webRequest: {onHeadersReceived: {
      addListener(listener, filter, extraInfoSpec) {
        webRequestRegistration = {listener, filter, extraInfoSpec};
        webRequestEvent.addListener(listener);
      }
    }},
    tabs: {onUpdated: tabsUpdated, onRemoved: tabsRemoved},
    permissions: {onRemoved: permissionRemoved},
    runtime: {
      onInstalled: installed,
      onStartup: startup,
      lastError: null,
      sendNativeMessage(host, message, callback) {
        sentMessages.push({host, message});
        const response = {version: 1, ok: true};
        if (typeof callback === "function") { callback(response); return undefined; }
        return Promise.resolve(response);
      }
    },
    contextMenus: {
      onClicked: menuClicked,
      create(properties) { menus.push(properties); return menus.length; },
      removeAll(callback) {
        menus.length = 0;
        if (typeof callback === "function") { callback(); return undefined; }
        return Promise.resolve();
      }
    }
  };

  const context = {
    URL, Date, Promise, Number, Array, Object, String, RegExp, Math,
    setTimeout, clearTimeout,
    console: {error: (...args) => errors.push(args)}
  };
  if (browserName === "firefox") context.browser = api;
  else context.chrome = api;

  const file = path.join(ROOT, "browser-extension", browserName, "background.js");
  vm.runInNewContext(fs.readFileSync(file, "utf8"), context, {filename: file});
  return {
    session, menus, sentMessages, errors, webRequestRegistration,
    tabsUpdated, tabsRemoved, permissionRemoved, installed, startup, menuClicked
  };
}

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await Promise.resolve();
}

for (const browserName of ["firefox", "chromium"]) {
  test(browserName + ": observes and deduplicates media responses per tab", async () => {
    const h = loadBackground(browserName);
    assert.ok(h.webRequestRegistration);
    assert.deepEqual(Array.from(h.webRequestRegistration.filter.types), ["media", "xmlhttprequest", "other"]);
    assert.deepEqual(Array.from(h.webRequestRegistration.extraInfoSpec), ["responseHeaders"]);

    const observe = h.webRequestRegistration.listener;
    const hls = {
      url: "https://cdn.example.test/master.m3u8?sig=secret",
      tabId: 7,
      type: "xmlhttprequest",
      statusCode: 200,
      responseHeaders: [{name: "Content-Type", value: "application/vnd.apple.mpegurl; charset=utf-8"}],
      requestHeaders: [{name: "Authorization", value: "must-not-be-copied"}]
    };
    observe(hls);
    observe(hls);
    observe({
      url: "https://cdn.example.test/manifest",
      tabId: 7,
      type: "xmlhttprequest",
      statusCode: 200,
      responseHeaders: [{name: "Content-Type", value: "application/dash+xml"}]
    });
    observe({...hls, tabId: 8});
    observe({...hls, url: "https://cdn.example.test/redirect.m3u8", statusCode: 302});
    observe({...hls, url: "https://user:pass@cdn.example.test/private.mp4"});
    observe({...hls, url: "https://cdn.example.test/image.png", responseHeaders: [{name: "Content-Type", value: "image/png"}]});
    observe({...hls, url: "https://cdn.example.test/private-window.mp4", incognito: true});
    await settle();

    const candidates = h.session[STORAGE_KEY];
    assert.equal(candidates.length, 3);
    assert.equal(candidates.filter((item) => item.tabId === 7 && item.url === hls.url).length, 1);
    assert.ok(candidates.some((item) => item.kind === "DASH manifest"));
    assert.ok(candidates.some((item) => item.tabId === 8 && item.url === hls.url));
    assert.ok(candidates.every((item) => !("requestHeaders" in item)));

    h.tabsUpdated.fire(7, {status: "loading"}, {});
    await settle();
    assert.equal(h.session[STORAGE_KEY].length, 1);
    assert.equal(h.session[STORAGE_KEY][0].tabId, 8);
    h.tabsRemoved.fire(8);
    await settle();
    assert.equal(h.session[STORAGE_KEY].length, 0);

    observe(hls);
    await settle();
    h.permissionRemoved.fire({origins: ["*://*/*"]});
    await settle();
    assert.equal(h.session[STORAGE_KEY].length, 0);
  });

  test(browserName + ": preserves explicit context-menu native handoff", async () => {
    const h = loadBackground(browserName);
    h.installed.fire();
    await settle();
    assert.equal(h.menus.length, 2);
    assert.ok(h.menus.some((item) => item.id === "mediagrab-send-link"));
    assert.ok(h.menus.some((item) => item.id === "mediagrab-send-page"));
    h.menuClicked.fire({
      menuItemId: "mediagrab-send-link",
      linkUrl: "https://media.example.test/file.mp4?sig=private",
      pageUrl: "https://page.example.test/"
    });
    await settle();
    h.menuClicked.fire({
      menuItemId: "mediagrab-send-link",
      linkUrl: "https://media.example.test/private.mp4",
      pageUrl: "https://page.example.test/"
    }, {incognito: true});
    await settle();
    assert.equal(h.sentMessages.length, 1, "private-window context menus must not hand off URLs");
    assert.equal(h.sentMessages[0].host, "io.github.SakibShahariar.MediaGrab");
    assert.equal(h.sentMessages[0].message.type, "add-url");
    assert.equal(h.sentMessages[0].message.url, "https://media.example.test/file.mp4?sig=private");
  });
}
