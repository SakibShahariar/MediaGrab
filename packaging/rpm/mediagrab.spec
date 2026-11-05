Name:           mediagrab
Version:        0.1.0
Release:        1%{?dist}
Summary:        Native Linux download manager with browser media capture
License:        GPL-3.0-or-later
URL:            https://github.com/SakibShahariar/MediaGrab
Source0:        https://github.com/SakibShahariar/MediaGrab/archive/refs/tags/v%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
BuildRequires:  python3dist(setuptools)
BuildRequires:  python3dist(pytest)
BuildRequires:  desktop-file-utils
BuildRequires:  appstream

Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Recommends:     ffmpeg-free

%description
MediaGrab is a GTK4/libadwaita download manager for Linux. It supports direct
HTTP(S) downloads, browser media capture, and optional FFmpeg-backed HLS/DASH
stream downloads.

%prep
%autosetup -n MediaGrab-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files mediagrab

install -Dpm 0644 data/io.github.SakibShahariar.MediaGrab.desktop \
    %{buildroot}%{_datadir}/applications/io.github.SakibShahariar.MediaGrab.desktop
install -Dpm 0644 data/icons/hicolor/scalable/apps/io.github.SakibShahariar.MediaGrab.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.SakibShahariar.MediaGrab.svg
install -Dpm 0644 data/io.github.SakibShahariar.MediaGrab.metainfo.xml \
    %{buildroot}%{_datadir}/metainfo/io.github.SakibShahariar.MediaGrab.metainfo.xml
install -Dpm 0644 scripts/install_native_host.py \
    %{buildroot}%{_datadir}/mediagrab/install_native_host.py

%check
desktop-file-validate data/io.github.SakibShahariar.MediaGrab.desktop
appstreamcli validate --no-net data/io.github.SakibShahariar.MediaGrab.metainfo.xml
PYTHONPATH=app python3 -m pytest -q

%files -f %{pyproject_files}
%license LICENSE
%doc README.md docs/fedora-packaging.md
%{_datadir}/applications/io.github.SakibShahariar.MediaGrab.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.SakibShahariar.MediaGrab.svg
%{_datadir}/metainfo/io.github.SakibShahariar.MediaGrab.metainfo.xml
%{_datadir}/mediagrab/install_native_host.py
