from __future__ import annotations

import configparser
import tomllib
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def test_project_rpm_and_appstream_license_expressions_match() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    spec = (ROOT / "packaging/rpm/mediagrab.spec").read_text(encoding="utf-8")
    metadata = ElementTree.parse(ROOT / "data/io.github.SakibShahariar.MediaGrab.metainfo.xml").getroot()

    license_id = project["project"]["license"]
    assert license_id == "GPL-3.0-or-later"
    assert f"License:        {license_id}" in spec
    assert metadata.findtext("project_license") == license_id


def test_desktop_entry_matches_appstream_component_id() -> None:
    desktop = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    desktop.optionxform = str
    desktop.read(ROOT / "data/io.github.SakibShahariar.MediaGrab.desktop", encoding="utf-8")
    metadata = ElementTree.parse(ROOT / "data/io.github.SakibShahariar.MediaGrab.metainfo.xml").getroot()

    desktop_id = "io.github.SakibShahariar.MediaGrab.desktop"
    assert desktop["Desktop Entry"]["Icon"] == desktop_id.removesuffix(".desktop")
    assert metadata.findtext("id") == desktop_id.removesuffix(".desktop")
    assert metadata.findtext("launchable") == desktop_id


def test_rpm_spec_packages_every_console_entrypoint_and_native_host_installer() -> None:
    spec = (ROOT / "packaging/rpm/mediagrab.spec").read_text(encoding="utf-8")
    for command in ("mediagrab", "mediagrab-inspect", "mediagrab-native-host"):
        assert f"%{{_bindir}}/{command}" in spec
    assert "%{_datadir}/mediagrab/install_native_host.py" in spec
    assert (ROOT / "scripts/install_native_host.py").is_file()


def test_rpm_source_archive_name_matches_fedora_workflow_and_docs() -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    spec = (ROOT / "packaging/rpm/mediagrab.spec").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/fedora-rpm.yml").read_text(encoding="utf-8")
    docs = (ROOT / "docs/fedora-packaging.md").read_text(encoding="utf-8")

    assert "refs/tags/v%{version}.tar.gz" in spec
    assert f"SOURCES/v{version}.tar.gz" in workflow
    assert f"SOURCES/v{version}.tar.gz" in docs
