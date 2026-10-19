# MediaGrab Architecture

## Components

### 1. Browser extensions (Firefox and Chromium family)

Firefox and Chromium-family extensions should provide the same core features: observe browser-visible download/media signals and present a user-controlled handoff to MediaGrab. Share common logic and the versioned message schema; keep browser-specific API adapters thin. Support Brave, Vivaldi, and other Chromium-derived browsers when their extension APIs and native-host registration are compatible. Avoid site-specific assumptions unless an adapter is justified by tests.

The extension should not try to implement the full download engine. Its role is detection, context gathering, and user interaction.

### 2. Native messaging host

A small local bridge registered with the browser. It accepts structured messages, validates their schema and size, and forwards permitted requests to MediaGrab.

Security requirements:
- Treat all browser messages as untrusted input.
- Validate URL schemes and reject malformed payloads.
- Never execute received strings as commands.
- Avoid logging cookies, authorization headers, or other secrets.
- Keep the message protocol versioned.

### 3. Capture engine

Responsible for turning a candidate into a useful download option. It will distinguish direct media files from manifests and progressively add support for formats that can be handled reliably.

The engine should return explicit results: detected format, available variants when known, required metadata, and a clear reason when a candidate cannot be handled.

### 4. Download core

Responsible for transfer lifecycle: queueing, progress, cancellation, retries, output paths, partial files, and recovery. It should be independently testable without the GUI or browser extension.

### 5. GTK4/libadwaita application

Responsible for the queue, download details, settings, notifications, and user decisions. Long-running work must not block the UI thread. UI code should consume core state rather than own transfer logic.

## Suggested data flow

1. A supported browser extension observes a candidate resource or the user chooses a browser download.
2. The extension sends a versioned message through native messaging.
3. The native host validates the message.
4. MediaGrab inspects the candidate and determines whether it is a direct file or a supported stream.
5. The UI presents available choices and any limitations.
6. The download core performs the transfer and emits state updates.
7. The UI displays progress and completion/failure details.

## Initial implementation order

Start with the download core and a small desktop queue. Define the shared native-messaging protocol, then provide manual browser-to-app handoff in Firefox and Chromium-family browsers before automatic media detection. This validates the end-to-end architecture while keeping browser-specific APIs and extraction logic separate and testable.

## Open design decisions

- Whether to use a subprocess or an in-process service boundary for the first version.
- Which HTTP transfer library best supports cancellation, streaming, and robust tests.
- How queue state should be persisted across restarts.
- How to represent HLS/DASH variants and associated audio tracks.
- How to package and register native messaging for Firefox and each Chromium-family browser on each target distribution.
