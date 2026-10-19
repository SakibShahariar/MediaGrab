/* Manual handoff for Chromium-family browsers. */
const MENU_LINK = "mediagrab-send-link";
const MENU_PAGE = "mediagrab-send-page";

function createMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: MENU_LINK, title: "Send link to MediaGrab", contexts: ["link"] });
    chrome.contextMenus.create({ id: MENU_PAGE, title: "Send page to MediaGrab", contexts: ["page"] });
  });
}

function nativeMessage(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendNativeMessage("io.github.SakibShahariar.MediaGrab", message, (response) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(response);
    });
  });
}

function sendUrl(url) {
  if (typeof url !== "string" || !/^https?:\/\//i.test(url)) {
    return Promise.reject(new Error("Only HTTP(S) links can be sent to MediaGrab."));
  }
  return nativeMessage({ version: 1, type: "add-url", url }).then((response) => {
    if (!response || response.ok !== true) {
      throw new Error((response && response.error) || "MediaGrab did not accept the link.");
    }
    return response;
  });
}

chrome.runtime.onInstalled.addListener(createMenus);
chrome.contextMenus.onClicked.addListener((info) => {
  const url = info.menuItemId === MENU_LINK ? info.linkUrl : info.pageUrl;
  sendUrl(url).catch((error) => {
    // Never log the URL: signed media links may contain private tokens.
    console.error("MediaGrab handoff failed:", error.message);
  });
});
