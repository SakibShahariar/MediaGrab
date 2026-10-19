"""Keep the shipped browser manifests aligned with the native host."""
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_firefox_manifest_declares_native_messaging_and_stable_id() -> None:
    manifest = json.loads((ROOT / "browser-extension/firefox/manifest.json").read_text())
    assert "nativeMessaging" in manifest["permissions"]
    assert manifest["browser_specific_settings"]["gecko"]["id"] == "mediagrab@github.com"


def test_chromium_manifest_uses_service_worker_and_native_messaging() -> None:
    manifest = json.loads((ROOT / "browser-extension/chromium/manifest.json").read_text())
    assert manifest["manifest_version"] == 3
    assert manifest["background"]["service_worker"] == "background.js"
    assert "nativeMessaging" in manifest["permissions"]


def test_native_host_templates_use_matching_name_and_expected_allowlist() -> None:
    firefox = json.loads((ROOT / "native-host/io.github.SakibShahariar.MediaGrab.json.example").read_text())
    chromium = json.loads((ROOT / "native-host/chromium-host.json.example").read_text())
    assert firefox["name"] == chromium["name"] == "io.github.SakibShahariar.MediaGrab"
    assert firefox["allowed_extensions"] == ["mediagrab@github.com"]
    assert "REPLACE_WITH_EXTENSION_ID" in chromium["allowed_origins"][0]
