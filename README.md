# MediaGrab

A native Linux download manager focused on reliable browser-to-desktop media capture, inspired by the workflow of Internet Download Manager (IDM).

> **Status:** Early implementation. The GTK4/libadwaita queue, HTTP(S) download core, media-manifest inspection helpers, and a manual Firefox/Chromium browser-to-desktop handoff prototype are implemented. Automatic media detection and stream downloading are not implemented yet.

## Goals

- A polished GTK4/libadwaita desktop experience for GNOME and other Linux desktops.
- Cross-browser integration: Firefox and Chromium-based browsers, with Brave, Vivaldi, and other compatible browsers supported where their extension and native-messaging APIs permit.
- Detect downloadable media and offer clear choices for available streams and qualities where technically possible.
- Hand downloads from the browser to the desktop app through a versioned native-messaging bridge (manual context-menu handoff prototype now exists).
- Handle authenticated media carefully, using only browser-session information that the user is authorized to access.
- Keep the application modular, testable, and mindful of resource use.

## Planned architecture

```text
Browser WebExtension
        |
        | browser APIs and native messaging
        v
Native messaging host
        |
        v
MediaGrab core / capture engine
        |
        +---- media and stream inspection
        +---- download queue and retry policy
        +---- destination and file management
        |
        v
GTK4 / libadwaita desktop app
```

The extension will detect candidate media using documented browser APIs. The native host will validate and pass structured messages to the local application. The capture engine will determine which downloads are actually feasible; not every website or protected stream can be captured.

## Current implementation

- GTK4/libadwaita download queue with progress, cancellation, retry, and a three-download concurrency limit.
- HTTP(S) downloads with safe filenames, progress reporting, partial files, cooperative cancellation, and atomic finalization.
- Validator-aware resume using ETag or Last-Modified, including bounded byte-range responses and safe restart when range continuation is unavailable.
- Crash-resistant persistence for unfinished queue entries; interrupted items can be retried after restart.
- Initial media inspection helpers for direct media, HLS, and DASH classification, HLS master-playlist variant parsing, alternate HLS audio/subtitle track parsing, and DASH representation metadata extraction.
- Automated tests for transfers and media parsing, run by GitHub Actions on Python 3.11–3.14.

## Next milestones

1. **End-to-end browser handoff:** native-host registration installer added; validate Firefox and Chromium-family context menus against a running desktop session.
2. **Automatic detection:** observe documented browser-visible media signals and pass candidate URLs to the capture engine without collecting secrets unnecessarily.
3. **Media capture:** inspect browser-observed media requests and HLS/DASH manifests; expose quality choices only when verified. DASH template-based segment downloading remains future work.
4. **Reliability and polish:** configurable destinations, richer transfer controls, diagnostics with secrets redacted, packaging, and broader browser validation.

## Development principles

- Implement independently using public documentation and observable behavior; do not copy proprietary IDM code or bundle proprietary extension files.
- Prefer coherent, reviewable feature batches with automated tests; avoid splitting a feature into unnecessary implementation/test-only commit pairs.
- Be explicit about unsupported sites and protected content instead of promising universal capture.
- Keep browser detection, extraction, downloading, and UI responsibilities separated.

## Project layout

- `app/` — GTK4/libadwaita interface
- `browser-extension/` — browser extension
- `native-host/` — native messaging bridge
- `capture-engine/` — media inspection and extraction
- `docs/` — architecture and development notes
- `research/` — independently written behavioral observations
- `tests/` — automated tests

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines. Browser handoff setup and current limitations are documented in [docs/development.md](docs/development.md) and [the native-host installer guide](docs/browser-native-host-installer.md).

## License

The project license will be selected before distributing implementation code. Do not assume this repository grants permission to use third-party proprietary assets or code.
