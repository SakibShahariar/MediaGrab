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
