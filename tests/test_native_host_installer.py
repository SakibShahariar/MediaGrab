"""Tests for safe per-user native-messaging registration."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from scripts.install_native_host import build_manifest, install, uninstall, browser_manifest_path
from mediagrab.native_host import HOST_NAME

def executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path

def test_firefox_registration_uses_exact_extension_allowlist(tmp_path: Path) -> None:
    host = executable(tmp_path / "host")
    path = install("firefox", tmp_path, host, "")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["name"] == HOST_NAME
    assert payload["path"] == str(host)
    assert payload["type"] == "stdio"
    assert payload["allowed_extensions"] == ["mediagrab@github.com"]
    assert path.stat().st_mode & 0o777 == 0o600

def test_chromium_registration_requires_and_scopes_extension_id(tmp_path: Path) -> None:
    host = executable(tmp_path / "host")
    extension_id = "a" * 32
    payload = build_manifest("chromium", host, extension_id)
    assert payload["allowed_origins"] == [f"chrome-extension://{extension_id}/"]
    with pytest.raises(ValueError, match="real unpacked extension ID"):
        build_manifest("chromium", host, "")
    with pytest.raises(ValueError, match="32 lowercase letters"):
        build_manifest("chromium", host, "not-an-id")

def test_install_rejects_missing_or_non_executable_host(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not an executable file"):
        install("firefox", tmp_path, tmp_path / "missing-host", "")

def test_uninstall_is_idempotent_and_removes_only_registration(tmp_path: Path) -> None:
    host = executable(tmp_path / "host")
    path = install("firefox", tmp_path, host, "")
    other = path.parent / "keep.txt"
    other.write_text("keep", encoding="utf-8")
    assert uninstall("firefox", tmp_path) == path
    assert not path.exists()
    assert other.read_text(encoding="utf-8") == "keep"
    assert uninstall("firefox", tmp_path) == path

def test_browser_paths_are_distinct(tmp_path: Path) -> None:
    assert browser_manifest_path("firefox", tmp_path) != browser_manifest_path("chromium", tmp_path)
