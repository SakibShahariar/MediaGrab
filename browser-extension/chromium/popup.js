/* User-triggered scan: no page is inspected until the user presses Scan. */
const api = typeof browser !== "undefined" ? browser : chrome;
const HOST_NAME = "io.github.SakibShahariar.MediaGrab";
const scanButton = document.getElementById("scan");
const statusNode = document.getElementById("status");
const list = document.getElementById("candidates");
function classify(url) {
  const path = new URL(url).pathname.toLowerCase();
  if (path.endsWith(".m3u8")) return "HLS playlist";
  if (path.endsWith(".mpd")) return "DASH manifest";
  if (/\.(mp4|m4v|mkv|webm|mov|ogv)$/.test(path)) return "Video file";
  if (/\.(mp3|m4a|aac|ogg|opus|wav|flac)$/.test(path)) return "Audio file";
  if (/\.(ts|m4s|cmfv|cmfa)$/.test(path)) return "Media segment";
  return null;
}
function scanTab(tabId) {
  return api.scripting.executeScript({target: {tabId}, func: () =>
    performance.getEntriesByType("resource").map((entry) => entry.name).slice(-200)
  }).then((results) => (results && results[0] && results[0].result) || []);
}
function sendNative(url) {
  const message = {version: 1, type: "add-url", url};
  if (typeof browser !== "undefined") return browser.runtime.sendNativeMessage(HOST_NAME, message);
  return new Promise((resolve, reject) => {
    chrome.runtime.sendNativeMessage(HOST_NAME, message, (response) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message)); else resolve(response);
    });
  });
}
function addCandidate(url, kind) {
  const item = document.createElement("li"); item.className = "candidate";
  const label = document.createElement("div"); label.className = "kind"; label.textContent = kind;
  const display = document.createElement("div"); display.className = "url";
  const parsed = new URL(url); display.textContent = parsed.host + parsed.pathname;
  const button = document.createElement("button"); button.textContent = "Send to MediaGrab";
  button.addEventListener("click", async () => {
    button.disabled = true; button.textContent = "Sending…";
    try {
      const response = await sendNative(url);
      if (!response || response.ok !== true) throw new Error((response && response.error) || "MediaGrab rejected the URL");
      button.textContent = "Added";
    } catch (error) {
      button.disabled = false; button.textContent = "Retry handoff";
      statusNode.textContent = "Handoff failed. Check that MediaGrab and its native host are installed.";
      console.error("MediaGrab handoff failed:", error.message);
    }
  });
  item.append(label, display, button); list.append(item);
}
scanButton.addEventListener("click", async () => {
  scanButton.disabled = true; list.replaceChildren(); statusNode.textContent = "Scanning resources loaded by this tab…";
  try {
    const [tab] = await api.tabs.query({active: true, currentWindow: true});
    if (!tab || typeof tab.id !== "number") throw new Error("No active tab");
    const resources = await scanTab(tab.id); const found = new Map();
    for (const raw of resources) {
      if (typeof raw !== "string" || !/^https?:\/\//i.test(raw)) continue;
      let parsed; try { parsed = new URL(raw); } catch { continue; }
      if (parsed.username || parsed.password) continue;
      const kind = classify(raw); if (kind && !found.has(raw)) found.set(raw, kind);
    }
    for (const [url, kind] of [...found.entries()].slice(0, 30)) addCandidate(url, kind);
    statusNode.textContent = found.size ? "Found " + found.size + " possible media resource(s). Choose what to send."
      : "No recognizable media URLs found. This page may use blob URLs, encrypted streams, or resources without file extensions.";
  } catch (error) {
    statusNode.textContent = "Could not scan this tab. Try a normal website tab and check extension permissions.";
    console.error("MediaGrab scan failed:", error.message);
  } finally { scanButton.disabled = false; }
});
