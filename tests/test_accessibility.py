"""Regression checks for accessible names on icon-only GTK actions."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_icon_only_actions_expose_accessible_names() -> None:
    source = (ROOT / "app" / "mediagrab" / "main.py").read_text(encoding="utf-8")
    assert "widget.update_property([Gtk.AccessibleProperty.LABEL], [label])" in source
    for widget in (
        "self.retry_button",
        "self.candidate_action_button",
        "self.dismiss_candidate_button",
        "self.pause_button",
        "self.cancel_button",
        "diagnostics_button",
        "destination_button",
        "add_button",
        "open_button",
    ):
        assert f"set_accessible_label({widget}," in source
