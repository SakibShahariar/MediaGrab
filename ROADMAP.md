# MediaGrab Roadmap

MediaGrab has an initial GTK4/libadwaita queue and HTTP(S) download core. Milestones are ordered to validate reliable transfers before investing heavily in advanced media extraction.

## Phase 1 — Repository foundation

- [x] Document goals and planned architecture in README.
- [x] Add architecture notes and development conventions.
- [x] Establish a Python project and test runner.
- [x] Add CI for automated tests across Python 3.11–3.14.

## Phase 2 — Native desktop shell

- [x] Build the initial GTK4/libadwaita application window.
- [x] Implement queue rows and queued, active, completed, failed, cancelled, and interrupted states.
- [x] Add a paused queue state and pause/resume controls for direct HTTP(S) downloads.
- [x] Add a configurable download destination and persist the selection.
- [ ] Verify responsiveness with a large queue.

## Phase 3 — Download core

- [x] Implement ordinary HTTP(S) downloads.
- [x] Report progress and transfer speed.
- [x] Report estimated remaining time when total size and transfer speed are available.
- [x] Support cooperative pause/resume for direct HTTP(S) downloads; FFmpeg streams remain non-pausable.
- [x] Handle retries, timeouts, redirects, and partial files with validator-aware resume.
- [x] Add tests using a local test HTTP server.

## Phase 4 — Cross-browser integration

- [x] Define a versioned, browser-neutral message protocol and validate every message at the native boundary.
- [x] Add the native-messaging host, installable console entry point, and per-browser registration templates.
- [x] Create a Firefox WebExtension with manual link/page context-menu handoff.
- [x] Create a Chromium Manifest V3 extension with manual link/page context-menu handoff.
- [ ] Verify compatibility with Brave, Vivaldi, and other Chromium browsers where host registration permits it.
- [x] Add a manual “send link/page to MediaGrab” flow in Firefox and Chromium-family extensions (end-to-end browser testing still pending).
- [x] Add a user-level native-host registration installer; end-to-end browser testing remains pending.

## Phase 5 — Media capture

- [x] Add site-independent URL/MIME classification for direct media, HLS, and DASH candidates.
- [x] Parse HLS master playlists into variant URLs, bandwidth, resolution, and codec metadata.
- [x] Parse HLS alternate audio and subtitle tracks, including language and default/forced flags.
- [ ] Detect candidate media URLs from supported browser signals.
- [x] Parse DASH representation metadata, including inherited MIME/codecs and explicit BaseURL values.
- [x] Add optional FFmpeg-backed HLS/DASH stream downloads with cancellation and safe finalization (real-world site validation still pending).
- [ ] Validate HLS/DASH behavior against real-world playlist samples and cover advanced DASH segment-template edge cases.
- [ ] Inspect available variants and expose quality choices only when known.
- [ ] Handle relevant request metadata and cookies without logging secrets.
- [ ] Add site-independent tests and clearly document unsupported cases.

## Phase 6 — Reliability and packaging

- [ ] Add structured diagnostics with secrets redacted.
- [ ] Test interruption, app restart, and queue recovery.
- [ ] Measure CPU and memory use during idle and active capture.
- [ ] Package for Fedora first; evaluate other distributions afterward.
- [ ] Validate additional Chromium-family browsers and maintain browser-specific installation notes.

## Acceptance principles

- A feature is complete only when it works in a reproducible test and its limitations are documented.
- Avoid promising universal capture: sites differ, and DRM or other protections may prevent downloading.
- Keep the UI, browser integration, extraction logic, and transfer engine modular.
