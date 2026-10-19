/* Firefox WebExtension manual handoff. Uses Firefox's Promise-based browser APIs. */
const MENU_LINK = "mediagrab-send-link";
const MENU_PAGE = "mediagrab-send-page";
const HOST_NAME = "io.github.SakibShahariar.MediaGrab";

async function createMenus() {
  await browser.contextMenus.removeAll();
  browser.contextMenus.create({ id: MENU_LINK, title: "Send link to MediaGrab", contexts: ["link"] });
  browser.contextMenus.create({ id: MENU_PAGE, title: "Send page to MediaGrab", contexts: ["page"] });
}

async function sendUrl(url) {
  if (typeof url !== "string" || !/^https?:\/\//i.test(url)) {
    throw new Error("Only HTTP(S) links can be sent to MediaGrab.");
  }
  const response = await browser.runtime.sendNativeMessage(HOST_NAME, {
    version: 1,
    type: "add-url",
    url
  });
  if (!response || response.ok !== true) {
    throw new Error((response && response.error) || "MediaGrab did not accept the link.");
  }
}

browser.runtime.onInstalled.addListener(() => {
  createMenus().catch((error) => console.error("MediaGrab menu setup failed:", error.message));
});
browser.runtime.onStartup.addListener(() => {
  createMenus().catch((error) => console.error("MediaGrab menu setup failed:", error.message));
});
browser.contextMenus.onClicked.addListener((info) => {
  const url = info.menuItemId === MENU_LINK ? info.linkUrl : info.pageUrl;
  sendUrl(url).catch((error) => {
    // Never log the URL: signed media links may contain private tokens.
    console.error("MediaGrab handoff failed:", error.message);
  });
});
