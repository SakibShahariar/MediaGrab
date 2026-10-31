"""Tests for safe per-user native-messaging registration."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mediagrab.native_host import HOST_NAME
from scripts.install_native_host import (
    browser_config_root,
    browser_manifest_path,
    build_manifest,
    install,
    uninstall,
)


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


@pytest.mark.parametrize(
    "browser",
    ["chromium", "chrome", "brave", "vivaldi"],
)
def test_chromium_family_registration_requires_and_scopes_extension_id(
    tmp_path: Path, browser: str
) -> None:
    host = executable(tmp_path / "host")
    extension_id = "a" * 32
    payload = build_manifest(browser, host, extension_id)

    assert payload["name"] == HOST_NAME
    assert payload["path"] == str(host)
    assert payload["type"] == "stdio"
    assert payload["allowed_origins"] == [f"chrome-extension://{extension_id}/"]
    with pytest.raises(ValueError, match="real extension ID"):
        build_manifest(browser, host, "")
    with pytest.raises(ValueError, match="32 lowercase letters"):
        build_manifest(browser, host, "not-an-id")


@pytest.mark.parametrize(
    ("browser", "relative"),
    [
        ("chromium", Path("chromium")),
        ("chrome", Path("google-chrome")),
        ("brave", Path("BraveSoftware") / "Brave-Browser"),
        ("vivaldi", Path("vivaldi")),
    ],
)
def test_browser_config_roots_use_expected_linux_locations(
    tmp_path: Path, monkeypatch, browser: str, relative: Path
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    home = tmp_path / "home"
    assert browser_config_root(browser, home) == home / ".config" / relative


def test_browser_config_roots_respect_xdg_config_home(tmp_path: Path, monkeypatch) -> None:
    config_home = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    assert browser_config_root("brave", tmp_path / "home") == (
        config_home / "BraveSoftware" / "Brave-Browser"
    )


def test_browser_config_root_rejects_relative_xdg_config_home(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative-config")
    with pytest.raises(ValueError, match="absolute path"):
        browser_config_root("chromium", tmp_path / "home")


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


def test_browser_paths_are_distinct(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    home = tmp_path / "home"
    browsers = ("firefox", "chromium", "chrome", "brave", "vivaldi")
    paths = {
        browser_manifest_path(browser, browser_config_root(browser, home))
        for browser in browsers
    }
    assert len(paths) == len(browsers)
