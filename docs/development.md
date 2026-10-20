# Development Setup

These instructions target Fedora with GNOME. MediaGrab includes a GTK4/libadwaita download queue, HTTP(S) transfers, an FFmpeg-backed HLS/DASH adapter, a bounded manifest inspector, and manual browser handoff.

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

## Current limitations

- Browser scanning is user-triggered and limited to page-visible resource timing, media elements, subtitle tracks, and media-looking links.
- Browser cookies and authorization headers are not currently collected; authenticated streams may fail.
- HLS alternate track selection works for external rendition playlists that FFmpeg can open and mux. Embedded/default tracks remain controlled by FFmpeg; track group compatibility and codec/container support depend on the source manifest.
- HLS/DASH downloads require FFmpeg and remux to MKV without re-encoding. DRM is not bypassed.
- Queue state stores full URLs so retry works; signed query parameters may be sensitive. The queue UI and inspector output redact query/fragment values.
- Unfinished downloads restore as Interrupted and require manual retry.
- At most three downloads run at once. Existing completed filenames are not overwritten.
- Browser extension behavior and GTK UI integration still need end-to-end desktop testing.

## Browser handoff prototype

The repository includes manual context-menu extensions and a native messaging host. For Chromium, load `browser-extension/chromium` as an unpacked extension and configure its ID using the native-host installer. For Firefox, load `browser-extension/firefox` as a temporary add-on during development. Use **Send link to MediaGrab** from a link context menu or click the popup and choose **Scan this tab**.

The native host accepts HTTP(S) URLs and rejects embedded username/password credentials. Signed query parameters may be required for valid downloads and are not logged by the bridge.
