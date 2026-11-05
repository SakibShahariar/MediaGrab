# Fedora packaging

Fedora is the first target for native Linux packaging. The repository now contains an RPM spec and AppStream metadata; the Fedora CI workflow builds the RPM in a Fedora container.

## Package contents

- Python application and entry points: `mediagrab`, `mediagrab-native-host`, and `mediagrab-inspect`
- GNOME desktop launcher and scalable application icon
- AppStream metadata
- Per-user browser native-messaging installer
- GPL-3.0-or-later license

The RPM depends on GTK 4, libadwaita, and PyGObject. FFmpeg is recommended for HLS/DASH stream-copy downloads; Fedora's `ffmpeg-free` package may not support every codec or container combination.

## Build the RPM

The spec expects a source archive matching the `v0.1.0` tag:

```fish
mkdir -p ~/rpmbuild/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
tar --exclude=.git --transform='s,^,MediaGrab-0.1.0/,' \
  -czf ~/rpmbuild/SOURCES/mediagrab-0.1.0.tar.gz .
cp packaging/rpm/mediagrab.spec ~/rpmbuild/SPECS/
rpmbuild -ba --define "_topdir $HOME/rpmbuild" ~/rpmbuild/SPECS/mediagrab.spec
```

Install the generated noarch RPM with DNF. The CI workflow performs the same build and validates the desktop entry and AppStream metadata. A successful container build is not a substitute for installation and launch testing on a real Fedora GNOME session.

## Browser native-messaging registration

Registration remains per-user. After installing the RPM, run the included installer:

```fish
python3 /usr/share/mediagrab/install_native_host.py --browser firefox
python3 /usr/share/mediagrab/install_native_host.py --browser chromium --extension-id YOUR_REAL_EXTENSION_ID
```

Use the actual extension ID shown by the installed Chromium-family browser. The installer writes the registration under the user's browser configuration directory; it does not enable private-window permissions.

## Flatpak

Flatpak is not currently packaged. Browser native messaging needs a host executable and registration manifest visible to the unsandboxed browser, so a Flatpak-only install cannot assume that the browser can execute a binary inside the app sandbox. Treat Flatpak as a separate integration project rather than a supported installation method.
