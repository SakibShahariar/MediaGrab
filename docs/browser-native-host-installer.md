# Browser Native Host Installer

The installer creates per-user native-messaging registration files. It does not install the Python package or browser extension for you.

## Install

From the repository root, after installing MediaGrab into the Python environment you want to use:

```fish
python -m pip install --editable ".[test]"
python scripts/install_native_host.py --browser firefox
```

For Chromium-family browsers, first load `browser-extension/chromium` as an unpacked extension, open its details page, and copy the extension ID. Then choose the browser you use:

```fish
python scripts/install_native_host.py --browser chromium --extension-id YOUR_32_LETTER_EXTENSION_ID
python scripts/install_native_host.py --browser chrome --extension-id YOUR_32_LETTER_EXTENSION_ID
python scripts/install_native_host.py --browser brave --extension-id YOUR_32_LETTER_EXTENSION_ID
python scripts/install_native_host.py --browser vivaldi --extension-id YOUR_32_LETTER_EXTENSION_ID
python scripts/install_native_host.py --browser edge --extension-id YOUR_32_LETTER_EXTENSION_ID
```

For Firefox and Chromium, pass both settings:

```fish
python scripts/install_native_host.py --browser both --extension-id YOUR_32_LETTER_EXTENSION_ID
```

Firefox uses the fixed ID `mediagrab@github.com`. Chromium-family extension IDs must be exactly 32 lowercase letters from `a` to `p`. The installer locates `mediagrab-native-host` on `PATH`; use `--host-path /absolute/path/to/mediagrab-native-host` if necessary. It refuses to register a missing or non-executable host.

The default user-level Linux registration directories are:

| Browser | Registration directory |
|---|---|
| Firefox | `~/.mozilla/native-messaging-hosts/` |
| Chromium | `~/.config/chromium/NativeMessagingHosts/` |
| Google Chrome | `~/.config/google-chrome/NativeMessagingHosts/` |
| Brave | `~/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts/` |
| Vivaldi | `~/.config/vivaldi/NativeMessagingHosts/` |
| Microsoft Edge | `~/.config/microsoft-edge/NativeMessagingHosts/` |

For Chromium-family browsers, `XDG_CONFIG_HOME` is respected when set to an absolute path. Microsoft Edge uses its documented Linux per-user location under `~/.config/microsoft-edge/NativeMessagingHosts/` ([Microsoft documentation](https://learn.microsoft.com/en-us/microsoft-edge/extensions-chromium/developer-guide/native-messaging)). The visible `--config-root /absolute/path` option can target a custom Chromium-family profile or sandbox-specific configuration directory; sandbox visibility and native-messaging permissions still depend on the browser package. Firefox uses its standard `~/.mozilla` location. The registration directory is owner-only and the manifest is mode `0600`. Existing registration files with the same MediaGrab host name are replaced.

**Packaging limitations:** Vivaldi's Snap and Flatpak packages do not expose the Native Messaging API; use the native Linux package. Brave Flatpak sandbox registration has not been validated. Browser-specific directories are implemented, but successful end-to-end handoff still needs testing in each installed browser.

## Remove

```fish
python scripts/install_native_host.py --browser firefox --uninstall
python scripts/install_native_host.py --browser chromium --uninstall
python scripts/install_native_host.py --browser chrome --uninstall
python scripts/install_native_host.py --browser brave --uninstall
python scripts/install_native_host.py --browser vivaldi --uninstall
python scripts/install_native_host.py --browser edge --uninstall
```

Uninstalling the registration does not remove MediaGrab, its extension, the download queue, or downloaded files. Restart the browser after installing or removing a registration.
