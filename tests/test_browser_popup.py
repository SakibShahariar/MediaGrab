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
def test_popup_scan_requires_explicit_user_click_and_redacts_query_in_display() -> None:
    source = (EXT / "chromium" / "popup.js").read_text(encoding="utf-8")
    assert 'scanButton.addEventListener("click"' in source
    assert "performance.getEntriesByType" in source
    assert "parsed.host + parsed.pathname" in source
    assert 'type: "add-url"' in source
