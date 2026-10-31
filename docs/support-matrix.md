# MediaGrab Support Matrix

This matrix describes behavior implemented and covered by the repository's current tests. It is not a promise that every URL or streaming service is supported.

## Media input and transfer

| Input | Detection and inspection | Download behavior | Important limits |
|---|---|---|---|
| Direct HTTP(S) file | Classified from a recognized path extension or response MIME type. Unknown HTTP(S) URLs are still eligible for the generic direct-download path. | Native HTTP downloader; partial files, validator-aware range resume, pause, cancellation, safe output names, and atomic finalization. | Resume depends on server range and validator behavior. Unknown URLs may not be downloadable files. |
| HLS master playlist | Parses declared variants, bandwidth, resolution, codecs, audio groups, subtitle groups, and external audio/subtitle renditions. | FFmpeg stream-copy to MKV. A selected HLS variant can be queued; selected external audio/subtitle playlists can be passed as separate inputs. | Manifest declarations do not guarantee playability. Embedded/default tracks remain controlled by FFmpeg. No DRM bypass. Real-world site coverage is not yet established. |
| HLS media playlist | Recognizes the manifest and can pass it to FFmpeg. | FFmpeg handles the playlist as the stream input. | A media playlist does not declare a master variant list. Live/VOD edge cases still need real-world sample validation. |
| DASH MPD | Extracts representation IDs, bandwidth, dimensions, MIME type, codecs, and explicit BaseURL values. Inherited MIME/codecs are supported. | The MPD URL can be passed to FFmpeg as a stream input. | The inspector does not resolve SegmentTemplate, SegmentTimeline, initialization templates, or availability windows into selectable representation URLs. Per-representation selection is not implemented. |
| Other MIME types or URLs | Classified as unknown unless a supported media path or MIME type is recognized. | Unknown HTTP(S) URLs use the generic direct-download path. | This fallback does not imply that the resource is media or that the server allows downloading it. |

## Browser integration

| Capability | Current behavior | Limitations |
|---|---|---|
| Firefox | Manual link/page context-menu handoff and popup scan. | Temporary add-on installation requires reloading after browser restart during development. |
| Chromium-family | Shared extension code supports Chromium, Chrome, Brave, and Vivaldi extension APIs where compatible. | Native host registration paths are documented for native Linux packages; Brave Flatpak has not been validated. |
| Current-tab scan | User clicks **Scan this tab**; the popup inspects page-visible resource timing entries, media elements, subtitle tracks, and media-looking links. | Blob URLs, opaque requests, and protected resources may not be usable. |
| Background observation | Optional opt-in `webRequest.onHeadersReceived` observer classifies response Content-Type and URL, deduplicates per tab/URL, and shows candidates in the popup. | Off by default; requires optional access to all HTTP(S) sites to observe cross-origin CDNs. Candidate URLs live in `storage.session` and are cleared on tab navigation/close, permission revocation, or browser exit. Request headers and bodies are not read. |
| Native handoff | Versioned native-messaging message accepts validated HTTP(S) URLs without embedded credentials. | Actual browser-to-desktop runtime validation is still pending for installed browser builds. |
| Request context | Signed query parameters are preserved for legitimate downloads. | Browser cookies and authorization headers are not collected or stored. Authenticated streams may fail. |

## Security and unsupported content

- Only HTTP(S) URLs are accepted by the native host and transfer engines; embedded username/password credentials are rejected.
- Query strings may contain signed access tokens. UI labels and inspector output redact query/fragment values; the queue still retains the original URL so retries work.
- MediaGrab does not bypass DRM or other access controls.
- Browser capture does not transfer cookies, authorization headers, or other authenticated request context. Background observation reads response Content-Type only and does not inspect request headers or response bodies.
- Vivaldi Snap and Flatpak builds do not expose the Native Messaging API. Brave Flatpak registration is not validated.
- Private-window capture behavior has not been implemented as a separately configurable feature.

## Automated test evidence

The current suite is site-independent and uses fixtures, local HTTP servers, and mocked FFmpeg processes rather than live third-party services:

- `tests/test_capture.py`: URL/MIME classification, HLS variants and renditions, DASH representation metadata, malformed manifests, and credential rejection.
- `tests/test_media_inspector.py`: local-server manifest fetches, response-size and timeout limits, HTTP errors, and redirect validation.
- `tests/test_task_factory.py`: routing HLS/DASH manifests to the stream adapter and direct/unknown URLs to the HTTP downloader.
- `tests/test_media_stream.py`: FFmpeg command construction, stream finalization, cancellation, error handling, and optional external tracks using a fake process.
- `tests/test_downloader.py`: local HTTP transfers, resume behavior, pause/cancel, malformed responses, and safe finalization.
- `tests/test_native_host.py` and `tests/test_browser_popup.py`: native-messaging validation and static browser-extension contracts.

These tests establish core behavior in controlled environments. They do not replace real-world HLS/DASH sample validation or browser/GTK end-to-end testing. See the open validation work for [real-world HLS samples](https://github.com/SakibShahariar/MediaGrab/issues/3), [advanced DASH cases](https://github.com/SakibShahariar/MediaGrab/issues/4), and [browser handoff testing](https://github.com/SakibShahariar/MediaGrab/issues/14).
