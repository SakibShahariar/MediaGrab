# Development Setup

These instructions target Fedora with GNOME. MediaGrab currently has a GTK4/libadwaita download queue and a basic HTTP(S) download core. Browser media capture is not implemented yet.

## Install system dependencies

```fish
sudo dnf install python3 python3-gobject gtk4 libadwaita
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

Tests use a local HTTP server and do not need an external download URL or internet access.

## Current limitations

- Unfinished download URLs are saved to `$XDG_STATE_HOME/mediagrab/queue.json`, or `~/.local/state/mediagrab/queue.json` when `XDG_STATE_HOME` is not set.
- On restart, saved unfinished items are restored as **Interrupted**. They are not restarted automatically; use the retry button to resume or retry them.
- Queue persistence stores the full download URL so a queued item can be retried. If a URL contains signed query parameters or embedded credentials, those values may be written to the per-user queue file; avoid sharing that file and remove sensitive entries when no longer needed. Browser cookies and authorization headers are not currently collected. Partial transfer data remains in `~/Downloads` as `.part` files.
- Completed items are not persisted as history; their queue records are removed.
- At most three downloads run at once; additional downloads wait in the queue.
- Files are saved to `~/Downloads`; the destination is not configurable yet.
- Existing completed filenames are not overwritten.
- Interrupted downloads can resume if the server supports HTTP byte ranges. If the server ignores the range request, MediaGrab restarts the partial from byte zero.
- Cancellation is cooperative and may wait for the current network read to return or time out.
- Browser extension and native messaging integration are not implemented.


## Browser handoff prototype

The repository now includes manual context-menu extensions and a native-messaging host. This is an early integration prototype, not automatic media detection.

### Install the native host for development

1. Install MediaGrab in the Python environment you intend to use, so the `mediagrab` command is available.
2. Install the host launcher from `native-host/mediagrab-native-host` into a stable executable location, and ensure its Python environment can import the installed `mediagrab` package.
3. Copy the matching example manifest from `native-host/` to the native-messaging manifest location used by your browser. Replace `/usr/bin/mediagrab-native-host` with the actual absolute path.
4. Firefox's manifest goes in the Firefox native-messaging host directory. The Chromium-family manifest goes in the browser's native-messaging host directory; replace `REPLACE_WITH_EXTENSION_ID` with the extension ID shown after loading the unpacked extension.
5. Load `browser-extension/firefox` as a temporary add-on in Firefox, or `browser-extension/chromium` as an unpacked extension in a Chromium-family browser. For Chromium, enable developer mode on the extensions page.
6. Right-click a normal HTTP(S) link and choose **Send link to MediaGrab**, or right-click the page and choose **Send page to MediaGrab**.

The native host uses a versioned JSON message framed with a four-byte little-endian length. It accepts only HTTP(S) URLs and rejects embedded username/password credentials. Signed query parameters can still be sensitive and are needed for some legitimate downloads; MediaGrab does not log the URL in the bridge. The extension reports bridge errors to the browser console, not by displaying a popup yet.

### Current browser integration limitations

- This is manual handoff only; it does not inspect network requests, discover video streams, or choose quality.
- The extension passes the selected page/link URL. A page URL is not necessarily a downloadable file.
- Native-host registration is currently documented through example templates rather than an installer.
- Browser extension behavior and GTK UI integration still need end-to-end testing on a desktop. Python CI tests validate the protocol boundary but cannot verify browser installation or visual behavior.
