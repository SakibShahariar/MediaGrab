# MediaGrab

A native Linux download manager focused on reliable browser-to-desktop media capture, inspired by the workflow of Internet Download Manager (IDM).

> **Status:** Early implementation. The GTK4/libadwaita queue, HTTP(S) download core, browser handoff prototype, and HLS/DASH manifest inspection are implemented. Optional background response observation is available in the browser popup. Users can review detected candidates there and send them to MediaGrab's persistent in-app review inbox; candidates do not start downloading until explicitly approved. The app also offers an HLS variant chooser when a manifest is inspected. Direct-file downloads work natively; HLS/DASH manifest URLs are routed to an optional FFmpeg stream adapter.

## Goals

- A polished GTK4/libadwaita desktop experience for GNOME and other Linux desktops.
- Cross-browser integration: Firefox and Chromium-based browsers, with compatible browsers supported where their extension and native-messaging APIs permit it.
- Detect downloadable media and offer clear choices for available streams and qualities where technically possible.
- Hand downloads from the browser to the desktop app through a versioned native-messaging bridge.
- Keep the application modular, testable, and mindful of resource use.

## Planned architecture

```text
Browser WebExtension -> Native messaging host -> MediaGrab core
                                             -> manifest inspection
                                             -> download queue
                                             -> GTK4/libadwaita UI
```

Direct HTTP(S) downloads can be paused and resumed; pause is cooperative and may take up to one network read timeout to take effect. FFmpeg-backed HLS/DASH tasks do not currently support pause. Not every website or protected stream can be captured. MediaGrab does not bypass DRM or access controls.

## Current implementation

- GTK4/libadwaita queue with progress, cancellation, retry, and three concurrent downloads.
- Configurable destination folder, persisted settings, queue recovery, and ETA display.
- HTTP(S) transfers with safe filenames, automatic numbered names for collisions, partial files, validator-aware resume, cooperative pause/resume, cancellation, and atomic finalization.
- Optional FFmpeg-backed HLS/DASH downloads, collision-safe numbered MKV outputs, stream-copy remuxing, progress and cancellation.
- Media classification, HLS variant and alternate audio/subtitle parsing, and DASH representation metadata extraction.
- **Manifest inspection and track selection:** fetches bounded HLS/DASH manifests, lists HLS variants and alternate audio/subtitle playlists, and offers optional external audio/subtitle selection. Selected streams are muxed into MKV with FFmpeg stream copy; track choices survive queue recovery and retry.
- Browser popup scans page-visible resources and can optionally observe media response URLs and Content-Type headers across HTTP(S) sites after explicit all-sites permission. Candidates stay in browser-session memory, are deduplicated per tab, and are reviewed before handoff.
- Structured JSONL diagnostics record download and capture lifecycle events, redact sensitive values, rotate within a bounded size, and use private file permissions. Verbosity is configurable and redacted logs can be copied from the app.
- Automated tests run on Python 3.11–3.14.
- A [support matrix](docs/support-matrix.md) distinguishes tested core behavior from outstanding real-world and browser validation.

## Browser integration

The Firefox and Chromium-family extensions support manual link/page handoff, user-triggered current-tab scanning, and optional background response observation after the user grants all-sites HTTP(S) permission. Detected candidates can be sent to the persistent in-app review inbox without starting a download. Private/incognito tabs are excluded from background response capture, page scanning, and context-menu handoff even if the browser permits the extension to run there; MediaGrab does not offer a private-window capture exception. Install the extension and register the native host using the [browser installation guide](docs/browser-native-host-installer.md).

## Command-line control

The `mediagrab` command forwards operations to the running desktop application through its single-instance `GApplication` command-line channel (D-Bus activation). It can add URLs, inspect the current in-memory queue, and control queue items:

```fish
mediagrab --add-url 'https://example.test/video.mp4'
mediagrab --add-candidate 'https://example.test/master.m3u8'
mediagrab --list
mediagrab --status
mediagrab --pause 1
mediagrab --resume 1
mediagrab --retry 1
mediagrab --cancel 1
```

`--list` prints JSON rows with a 1-based queue ID, a redacted source URL, and the current status. `--status` prints JSON counts. Queue IDs are positional and can change when items are removed; obtain fresh IDs with `--list` before acting. Pause is available only for direct HTTP(S) downloads; FFmpeg-backed HLS/DASH transfers cannot currently be paused. Resume and retry both requeue an interrupted, paused, failed, cancelled, or detected item. URL inputs are restricted to HTTP(S) and URLs containing embedded credentials are rejected. This command-line channel uses the desktop application's existing single-instance D-Bus activation; a separately versioned public D-Bus object API is not yet exposed.

## Inspect a stream manifest

After installing the project, run:

```fish
mediagrab-inspect 'https://example.test/path/master.m3u8'
mediagrab-inspect 'https://example.test/path/manifest.mpd' --timeout 20
```

The report shows available HLS resolutions and bitrates, alternate audio/subtitle declarations, or DASH representation metadata. In the desktop quality picker, optional external HLS audio and subtitle playlists can be selected and muxed into the resulting MKV when FFmpeg supports those tracks. Manifest fetches are limited to 4 MiB and use a finite timeout. Query strings are omitted from the report because they may contain signed credentials. Actual downloads still require the original URL and may fail if authentication, DRM, or site-specific behavior is involved.

## Next milestones

1. Complete installed Firefox and Chromium browser-to-desktop end-to-end validation ([#14](https://github.com/SakibShahariar/MediaGrab/issues/14)).
2. Validate Brave and Vivaldi compatibility ([#12](https://github.com/SakibShahariar/MediaGrab/issues/12)).
3. Package MediaGrab for Fedora ([#11](https://github.com/SakibShahariar/MediaGrab/issues/11)).

## Development principles

- Implement independently using public documentation and observable behavior; do not copy proprietary IDM code or bundle proprietary extension files.
- Prefer coherent feature batches with automated tests.
- Be explicit about unsupported sites and protected content.
- Keep browser detection, inspection, downloading, and UI responsibilities separated.

## Project layout

- `app/` — GTK4/libadwaita interface and download core
- `browser-extension/` — browser extensions
- `native-host/` — native messaging bridge
- `docs/` — architecture and development notes
- `tests/` — automated tests

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/development.md](docs/development.md).

## License

The project license will be selected before distributing implementation code.
