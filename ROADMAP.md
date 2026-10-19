# MediaGrab Roadmap

MediaGrab has an initial GTK4/libadwaita queue and HTTP(S) download core. Milestones are ordered to validate reliable transfers before investing heavily in advanced media extraction.

## Phase 1 — Repository foundation

- [x] Document goals and planned architecture in README.
- [ ] Add architecture notes and development conventions.
- [ ] Establish a minimal Python project and test runner.
- [ ] Add CI for linting and tests.

## Phase 2 — Native desktop shell

- [x] Build the initial GTK4/libadwaita application window.
- [x] Implement queue rows and queued, active, completed, failed, cancelled, and interrupted states.
- [ ] Add a paused queue state and pause/resume controls.
- [ ] Verify responsiveness with a large queue.

## Phase 3 — Download core

- [x] Implement ordinary HTTP(S) downloads.
- [x] Report progress and transfer speed.
- [ ] Report estimated remaining time where available.
- [ ] Support user-controlled pause/resume.
- [x] Handle retries, timeouts, redirects, and partial files with validator-aware resume.
- [x] Add tests using a local test HTTP server.

## Phase 4 — Firefox integration

- [ ] Create a minimal WebExtension using documented APIs.
- [ ] Add a native-messaging host manifest and bridge.
- [ ] Validate all messages at the native boundary.
- [ ] Add a manual “send download to MediaGrab” flow before automatic detection.
- [ ] Document installation and troubleshooting on Fedora.

## Phase 5 — Media capture

- [ ] Detect candidate media URLs from supported browser signals.
- [ ] Distinguish direct files from HLS/DASH manifests where possible.
- [ ] Inspect available variants and expose quality choices only when known.
- [ ] Handle relevant request metadata and cookies without logging secrets.
- [ ] Add site-independent tests and clearly document unsupported cases.

## Phase 6 — Reliability and packaging

- [ ] Add structured diagnostics with secrets redacted.
- [ ] Test interruption, app restart, and queue recovery.
- [ ] Measure CPU and memory use during idle and active capture.
- [ ] Package for Fedora first; evaluate other distributions afterward.
- [ ] Consider Chromium support after the Firefox path is stable.

## Acceptance principles

- A feature is complete only when it works in a reproducible test and its limitations are documented.
- Avoid promising universal capture: sites differ, and DRM or other protections may prevent downloading.
- Keep the UI, browser integration, extraction logic, and transfer engine modular.
