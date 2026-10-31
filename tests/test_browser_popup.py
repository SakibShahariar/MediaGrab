"""Static contract tests for the user-triggered media scan popup."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "browser-extension"


def test_both_extensions_expose_scan_popup_with_opt_in_detection() -> None:
    for browser in ("firefox", "chromium"):
        directory = EXT / browser
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        assert {"activeTab", "scripting", "webRequest", "storage"} <= set(manifest["permissions"])
        optional_hosts = manifest.get("optional_host_permissions", manifest.get("optional_permissions", []))
        assert "*://*/*" in optional_hosts
        assert all((directory / name).is_file() for name in ("popup.html", "popup.css", "popup.js"))
        assert "default_popup" in manifest.get("action", manifest.get("browser_action", {}))


def test_popup_scan_is_user_triggered_and_redacts_secrets_in_display() -> None:
    source = (EXT / "chromium" / "popup.js").read_text(encoding="utf-8")
    assert 'scanButton.addEventListener("click"' in source
    assert "performance.getEntriesByType" in source
    assert "parsed.host + parsed.pathname" in source
    assert 'type: "add-url"' in source
    assert "MAX_CANDIDATES = 40" in source
    assert "element.currentSrc" in source
    assert 'querySelectorAll("video, audio")' in source
    assert 'querySelectorAll("track[src]")' in source
    assert 'querySelectorAll("a[href]")' in source
    assert 'path.endsWith(".m3u8")' in source
    assert 'return "Subtitle file"' in source
    assert "priority - b[1].priority" in source


def test_firefox_and_chromium_popup_implementations_stay_in_sync() -> None:
    firefox = (EXT / "firefox" / "popup.js").read_text(encoding="utf-8")
    chromium = (EXT / "chromium" / "popup.js").read_text(encoding="utf-8")
    assert firefox == chromium
    firefox_html = (EXT / "firefox" / "popup.html").read_text(encoding="utf-8")
    chromium_html = (EXT / "chromium" / "popup.html").read_text(encoding="utf-8")
    assert firefox_html == chromium_html



def test_background_detection_is_opt_in_session_only_and_header_minimal() -> None:
    for browser in ("firefox", "chromium"):
        source = (EXT / browser / "background.js").read_text(encoding="utf-8")
        assert "webRequest.onHeadersReceived.addListener" in source
        assert '"responseHeaders"' in source
        assert "storage.session" in source
        assert "tabId" in source
        assert "CANDIDATE_TTL_MS" in source
        assert "MAX_CANDIDATES = 100" in source
        assert "tabs.onRemoved" in source
        assert "permissions.onRemoved" in source
        assert "requestHeaders" not in source
        assert "filterResponseData" not in source


def test_popup_exposes_explicit_background_permission_control() -> None:
    source = (EXT / "chromium" / "popup.js").read_text(encoding="utf-8")
    html = (EXT / "chromium" / "popup.html").read_text(encoding="utf-8")
    assert 'id="toggle-detection"' in html
    assert 'id="detection-status"' in html
    assert "api.permissions.request" in source
    assert 'detectionButton.dataset.enabled === "true"' in source
    assert "api.permissions.remove" in source
    assert "api.storage.session.get" in source
    assert "Observed network response" in source
    assert "parsed.host + parsed.pathname" in source


def test_firefox_and_chromium_background_observers_stay_in_sync() -> None:
    firefox = (EXT / "firefox" / "background.js").read_text(encoding="utf-8")
    chromium = (EXT / "chromium" / "background.js").read_text(encoding="utf-8")
    assert firefox == chromium



def test_background_keeps_existing_context_menu_native_handoff() -> None:
    for browser in ("firefox", "chromium"):
        source = (EXT / browser / "background.js").read_text(encoding="utf-8")
        assert "contextMenus.onClicked" in source
        assert "Send link to MediaGrab" in source
        assert "sendNativeMessage" in source
        assert 'type: "add-url"' in source
