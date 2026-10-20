# MediaGrab

A native Linux download manager focused on reliable browser-to-desktop media capture, inspired by the workflow of Internet Download Manager (IDM).

> **Status:** Early implementation. The GTK4/libadwaita queue, HTTP(S) download core, browser handoff prototype, and HLS/DASH manifest inspection are implemented. Automatic background detection remains unfinished; the app now offers an in-app HLS variant chooser when a manifest is inspected. Direct-file downloads work natively; HLS/DASH manifest URLs are routed to an optional FFmpeg stream adapter.

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

Not every website or protected stream can be captured. MediaGrab does not bypass DRM or access controls.

## Current implementation

- GTK4/libadwaita queue with progress, cancellation, retry, and three concurrent downloads.
- Configurable destination folder, persisted settings, queue recovery, and ETA display.
- HTTP(S) transfers with safe filenames, partial files, validator-aware resume, cancellation, and atomic finalization.
- Optional FFmpeg-backed HLS/DASH downloads, stream-copy remuxing to MKV, progress and cancellation.
- Media classification, HLS variant and alternate audio/subtitle parsing, and DASH representation metadata extraction.
- **Manifest inspection and track selection:** fetches bounded HLS/DASH manifests, lists HLS variants and alternate audio/subtitle playlists, and offers optional external audio/subtitle selection. Selected streams are muxed into MKV with FFmpeg stream copy; track choices survive queue recovery and retry.
- Browser popup scans page-visible resource timing, media elements, subtitle tracks, and media-looking links. Handoffs are user-triggered.
- Automated tests run on Python 3.11–3.14.

## Inspect a stream manifest

After installing the project, run:

```fish
mediagrab-inspect 'https://example.test/path/master.m3u8'
mediagrab-inspect 'https://example.test/path/manifest.mpd' --timeout 20
```

The report shows available HLS resolutions and bitrates, alternate audio/subtitle declarations, or DASH representation metadata. In the desktop quality picker, optional external HLS audio and subtitle playlists can be selected and muxed into the resulting MKV when FFmpeg supports those tracks. Manifest fetches are limited to 4 MiB and use a finite timeout. Query strings are omitted from the report because they may contain signed credentials. Actual downloads still require the original URL and may fail if authentication, DRM, or site-specific behavior is involved.

## Next milestones

1. End-to-end browser handoff validation in Firefox and Chromium.
3. Improve user-controlled request observation where supported by browser APIs.
4. Add pause/resume controls, collision-safe simultaneous downloads, diagnostics, and packaging.

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
