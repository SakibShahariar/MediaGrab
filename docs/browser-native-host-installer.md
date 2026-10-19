# Browser Native Host Installer

The installer creates per-user native-messaging registration files. It does not install the Python package or browser extension for you.

## Install

From the repository root, after installing MediaGrab into the Python environment you want to use:

```fish
python -m pip install --editable ".[test]"
python scripts/install_native_host.py --browser firefox
```

For Chromium-family browsers, first load `browser-extension/chromium` as an unpacked extension, open its details page, and copy the extension ID. Then run:

```fish
python scripts/install_native_host.py --browser chromium --extension-id YOUR_32_LETTER_EXTENSION_ID
```

For both browsers, pass both settings:

```fish
python scripts/install_native_host.py --browser both --extension-id YOUR_32_LETTER_EXTENSION_ID
```

Firefox uses the fixed ID `mediagrab@github.com`. Chromium extension IDs must be exactly 32 lowercase letters from `a` to `p`. The installer locates `mediagrab-native-host` on `PATH`; use `--host-path /absolute/path/to/mediagrab-native-host` if necessary. It refuses to register a missing or non-executable host.

Registrations are written under `~/.mozilla/native-messaging-hosts/` for Firefox and `~/.config/chromium/NativeMessagingHosts/` for Chromium. The registration directory is owner-only and the manifest is mode `0600`. Existing registration files with the same MediaGrab host name are replaced.

## Remove

```fish
python scripts/install_native_host.py --browser firefox --uninstall
python scripts/install_native_host.py --browser chromium --uninstall
```

Uninstalling the registration does not remove MediaGrab, its extension, the download queue, or downloaded files. Restart the browser after installing or removing a registration. Brave/Vivaldi may require their own native-messaging directory; support for their paths is not claimed yet.
