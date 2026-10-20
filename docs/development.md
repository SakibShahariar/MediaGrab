# Development Setup

These instructions target Fedora with GNOME. MediaGrab has a GTK4/libadwaita download queue, a basic HTTP(S) download core, an FFmpeg-backed HLS/DASH adapter, and an early manual browser-to-desktop handoff prototype. Browser scans now combine page-visible resource timing, video/audio elements, subtitle tracks, and media-looking links; this remains a user-triggered scan, not automatic request interception.

## Install system dependencies

```fish
sudo dnf install python3 python3-gobject gtk4 libadwaita ffmpeg
```

## Set up a development environment

From the repository root:

```fish
python3 -m venv --system-site-packages .venv
source .venv/bin/activate.fish
python -m pip install --editable ".[test]"
```

The `--system-site-packages` option lets the virtual environment see Fedora's PyGObject bindings. If GTK namespaces are unavailable, run the app with Fedora's system Python after installing the system packages.

## Run the app

```fish
mediagrab
```

Or, without installing the console entry point:

```fish
python -m mediagrab.main
```

## Run tests

```fish
python -m pytest -v
```

Tests use a local HTTP server and mocked FFmpeg processes; they do not need an external download URL or internet access.

## Current limitations

- Unfinished download URLs are saved to `$XDG_STATE_HOME/mediagrab/queue.json`, or `~/.local/state/mediagrab/queue.json` when `XDG_STATE_HOME` is not set.
- On restart, saved unfinished items are restored as **Interrupted**. They are not restarted automatically; use the retry button to resume or retry them.
- Queue persistence stores the full download URL so a queued item can be retried. Signed query parameters may be written to the per-user queue file; avoid sharing that file and remove sensitive entries when no longer needed. The queue UI redacts query and fragment values. URLs with embedded username/password credentials are rejected when creating or restoring tasks. Browser cookies and authorization headers are not currently collected. Partial transfer data remains in the selected download folder as `.part` files.
- Completed items are not persisted as history; their queue records are removed.
- At most three downloads run at once; additional downloads wait in the queue.
- Progress rows estimate remaining time only when a known total size and non-zero measured speed are available; streams without a known total show bytes received instead.
- The download folder defaults to `~/Downloads`. Use the folder button in the header to choose another location; the selection is saved in `$XDG_CONFIG_HOME/mediagrab/settings.json` (or `~/.config/mediagrab/settings.json`).
- Existing completed filenames are not overwritten.
- Interrupted direct downloads can resume if the server supports HTTP byte ranges and the saved partial has a matching validator (ETag or Last-Modified). If the server ignores the range request, MediaGrab restarts the partial from byte zero.
- Cancellation of direct downloads is cooperative and may wait for the current network read to return or time out.
- HLS/DASH downloads require FFmpeg (`sudo dnf install ffmpeg`) and remux to MKV without re-encoding. Some streams may fail due to expired URLs, missing browser authentication, unsupported codecs, or DRM; the app does not bypass DRM.
- Browser scans are still user-triggered and limited to page-visible URLs. They may miss blob URLs, opaque API endpoints, authenticated requests, hidden streams, and protected content. The extension does not continuously monitor browsing activity.

## Browser handoff prototype

The repository includes manual context-menu extensions and a native-messaging host. This is an early integration prototype, not automatic media detection.

### Install the native host for development

1. Install MediaGrab in the Python environment you intend to use, so the `mediagrab` command is available.
2. Use the native-host installer documented in [Browser Native Host Installer](browser-native-host-installer.md) to register the bridge for the browser you use.
3. For Chromium-family browsers, load `browser-extension/chromium` as an unpacked extension and provide its extension ID to the installer. For Firefox, load `browser-extension/firefox` as a temporary add-on if you are developing against an unpacked copy.
4. Right-click a normal HTTP(S) link and choose **Send link to MediaGrab**, or right-click the page and choose **Send page to MediaGrab**. The popup's **Scan this tab** action is a separate user-triggered candidate scan.

The native host uses a versioned JSON message framed with a four-byte little-endian length. It accepts only HTTP(S) URLs and rejects embedded username/password credentials. Signed query parameters can still be sensitive and are needed for some legitimate downloads; the bridge does not log the URL.

### Current browser integration limitations

- Browser handoff remains manual; a page URL is not necessarily a downloadable file.
- Popup scanning combines resource timing, media element sources, subtitle tracks, and media-looking links. Query strings are hidden in candidate labels, but retained for the actual handoff because signed URLs may be required.
- Resource-timing scans cannot read response bodies or reliably infer MIME types. They may miss blob URLs, hidden streams, and requests whose details are not exposed to the page.
- Browser extension behavior and GTK UI integration still need end-to-end testing on a desktop. Python CI tests validate the protocol boundary but cannot verify browser installation or visual behavior.
