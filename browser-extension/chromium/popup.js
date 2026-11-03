/* User-triggered page scan plus optional per-session network response detection. */
const api = typeof browser !== "undefined" ? browser : chrome;
const HOST_NAME = "io.github.SakibShahariar.MediaGrab";
const STORAGE_KEY = "mediagrabDetectedCandidates";
const OPTIONAL_ORIGINS = ["*://*/*"];
const scanButton = document.getElementById("scan");
const detectionButton = document.getElementById("toggle-detection");
const detectionStatus = document.getElementById("detection-status");
const statusNode = document.getElementById("status");
const list = document.getElementById("candidates");
const filterInput = document.getElementById("candidate-filter");
const MAX_CANDIDATES = 40;

function classify(url, hint = "", mime = "") {
  let parsed;
  try { parsed = new URL(url); } catch { return null; }
  if (!/^https?:$/.test(parsed.protocol) || parsed.username || parsed.password) return null;
  const path = parsed.pathname.toLowerCase();
  const contentType = mime.split(";", 1)[0].trim().toLowerCase();
  if (path.endsWith(".m3u8") || /mpegurl/.test(contentType)) return "HLS playlist";
  if (path.endsWith(".mpd") || contentType.includes("dash+xml")) return "DASH manifest";
  if (/\.(vtt|srt|ass|ssa|ttml|dfxp)$/.test(path) || contentType.includes("text/vtt")) return "Subtitle file";
  if (/\.(mp4|m4v|mkv|webm|mov|ogv|avi|mpeg|mpg)$/.test(path) || contentType.startsWith("video/")) return "Video file";
  if (/\.(mp3|m4a|aac|ogg|opus|wav|flac|weba)$/.test(path) || contentType.startsWith("audio/")) return "Audio file";
  if (/\.(ts|m4s|cmfv|cmfa|mp4v)$/.test(path)) return "Media segment";
  if (hint === "video") return "Video element source";
  if (hint === "audio") return "Audio element source";
  if (hint === "subtitle") return "Subtitle track";
  return null;
}

function priorityFor(kind) {
  if (kind === "HLS playlist" || kind === "DASH manifest") return 0;
  if (kind.includes("Subtitle")) return 1;
  if (kind.includes("Video")) return 2;
  if (kind.includes("Audio")) return 3;
  return 4;
}

async function refreshDetectionControls() {
  const enabled = await api.permissions.contains({origins: OPTIONAL_ORIGINS});
  detectionButton.dataset.enabled = enabled ? "true" : "false";
  detectionButton.textContent = enabled ? "Disable background detection" : "Enable background detection (all sites)";
  detectionStatus.textContent = enabled
    ? "On for HTTP(S) sites. Private-window availability follows your browser extension settings. Only response Content-Type and candidate URLs are observed; request headers and bodies are not read."
    : "Off by default. Enabling requests optional access to all HTTP(S) sites so cross-origin media CDN requests can be seen.";
}

detectionButton.addEventListener("click", async () => {
  detectionButton.disabled = true;
  try {
    const enabled = detectionButton.dataset.enabled === "true";
    if (enabled) {
      await api.permissions.remove({origins: OPTIONAL_ORIGINS});
      await api.storage.session.remove(STORAGE_KEY);
    } else {
      const granted = await api.permissions.request({origins: OPTIONAL_ORIGINS});
      if (!granted) detectionStatus.textContent = "Permission was not granted. Manual current-tab scanning still works.";
    }
    await refreshDetectionControls();
  } catch (error) {
    detectionStatus.textContent = "Could not change background detection permissions.";
    console.error("MediaGrab permission update failed:", error.message);
  } finally {
    detectionButton.disabled = false;
  }
});

function scanTab(tabId) {
  return api.scripting.executeScript({
    target: {tabId},
    func: () => {
      const resources = performance.getEntriesByType("resource").map((entry) => ({url: entry.name, hint: ""}));
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
      for (const link of document.querySelectorAll("a[href]")) candidates.push({url: link.href, hint: ""});
      return candidates.slice(-1000);
    }
  }).then((results) => (results && results[0] && results[0].result) || []);
}

async function getObservedCandidates(tabId) {
  const stored = await api.storage.session.get(STORAGE_KEY);
  const now = Date.now();
  return (Array.isArray(stored[STORAGE_KEY]) ? stored[STORAGE_KEY] : []).filter((item) =>
    item && item.tabId === tabId && typeof item.url === "string" &&
    Number.isFinite(item.lastSeenAt) && now - item.lastSeenAt >= 0 &&
    now - item.lastSeenAt < 30 * 60 * 1000
  );
}

async function removeObservedCandidate(tabId, url) {
  const stored = await api.storage.session.get(STORAGE_KEY);
  const candidates = Array.isArray(stored[STORAGE_KEY]) ? stored[STORAGE_KEY] : [];
  await api.storage.session.set({[STORAGE_KEY]: candidates.filter((item) => item.tabId !== tabId || item.url !== url)});
}

function sendNative(url, type = "add-candidate") {
  const message = {version: 1, type, url};
  if (typeof browser !== "undefined") return browser.runtime.sendNativeMessage(HOST_NAME, message);
  return new Promise((resolve, reject) => {
    chrome.runtime.sendNativeMessage(HOST_NAME, message, (response) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message)); else resolve(response);
    });
  });
}

function applyCandidateFilter() {
  const query = filterInput.value.trim().toLowerCase();
  for (const node of list.children) {
    node.hidden = Boolean(query) && !node.dataset.search.includes(query);
  }
}

filterInput.addEventListener("input", applyCandidateFilter);

function addCandidate(url, item, tabId) {
  const node = document.createElement("li");
  node.className = "candidate";
  const label = document.createElement("div");
  label.className = "kind";
  label.textContent = item.kind;
  const source = document.createElement("div");
  source.className = "source";
  source.textContent = item.observed ? "Observed network response" : "Page scan";
  const display = document.createElement("div");
  display.className = "url";
  const parsed = new URL(url);
  display.textContent = parsed.host + parsed.pathname;
  node.dataset.search = (item.kind + " " + parsed.host + parsed.pathname).toLowerCase();
  const button = document.createElement("button");
  button.textContent = "Review in MediaGrab";
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "Sending…";
    try {
      const response = await sendNative(url, "add-candidate");
      if (!response || response.ok !== true) throw new Error((response && response.error) || "MediaGrab rejected the URL");
      if (item.observed) removeObservedCandidate(tabId, url).catch((error) => {
        console.error("MediaGrab candidate cleanup failed:", error.message);
      });
      button.textContent = "Sent for review";
    } catch (error) {
      button.disabled = false;
      button.textContent = "Retry handoff";
      statusNode.textContent = "Handoff failed. Check that MediaGrab and its native host are installed.";
      console.error("MediaGrab handoff failed:", error.message);
    }
  });
  node.append(label, source, display, button);
  list.append(node);
}

scanButton.addEventListener("click", async () => {
  scanButton.disabled = true;
  list.replaceChildren();
  statusNode.textContent = "Scanning this tab and loading observed media responses…";
  try {
    const [tab] = await api.tabs.query({active: true, currentWindow: true});
    if (!tab || typeof tab.id !== "number") throw new Error("No active tab");
    const [resources, observed] = await Promise.all([scanTab(tab.id), getObservedCandidates(tab.id)]);
    const found = new Map();
    for (const item of observed) {
      const kind = item.kind || classify(item.url);
      if (kind) found.set(item.url, {kind, priority: priorityFor(kind), observed: true});
    }
    for (const item of resources) {
      if (!item || typeof item.url !== "string") continue;
      const kind = classify(item.url, item.hint);
      if (!kind || found.has(item.url)) continue;
      found.set(item.url, {kind, priority: priorityFor(kind), observed: false});
    }
    const sorted = [...found.entries()].sort((a, b) => a[1].priority - b[1].priority);
    for (const [url, item] of sorted.slice(0, MAX_CANDIDATES)) addCandidate(url, item, tab.id);
    const networkCount = sorted.filter(([, item]) => item.observed).length;
    statusNode.textContent = sorted.length
      ? "Found " + sorted.length + " possible resource(s), including " + networkCount + " observed network response(s); showing up to " + MAX_CANDIDATES + "."
      : "No recognizable media URLs found. This page may use blob URLs, protected streams, or opaque request URLs.";
  } catch (error) {
    statusNode.textContent = "Could not scan this tab. Check that the browser permits MediaGrab to access it.";
    console.error("MediaGrab scan failed:", error.message);
  } finally {
    scanButton.disabled = false;
  }
});

refreshDetectionControls().catch((error) => {
  detectionStatus.textContent = "Background detection permission status is unavailable.";
  console.error("MediaGrab permission status failed:", error.message);
});
