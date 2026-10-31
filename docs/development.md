# Development Setup

These instructions target Fedora with GNOME. MediaGrab includes a GTK4/libadwaita download queue, HTTP(S) transfers, an FFmpeg-backed HLS/DASH adapter, a bounded manifest inspector, and user-triggered browser media scanning and handoff.

## Install system dependencies

```fish
sudo dnf install python3 python3-gobject gtk4 libadwaita ffmpeg
```

## Set up a development environment

```fish
python3 -m venv --system-site-packages .venv
source .venv/bin/activate.fish
python -m pip install --editable ".[test]"
```

## Run the app and tests

```fish
mediagrab
python -m pytest -v
```

## Inspect HLS/DASH quality metadata

In the desktop app, choose **Add URL → Inspect media…** to fetch a manifest in a background worker and show its declared HLS video variants. Selecting a listed HLS variant queues that video playlist. Where the master manifest declares external audio/subtitle playlists, the dialog offers optional selectors; FFmpeg opens the chosen inputs and stream-copies the selected audio and subtitle streams into the MKV. These selections are persisted with unfinished queue entries and restored for manual retry. Use tracks belonging to the selected variant’s audio/subtitle groups; not every manifest declares compatible external tracks.

Install the editable package, then run:

```fish
mediagrab-inspect 'https://example.test/master.m3u8'
mediagrab-inspect 'https://example.test/manifest.mpd' --timeout 20
```

The inspector fetches only the manifest, caps its response at 4 MiB, uses a finite timeout, and prints URLs without query strings or fragments. It reports declared metadata, not a guarantee that a representation is playable. It does not collect browser cookies or authorization headers.

## Browser integration

MediaGrab provides manual Firefox and Chromium-family extensions. Scanning is user-triggered: the popup inspects page-visible resource timing entries, media elements, subtitle tracks, and links after you click **Scan this tab**. The extension uses `activeTab` and `scripting`; it does not request permanent access to every site or monitor all browser traffic in the background.

### Install the extension

- **Firefox:** open `about:debugging#/runtime/this-firefox`, choose **Load Temporary Add-on…**, and select `browser-extension/firefox/manifest.json`. Temporary add-ons must be loaded again after Firefox restarts.
- **Chromium, Chrome, Brave, or Vivaldi:** open the browser's extensions page, enable Developer mode, choose **Load unpacked**, and select the `browser-extension/chromium` directory. Copy the extension ID shown on that browser's extension details page.

### Register the native host

The native host is installed as the `mediagrab-native-host` console command when the editable package is installed. Register it for the browser you use:

```fish
python scripts/install_native_host.py --browser firefox
python scripts/install_native_host.py --browser chromium --extension-id YOUR_32_LETTER_EXTENSION_ID
python scripts/install_native_host.py --browser chrome --extension-id YOUR_32_LETTER_EXTENSION_ID
python scripts/install_native_host.py --browser brave --extension-id YOUR_32_LETTER_EXTENSION_ID
python scripts/install_native_host.py --browser vivaldi --extension-id YOUR_32_LETTER_EXTENSION_ID
```

For Firefox and Chromium together, `--browser both` registers both default locations; supply the Chromium extension ID as well. The installer writes user-level manifests and validates the executable path and extension ID. It respects `XDG_CONFIG_HOME` for Chromium-family browser configuration directories.

See [Browser Native Host Installer](browser-native-host-installer.md) for exact paths, removal commands, and package limitations.

### Use the extension

- Right-click a link and choose **Send link to MediaGrab**, or right-click the page and choose **Send page to MediaGrab**.
- Open the extension popup and choose **Scan this tab**. Review the candidates and send an individual URL to MediaGrab.
- The native host accepts HTTP(S) URLs and rejects malformed URLs and embedded username/password credentials. Signed query parameters may be required for legitimate downloads and are not logged by the bridge.

### Troubleshooting

1. **The browser says the native host is missing.** Confirm `mediagrab-native-host` is installed with `command -v mediagrab-native-host`. If it is outside `PATH`, pass its absolute executable path using `--host-path /absolute/path/to/mediagrab-native-host`.
2. **The browser cannot connect to the host.** Check that the registration file exists in the browser-specific directory listed in [the installer guide](browser-native-host-installer.md). Its `path` must point to an executable file, its `name` must be `io.github.SakibShahariar.MediaGrab`, and its allowed extension ID must match the ID shown by that browser.
3. **You changed or reloaded the unpacked extension.** Recheck its extension ID and rerun the installer with the current ID. Do not reuse an ID copied from a different browser.
4. **The extension still reports a connection error.** Restart the browser after registration changes. Inspect the extension's background/service-worker console for native-messaging errors; the host reserves stdout for protocol frames and writes diagnostics to stderr.
5. **A URL is rejected.** Only valid HTTP(S) URLs without embedded credentials are accepted. A signed query string is allowed, but unsupported schemes such as `file:` and `javascript:` are not.
6. **The browser package is sandboxed.** Vivaldi Snap and Flatpak packages do not expose the Native Messaging API. Brave Flatpak registration has not been validated; use a native browser package for the supported user-level handoff path.

## Current limitations

- Browser scanning is user-triggered and limited to page-visible resource timing, media elements, subtitle tracks, and media-looking links. It does not automatically observe every network request.
- Browser cookies and authorization headers are not currently collected; authenticated streams may fail.
- HLS alternate track selection works for external rendition playlists that FFmpeg can open and mux. Embedded/default tracks remain controlled by FFmpeg; track group compatibility and codec/container support depend on the source manifest.
- HLS/DASH downloads require FFmpeg and remux to MKV without re-encoding. DRM is not bypassed.
- Queue state stores full URLs so retry works; signed query parameters may be sensitive. The queue UI and inspector output redact query/fragment values.
- Unfinished downloads restore as Interrupted and require manual retry.
- At most three downloads run at once. Existing completed files are preserved; repeated names use numbered alternatives such as `file (1).zip`. Filename selection also skips names with an existing partial download.
- Actual Firefox/Chromium-family browser-to-desktop handoff and GTK UI behavior still need end-to-end testing on installed browsers.
