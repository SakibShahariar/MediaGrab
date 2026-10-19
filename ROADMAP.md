# MediaGrab Roadmap

MediaGrab is in its planning stage. Milestones are ordered to validate the core download workflow before investing heavily in advanced media extraction.

## Phase 1 — Repository foundation

- [x] Document goals and planned architecture in README.
- [ ] Add architecture notes and development conventions.
- [ ] Establish a minimal Python project and test runner.
- [ ] Add CI for linting and tests.

## Phase 2 — Native desktop shell

- [ ] Build the initial GTK4/libadwaita application window.
- [ ] Define a download item model and queue states.
- [ ] Add empty, active, completed, failed, and paused queue views.
- [ ] Make cancellation and retry behavior explicit.
- [ ] Verify responsiveness with a large queue.

## Phase 3 — Download core

- [ ] Implement ordinary HTTP(S) downloads.
- [ ] Report progress, speed, and estimated remaining time where available.
- [ ] Support pause/resume when the server and transfer method permit it.
- [ ] Handle retries, timeouts, redirects, and partial files safely.
- [ ] Add tests using a local test HTTP server.

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
