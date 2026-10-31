#!/usr/bin/env python3
"""Install or remove MediaGrab native-messaging registrations for browsers."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from mediagrab.native_host import HOST_NAME

FIREFOX_ID = "mediagrab@github.com"
CHROMIUM_CONFIG_DIRS = {
    "chromium": Path("chromium"),
    "chrome": Path("google-chrome"),
    "brave": Path("BraveSoftware") / "Brave-Browser",
    "vivaldi": Path("vivaldi"),
}
CHROMIUM_BROWSERS = tuple(CHROMIUM_CONFIG_DIRS)
BROWSER_CHOICES = ("firefox", *CHROMIUM_BROWSERS, "both")


def browser_config_root(browser: str, home: Path | None = None) -> Path:
    """Return the default Linux per-user config root for a supported browser."""
    home = Path.home() if home is None else home
    if browser == "firefox":
        return home / ".mozilla"
    relative = CHROMIUM_CONFIG_DIRS.get(browser)
    if relative is None:
        raise ValueError(f"Unsupported browser: {browser}")
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")).expanduser()
    if not config_home.is_absolute():
        raise ValueError("XDG_CONFIG_HOME must be an absolute path")
    return config_home / relative


def browser_manifest_path(browser: str, root: Path) -> Path:
    """Return the registration manifest path under a browser's config root."""
    if browser == "firefox":
        return root / "native-messaging-hosts" / f"{HOST_NAME}.json"
    if browser in CHROMIUM_BROWSERS:
        return root / "NativeMessagingHosts" / f"{HOST_NAME}.json"
    raise ValueError(f"Unsupported browser: {browser}")


def build_manifest(browser: str, host_path: Path, extension_id: str) -> dict[str, object]:
    """Build a browser-specific native-messaging manifest."""
    if not host_path.is_absolute():
        raise ValueError("Native host path must be absolute")
    payload: dict[str, object] = {
        "name": HOST_NAME,
        "description": "MediaGrab browser-to-desktop handoff",
        "path": str(host_path),
        "type": "stdio",
    }
    if browser == "firefox":
        payload["allowed_extensions"] = [FIREFOX_ID]
        return payload
    if browser not in CHROMIUM_BROWSERS:
        raise ValueError(f"Unsupported browser: {browser}")
    if not extension_id:
        raise ValueError("Chromium-family browsers require the real extension ID (use --extension-id)")
    if len(extension_id) != 32 or any(char not in "abcdefghijklmnop" for char in extension_id):
        raise ValueError("Chromium extension ID must be 32 lowercase letters a-p")
    payload["allowed_origins"] = [f"chrome-extension://{extension_id}/"]
    return payload


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def install(browser: str, root: Path, host_path: Path, extension_id: str) -> Path:
    if not host_path.is_file() or not os.access(host_path, os.X_OK):
        raise ValueError(f"Native host is not an executable file: {host_path}")
    path = browser_manifest_path(browser, root)
    atomic_write_json(path, build_manifest(browser, host_path, extension_id))
    return path


def uninstall(browser: str, root: Path) -> Path:
    path = browser_manifest_path(browser, root)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", choices=BROWSER_CHOICES, default="both")
    parser.add_argument(
        "--extension-id",
        help="Chromium-family extension ID shown on its details page",
    )
    parser.add_argument(
        "--host-path",
        help="Absolute path to mediagrab-native-host; defaults to PATH lookup",
    )
    parser.add_argument("--config-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove MediaGrab registration files",
    )
    args = parser.parse_args(argv)
    browsers = ("firefox", "chromium") if args.browser == "both" else (args.browser,)
    host_string = args.host_path or shutil.which("mediagrab-native-host")
    if not args.uninstall and not host_string:
        parser.error("mediagrab-native-host not found; install MediaGrab or pass --host-path")
    host = Path(host_string).expanduser() if host_string else Path("/nonexistent")
    try:
        for browser in browsers:
            root = args.config_root or browser_config_root(browser)
            path = (
                uninstall(browser, root)
                if args.uninstall
                else install(browser, root, host, args.extension_id or "")
            )
            action = "Removed" if args.uninstall else "Installed"
            print(f"{action} {browser} registration: {path}")
    except (OSError, ValueError) as exc:
        print(f"MediaGrab native host setup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
