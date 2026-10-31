# Fedora packaging status

MediaGrab targets Linux desktops and is being prepared for Fedora as the first packaged distribution.

## Desktop integration

The repository now contains:

- Desktop ID and application ID: `io.github.SakibShahariar.MediaGrab`.
- Desktop launcher: `data/io.github.SakibShahariar.MediaGrab.desktop`.
- Scalable application icon: `data/icons/hicolor/scalable/apps/io.github.SakibShahariar.MediaGrab.svg`.

The launcher starts the installed `mediagrab` entry point. The native-messaging registration remains a separate per-user step; see [Browser Native Host Installer](browser-native-host-installer.md).

## Runtime requirements

The Fedora package will need the system GTK stack and FFmpeg:

- Python 3.11 or newer.
- GTK 4.
- libadwaita.
- PyGObject / GObject introspection.
- FFmpeg (required for HLS/DASH stream-copy tasks; direct HTTP downloads use the native downloader).

The Python project currently has no third-party runtime dependencies declared in `pyproject.toml`; GTK bindings and FFmpeg are system dependencies.

## RPM status

An installable RPM specification is intentionally deferred. The project metadata currently declares `license = { text = "TBD" }` and there is no project license file. RPM and AppStream metadata must contain an accurate project license expression. The license must not be guessed or silently changed as part of packaging.

Once the project license is selected, the RPM can package the Python entry points, desktop file, icon, AppStream metadata, and native-host installer. The spec should be built and installed in a Fedora CI/container environment before the Fedora installation issue is closed.

## Flatpak evaluation

Flatpak is not a drop-in replacement for the RPM. The app needs network access, GTK/libadwaita, and FFmpeg. Browser native messaging is the difficult integration boundary: the browser runs outside the app sandbox, so a host executable and registration manifest must be installed where the host browser can access them. A Flatpak-only installation cannot assume that the browser can execute a binary inside the sandbox. A separate host-side installer or portal-based bridge would be required and needs independent validation.

For now, native RPM packaging is the first target; Flatpak remains an evaluation item rather than a claimed supported format.
