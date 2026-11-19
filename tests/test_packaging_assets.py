from __future__ import annotations

import configparser
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ID = "io.github.SakibShahariar.MediaGrab"


def test_desktop_entry_has_valid_application_identity_and_launcher() -> None:
    path = ROOT / "data" / f"{APP_ID}.desktop"
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    with path.open(encoding="utf-8") as stream:
        parser.read_file(stream)

    entry = parser["Desktop Entry"]
    assert entry["Type"] == "Application"
    assert entry["Name"] == "MediaGrab"
    assert entry["Exec"] == "mediagrab"
    assert entry["Icon"] == APP_ID
    assert entry["Terminal"] == "false"
    assert "AudioVideo;" in entry["Categories"]


def test_scalable_app_icon_is_well_formed_svg() -> None:
    path = ROOT / "data" / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"
    root = ET.parse(path).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.attrib["viewBox"] == "0 0 128 128"
    assert "linearGradient" in path.read_text(encoding="utf-8")


def test_symbolic_and_monochrome_app_icons_follow_icon_conventions() -> None:
    icons = ROOT / "data" / "icons" / "hicolor"
    symbolic = icons / "symbolic" / "apps" / f"{APP_ID}-symbolic.svg"
    mono = icons / "scalable" / "apps" / f"{APP_ID}-mono.svg"

    symbolic_root = ET.parse(symbolic).getroot()
    assert symbolic_root.tag == "{http://www.w3.org/2000/svg}svg"
    assert symbolic_root.attrib["viewBox"] == "0 0 16 16"
    assert symbolic_root.attrib["width"] == "16"
    assert symbolic_root.attrib["height"] == "16"
    assert "#bebebe" in symbolic.read_text(encoding="utf-8")

    mono_root = ET.parse(mono).getroot()
    assert mono_root.tag == "{http://www.w3.org/2000/svg}svg"
    assert mono_root.attrib["viewBox"] == "0 0 128 128"
    mono_text = mono.read_text(encoding="utf-8")
    assert "linearGradient" not in mono_text
    assert 'fill="#bebebe"' in mono_text
