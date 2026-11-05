# MediaGrab Support Matrix

This matrix describes behavior implemented and covered by the repository's current tests. It is not a promise that every URL or streaming service is supported.

## Media input and transfer

| Input | Detection and inspection | Download behavior | Important limits |
|---|---|---|---|
| Direct HTTP(S) file | Classified from a recognized path extension or response MIME type. Unknown HTTP(S) URLs are still eligible for the generic direct-download path. | Native HTTP downloader; partial files, validator-aware range resume, pause, cancellation, safe output names, and atomic finalization. | Resume depends on server range and validator behavior. Unknown URLs may not be downloadable files. |
| HLS master playlist | Parses declared variants, bandwidth, resolution, codecs, audio groups, subtitle groups, and external audio/subtitle renditions. | FFmpeg stream-copy to MKV. A selected HLS variant can be queued; selected external audio/subtitle playlists can be passed as separate inputs. | Manifest declarations do not guarantee playability. Embedded/default tracks remain controlled by FFmpeg. No DRM bypass. Real-world site coverage is not yet established. |
| HLS media playlist | Recognizes the manifest and can pass it to FFmpeg. | FFmpeg handles the playlist as the stream input. | A media playlist does not declare a master variant list. Live/VOD edge cases still need real-world sample validation. |
| DASH MPD | Extracts representation IDs, bandwidth, dimensions, MIME type, codecs, and explicit BaseURL values. Inherited MIME/codecs are supported. | The MPD URL can be passed to FFmpeg as a stream input. | The parser's regression tests cover nested BaseURL inheritance, SegmentBase, SegmentList, SegmentTemplate/SegmentTimeline, and the rule that segmented resources are not misreported as direct file URLs. Dynamic MPD declarations (`availabilityStartTime`, `timeShiftBufferDepth`, `minimumUpdatePeriod`, and `suggestedPresentationDelay`) are preserved as metadata. The inspector does not calculate live segment availability, expand initialization/media templates into requests, or implement per-representation segmented downloading; these remain unsupported. |
| Other MIME types or URLs | Classified as unknown unless a supported media path or MIME type is recognized. | Unknown HTTP(S) URLs use the generic direct-download path. | This fallback does not imply that the resource is media or that the server allows downloading it. |

## Browser integration

| Capability | Current behavior | Limitations |
|---|---|---|
| Firefox | Manual link/page context-menu handoff and popup scan. | Temporary add-on installation requires reloading after browser restart during development. |
| Chromium-family | Shared extension code supports Chromium, Chrome, Brave, Vivaldi, and Microsoft Edge extension APIs where compatible. | Native host registration paths are documented for native Linux packages; Edge has a tested per-user path, Brave Flatpak has not been validated, and other custom Chromium profiles can use `--config-root`. |
| Current-tab scan | User clicks **Scan this tab**; the popup inspects page-visible resource timing entries, media elements, subtitle tracks, and media-looking links. | Blob URLs, opaque requests, and protected resources may not be usable. |
| Background observation | Optional opt-in `webRequest.onHeadersReceived` observer classifies response Content-Type and URL, deduplicates per tab/URL, and shows candidates in the popup. | Off by default; requires optional access to all HTTP(S) sites to observe cross-origin CDNs. Candidate URLs live in `storage.session` and are cleared on tab navigation/close, permission revocation, or browser exit. Request headers and bodies are not read. |
| Native handoff | Context-menu actions use `add-url` for explicit immediate downloads. Popup candidates use `add-candidate` to create a persisted **Detected** row in the app; the user can inspect/download or dismiss it. | Actual browser-to-desktop runtime validation is still pending for installed browser builds. |
| Private/incognito windows | The same page scan, optional background response observation, and context-menu handoff are available when the user allows the extension to run in private windows through the browser's native extension settings. | Browser permission is required; MediaGrab adds no separate private-window toggle. Real-browser validation is pending. |
| Request context | Signed query parameters are preserved for legitimate downloads. | Browser cookies and authorization headers are not collected or stored. Authenticated streams may fail. |

## Security and unsupported content

- Only HTTP(S) URLs are accepted by the native host and transfer engines; embedded username/password credentials are rejected.
- Query strings may contain signed access tokens. UI labels and inspector output redact query/fragment values; the queue still retains the original URL so retries work.
- MediaGrab does not bypass DRM or other access controls.
- Browser capture does not transfer cookies, authorization headers, or other authenticated request context. Background observation reads response Content-Type only and does not inspect request headers or response bodies.
- Vivaldi Snap and Flatpak builds do not expose the Native Messaging API. Brave Flatpak registration is not validated.
- Private/incognito availability is controlled by the browser's native extension permission. When enabled, MediaGrab can observe and hand off the same candidate URLs as in regular windows; observed candidates remain in browser-session storage. Browser cookies and authorization headers are not collected or transferred.

## Automated test evidence

The current suite is site-independent and uses fixtures, local HTTP servers, and mocked FFmpeg processes rather than live third-party services:

- `tests/test_capture.py`: URL/MIME classification, synthetic HLS variants and renditions, DASH representation metadata, malformed manifests, and credential rejection.
- `tests/test_hls_real_world_fixtures.py`: parser regression checks against Apache-2.0-licensed real-world master playlists with multiple variants, external audio, and subtitles; fixture provenance is recorded in `tests/fixtures/hls/README.md`.
- `tests/test_media_stream_integration.py`: optional local HTTP HLS segment download, FFmpeg remux, output finalization, and decode verification when FFmpeg is installed.
- `tests/test_media_inspector.py`: local-server manifest fetches, response-size and timeout limits, HTTP errors, and redirect validation.
- `tests/test_task_factory.py`: routing HLS/DASH manifests to the stream adapter and direct/unknown URLs to the HTTP downloader.
- `tests/test_media_stream.py`: FFmpeg command construction, stream finalization, cancellation, error handling, and optional external tracks using a fake process.
- `tests/test_dash_representation_selection.py` and `tests/test_dash_media_stream_integration.py`: single-period representation ordering, FFmpeg stream mapping, and an optional generated DASH SegmentTemplate download that verifies the selected output resolution.
- `tests/test_downloader.py`: local HTTP transfers, resume behavior, pause/cancel, malformed responses, and safe finalization.
- `tests/test_native_host.py` and `tests/test_browser_popup.py`: native-messaging validation and static browser-extension contracts.
- `tests/browser-extension-background.test.cjs`: Node-based Firefox/Chromium background API harness covering response classification, per-tab deduplication, navigation cleanup, permission revocation, and context-menu handoff.

These tests establish core behavior in controlled environments. Real-world HLS master-playlist metadata is covered by retained upstream fixtures; the FFmpeg end-to-end test uses a generated local HLS source, not a third-party live/VOD segment origin. It does not establish compatibility with every encrypted, live, or site-specific stream. Real-world segment-origin validation and browser/GTK end-to-end testing remain outstanding. See the open validation work for [real-world HLS samples](https://github.com/SakibShahariar/MediaGrab/issues/3), [advanced DASH cases](https://github.com/SakibShahariar/MediaGrab/issues/4), and [browser handoff testing](https://github.com/SakibShahariar/MediaGrab/issues/14).


## Diagnostics

| Capability | Current behavior | Limitations |
|---|---|---|
| Structured logging | JSONL lifecycle events for downloads, retries, manifest inspection, and browser candidate review; secrets and personal paths are redacted. | No per-chunk progress logging; diagnostics are local to the user account. |
| Storage and export | Rotating 1 MiB log plus two backups, owner-only file permissions, and a copy-to-clipboard action that redacts again. | Clipboard export is user-triggered; no automatic upload or remote telemetry. |
| Verbosity | ERROR, WARNING, INFO, and DEBUG can be selected in the app and persisted in settings. | DEBUG may contain more operational detail, but sensitive fields still pass through redaction. |
