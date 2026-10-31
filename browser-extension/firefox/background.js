/* Opt-in, non-blocking media response observation for the active browser session. */
const api = browser;
const HOST_NAME = "io.github.SakibShahariar.MediaGrab";
const MENU_LINK = "mediagrab-send-link";
const MENU_PAGE = "mediagrab-send-page";

function removeMenus() {
  return browser.contextMenus.removeAll();
}

async function createMenus() {
  await removeMenus();
  api.contextMenus.create({id: MENU_LINK, title: "Send link to MediaGrab", contexts: ["link"]});
  api.contextMenus.create({id: MENU_PAGE, title: "Send page to MediaGrab", contexts: ["page"]});
}

function sendUrl(url) {
  let parsed;
  try { parsed = new URL(url); } catch {
    return Promise.reject(new Error("Only HTTP(S) links can be sent to MediaGrab."));
  }
  if (
    (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
    parsed.username ||
    parsed.password
  ) {
    return Promise.reject(new Error("Only credential-free HTTP(S) links can be sent to MediaGrab."));
  }
  return browser.runtime.sendNativeMessage(HOST_NAME, {
    version: 1,
    type: "add-url",
    url
  }).then((response) => {
    if (!response || response.ok !== true) {
      throw new Error((response && response.error) || "MediaGrab did not accept the link.");
    }
    return response;
  });
}

const STORAGE_KEY = "mediagrabDetectedCandidates";
const MAX_CANDIDATES = 100;
const CANDIDATE_TTL_MS = 30 * 60 * 1000;
const OPTIONAL_ORIGIN = "*://*/*";
let writeQueue = Promise.resolve();

function responseContentType(details) {
  const header = (details.responseHeaders || []).find(
    (item) => item && typeof item.name === "string" && item.name.toLowerCase() === "content-type"
  );
  return header && typeof header.value === "string"
    ? header.value.split(";", 1)[0].trim().toLowerCase()
    : "";
}

function classifyResponse(details) {
  let parsed;
  try { parsed = new URL(details.url); } catch { return null; }
  if (!/^https?:$/.test(parsed.protocol) || parsed.username || parsed.password) return null;
  const path = parsed.pathname.toLowerCase();
  const mime = responseContentType(details);
  if (path.endsWith(".m3u8") || /mpegurl/.test(mime)) return "HLS playlist";
  if (path.endsWith(".mpd") || mime.includes("dash+xml")) return "DASH manifest";
  if (/\.(vtt|srt|ass|ssa|ttml|dfxp)$/.test(path) || mime.includes("text/vtt")) return "Subtitle resource";
  if (/\.(mp4|m4v|mkv|webm|mov|ogv|avi|mpeg|mpg)$/.test(path) || mime.startsWith("video/")) return "Video resource";
  if (/\.(mp3|m4a|aac|ogg|opus|wav|flac|weba)$/.test(path) || mime.startsWith("audio/")) return "Audio resource";
  if (/\.(ts|m4s|cmfv|cmfa|mp4v)$/.test(path)) return "Media segment";
  if (details.type === "media") return "Media response";
  return null;
}

function mutateCandidates(mutator) {
  writeQueue = writeQueue.then(async () => {
    const stored = await api.storage.session.get(STORAGE_KEY);
    const current = Array.isArray(stored[STORAGE_KEY]) ? stored[STORAGE_KEY] : [];
    const now = Date.now();
    const fresh = current.filter((item) =>
      item && typeof item.url === "string" && Number.isInteger(item.tabId) &&
      Number.isFinite(item.lastSeenAt) && now - item.lastSeenAt >= 0 &&
      now - item.lastSeenAt < CANDIDATE_TTL_MS
    );
    const next = mutator(fresh, now).sort((a, b) => a.lastSeenAt - b.lastSeenAt);
    await api.storage.session.set({[STORAGE_KEY]: next.slice(-MAX_CANDIDATES)});
  }).catch((error) => {
    console.error("MediaGrab candidate storage failed:", error.message);
  });
  return writeQueue;
}

function rememberCandidate(details) {
  if (!details || !Number.isInteger(details.tabId) || details.tabId < 0) return;
  if (typeof details.url !== "string") return;
  if (Number.isInteger(details.statusCode) && (details.statusCode < 200 || details.statusCode >= 300)) return;
  const kind = classifyResponse(details);
  if (!kind) return;
  return mutateCandidates((current, now) => {
    const existing = current.find((item) => item.tabId === details.tabId && item.url === details.url);
    if (existing) {
      existing.kind = kind;
      existing.lastSeenAt = now;
      return current;
    }
    current.push({url: details.url, kind, tabId: details.tabId, firstSeenAt: now, lastSeenAt: now});
    return current;
  });
}

function removeTabCandidates(tabId) {
  return mutateCandidates((current) => current.filter((item) => item.tabId !== tabId));
}

function clearCandidates() {
  return mutateCandidates(() => []);
}

api.webRequest.onHeadersReceived.addListener(
  (details) => { rememberCandidate(details); },
  {urls: [OPTIONAL_ORIGIN], types: ["media", "xmlhttprequest", "other"]},
  ["responseHeaders"]
);
api.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading") removeTabCandidates(tabId);
});
api.tabs.onRemoved.addListener((tabId) => removeTabCandidates(tabId));
api.permissions.onRemoved.addListener((removed) => {
  if (Array.isArray(removed.origins) && removed.origins.includes(OPTIONAL_ORIGIN)) clearCandidates();
});

api.runtime.onInstalled.addListener(() => {
  createMenus().catch((error) => console.error("MediaGrab menu setup failed:", error.message));
});
api.runtime.onStartup.addListener(() => {
  createMenus().catch((error) => console.error("MediaGrab menu setup failed:", error.message));
});
api.contextMenus.onClicked.addListener((info) => {
  const url = info.menuItemId === MENU_LINK ? info.linkUrl : info.pageUrl;
  sendUrl(url).catch((error) => {
    // Never log the URL: signed media links may contain private tokens.
    console.error("MediaGrab handoff failed:", error.message);
  });
});
