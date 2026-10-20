"""Static contract tests for the user-triggered media scan popup."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "browser-extension"


def test_both_extensions_expose_scan_popup_with_minimal_permissions() -> None:
    for browser in ("firefox", "chromium"):
        directory = EXT / browser
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        assert "activeTab" in manifest["permissions"] and "scripting" in manifest["permissions"]
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
