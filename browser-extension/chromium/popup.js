/* User-triggered scan: inspect only the active tab after an explicit click. */
const api = typeof browser !== "undefined" ? browser : chrome;
const HOST_NAME = "io.github.SakibShahariar.MediaGrab";
const scanButton = document.getElementById("scan");
const statusNode = document.getElementById("status");
const list = document.getElementById("candidates");
const MAX_CANDIDATES = 40;

function classify(url, hint = "") {
  let parsed;
  try { parsed = new URL(url); } catch { return null; }
  if (!/^https?:$/.test(parsed.protocol) || parsed.username || parsed.password) return null;
  const path = parsed.pathname.toLowerCase();
  if (path.endsWith(".m3u8")) return "HLS playlist";
  if (path.endsWith(".mpd")) return "DASH manifest";
  if (/\.(vtt|srt|ass|ssa|ttml|dfxp)$/.test(path)) return "Subtitle file";
  if (/\.(mp4|m4v|mkv|webm|mov|ogv|avi|mpeg|mpg)$/.test(path)) return "Video file";
  if (/\.(mp3|m4a|aac|ogg|opus|wav|flac|weba)$/.test(path)) return "Audio file";
  if (/\.(ts|m4s|cmfv|cmfa|mp4v)$/.test(path)) return "Media segment";
  if (hint === "video") return "Video element source";
  if (hint === "audio") return "Audio element source";
  if (hint === "subtitle") return "Subtitle track";
  return null;
}

function scanTab(tabId) {
  return api.scripting.executeScript({
    target: {tabId},
    func: () => {
      const resources = performance.getEntriesByType("resource").map((entry) => ({
        url: entry.name, hint: ""
      }));
      const candidates = [...resources];
      for (const element of document.querySelectorAll("video, audio")) {
        const hint = element.tagName.toLowerCase();
        if (element.currentSrc) candidates.push({url: element.currentSrc, hint});
        if (element.src) candidates.push({url: element.src, hint});
        for (const source of element.querySelectorAll("source")) {
          if (source.src) candidates.push({url: source.src, hint});
        }
        if (hint === "video" && element.poster) candidates.push({url: element.poster, hint: ""});
        for (const track of element.querySelectorAll("track[src]")) {
          candidates.push({url: track.src, hint: "subtitle"});
        }
      }
      for (const link of document.querySelectorAll("a[href]")) {
        candidates.push({url: link.href, hint: ""});
      }
      return candidates.slice(-1000);
    }
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
  scanButton.disabled = true; list.replaceChildren();
  statusNode.textContent = "Scanning loaded resources, media elements, subtitle tracks, and links…";
  try {
    const [tab] = await api.tabs.query({active: true, currentWindow: true});
    if (!tab || typeof tab.id !== "number") throw new Error("No active tab");
    const resources = await scanTab(tab.id);
    const found = new Map();
    for (const item of resources) {
      if (!item || typeof item.url !== "string") continue;
      const kind = classify(item.url, item.hint);
      if (!kind || found.has(item.url)) continue;
      const priority = kind === "HLS playlist" || kind === "DASH manifest" ? 0
        : kind.includes("Subtitle") || kind === "Subtitle track" ? 1
        : kind.includes("Video") || kind === "Video file" ? 2
        : kind.includes("Audio") || kind === "Audio file" ? 3 : 4;
      found.set(item.url, {kind, priority});
    }
    const sorted = [...found.entries()].sort((a, b) => a[1].priority - b[1].priority);
    for (const [url, item] of sorted.slice(0, MAX_CANDIDATES)) addCandidate(url, item.kind);
    statusNode.textContent = sorted.length
      ? "Found " + sorted.length + " possible resource(s); showing up to " + MAX_CANDIDATES + ". Manifests and media files are listed first."
      : "No recognizable media URLs found. This page may use blob URLs, protected streams, or opaque request URLs.";
  } catch (error) {
    statusNode.textContent = "Could not scan this tab. Try a normal website tab and check extension permissions.";
    console.error("MediaGrab scan failed:", error.message);
  } finally { scanButton.disabled = false; }
});
