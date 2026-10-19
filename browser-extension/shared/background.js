/* Shared manual handoff for Firefox and Chromium-family browsers. */
const api = typeof browser !== "undefined" ? browser : chrome;
const MENU_LINK = "mediagrab-send-link";
const MENU_PAGE = "mediagrab-send-page";

function createMenus() {
  api.contextMenus.removeAll(() => {
    api.contextMenus.create({ id: MENU_LINK, title: "Send link to MediaGrab", contexts: ["link"] });
    api.contextMenus.create({ id: MENU_PAGE, title: "Send page to MediaGrab", contexts: ["page"] });
  });
}

function sendUrl(url) {
  if (typeof url !== "string" || !/^https?:\/\//i.test(url)) {
    return Promise.reject(new Error("Only HTTP(S) links can be sent to MediaGrab."));
  }
  return api.runtime.sendNativeMessage("io.github.SakibShahariar.MediaGrab", {
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

api.runtime.onInstalled.addListener(createMenus);
api.contextMenus.onClicked.addListener((info) => {
  const url = info.menuItemId === MENU_LINK ? info.linkUrl : info.pageUrl;
  sendUrl(url).catch((error) => {
    // Never log the URL: signed media links may contain private tokens.
    console.error("MediaGrab handoff failed:", error.message);
  });
});
