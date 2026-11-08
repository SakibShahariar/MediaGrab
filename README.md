# MediaGrab

A native Linux download manager with browser-to-desktop media capture, built with GTK4 and libadwaita.

> **Development status:** MediaGrab is under active development. The desktop queue, direct HTTP(S) downloads, browser handoff, and HLS/DASH inspection are implemented. Real-world browser and desktop validation is still in progress; see the [support matrix](docs/support-matrix.md).

## What it does

- **Manage downloads:** queue, pause/resume supported direct transfers, retry, cancel, recover interrupted work, and control concurrent downloads.
- **Capture from browsers:** Firefox and Chromium-family extensions can hand off links and scan the current tab. Optional background media detection requires explicit all-sites permission.
- **Inspect streams:** review HLS variants, alternate audio/subtitle playlists, and DASH representations before choosing a stream.
- **Download media:** direct HTTP(S) transfers run natively; HLS/DASH downloads use optional FFmpeg integration.
- **Keep track:** search and filter local download history, verify checksums, view progress and ETA, and receive optional desktop notifications.
- **Automate:** use the `mediagrab` command or the session-scoped D-Bus API to add URLs and control queue items.

## Browser integration

The browser extensions support manual link/page handoff, user-triggered tab scanning, and optional response observation. Detected candidates are reviewed in the browser or the app's inbox; **detection never starts a download automatically**.

Background observation is off by default and requires a separate all-sites HTTP(S) permission. The extensions do not read cookies, request bodies, or authorization headers. Private-window support follows the browser's own extension permission. See the [browser installation guide](docs/browser-native-host-installer.md).

## Quick use

Once MediaGrab is installed, the command-line client can send work to the running desktop application:

```sh
mediagrab --help
mediagrab --add-url 'https://example.test/video.mp4'
mediagrab --list
mediagrab --status
```

Queue IDs are positional and can change when items are removed; run `mediagrab --list` before controlling a specific item. The CLI and D-Bus interface use the same URL validation and queue-state checks.

To inspect a stream manifest without adding it to the queue:

```sh
mediagrab-inspect 'https://example.test/path/master.m3u8'
mediagrab-inspect 'https://example.test/path/manifest.mpd'
```

## Important limitations

- Not every website or protected stream is supported. MediaGrab does not bypass DRM or access controls.
- Pause/resume is supported for direct HTTP(S) downloads; FFmpeg-backed HLS/DASH transfers cannot currently be paused.
- Stream capture depends on the site's delivery method and may require authentication or site-specific behavior that MediaGrab does not provide.

## Development

The project is organized into the GTK application and download core (`app/`), browser extensions (`browser-extension/`), native messaging bridge (`native-host/`), documentation (`docs/`), and automated tests (`tests/`).

See [development setup and workflow](docs/development.md), [contributing guidelines](CONTRIBUTING.md), and the [support matrix](docs/support-matrix.md) for setup, testing, and validation details.

## Privacy and safety

Download history, queue data, settings, and diagnostics are stored locally. Diagnostic logs redact sensitive values and are bounded; no remote telemetry or automatic diagnostics upload is implemented. Browser response observation is opt-in, and candidate URLs remain in browser-session storage. See the browser guide and support matrix for the details and limitations.

MediaGrab also supports trusted Python site-extractor plugins through the `mediagrab.extractors` entry-point group. Plugins run with the user's permissions and are **not sandboxed**; install only plugins you trust. See the [plugin API documentation](docs/development.md#site-extractor-plugin-api).

## Roadmap

Current priorities include end-to-end validation in Firefox and Chromium, compatibility checks for Brave and Vivaldi, and Fedora packaging:

- [Browser end-to-end validation](https://github.com/SakibShahariar/MediaGrab/issues/14)
- [Brave and Vivaldi compatibility](https://github.com/SakibShahariar/MediaGrab/issues/12)
- [Fedora packaging](https://github.com/SakibShahariar/MediaGrab/issues/11)

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
