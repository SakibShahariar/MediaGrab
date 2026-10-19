# Browser Integration Research Notes

These notes record preliminary structural observations from a locally supplied IDM browser extension package. They are research notes, not a claim that MediaGrab has implemented equivalent behavior.

## Preliminary observations

- The inspected package uses a Manifest V2-style extension structure.
- Its files include background logic, content-script logic, document/page integration, capture UI, and localization resources.
- The content-script path appears to inspect media-related DOM elements and react to DOM changes.
- Background logic appears to observe network request/response events and coordinate messages, cookies, and a native host.
- Some initialization logic appears platform-dependent, so the extension package should not be assumed to work independently on Linux.
- The package contains multiple interacting paths; reading one script alone is not enough to understand the full capture lifecycle.

These observations are preliminary and need to be verified against actual call paths and runtime behavior before being treated as design requirements.

## Questions to investigate

1. What signals cause a candidate to be created?
2. How are candidates filtered, deduplicated, and updated?
3. Which message types connect content scripts, background logic, and the native host?
4. How are direct files distinguished from segmented streams?
5. When and how are cookies or request metadata passed to the downloader?
6. What is the user-visible behavior for multiple qualities, audio tracks, or unsupported media?
7. What happens when requests are short-lived, redirected, cross-origin, or authenticated?
8. Which behaviors depend on a companion desktop application?

## Research boundaries

- Do not commit the original extension package, extracted source, or proprietary assets.
- Do not copy proprietary implementation code into MediaGrab.
- Use this document to guide independent experiments and implementations based on public browser APIs.
- Record reproducible behavior and test cases, not assumptions about undocumented internals.
- Do not attempt to bypass DRM or access controls.
