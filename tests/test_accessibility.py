"""Regression checks for accessible names on icon-only GTK actions."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_icon_only_actions_expose_accessible_names() -> None:
    source = (ROOT / "app" / "mediagrab" / "main.py").read_text(encoding="utf-8")
    assert "widget.update_property([Gtk.AccessibleProperty.LABEL], [label])" in source
    assert 'set_accessible_label(self.progress, "Download progress")' in source
    assert 'set_accessible_label(self.search_entry, "Search downloads")' in source
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


def test_form_and_filter_controls_expose_accessible_names() -> None:
    source = (ROOT / "app" / "mediagrab" / "main.py").read_text(encoding="utf-8")
    for expression in (
        'set_accessible_label(search, "Search download history")',
        'set_accessible_label(status_filter, "Filter history by outcome")',
        'set_accessible_label(file_type_filter, "Filter history by file type")',
        'set_accessible_label(date_filter, "Filter history by date")',
        'set_accessible_label(size_filter, "Filter history by file size")',
        'set_accessible_label(domain_filter, "Filter history by source domain")',
        'set_accessible_label(level, "Logging verbosity")',
        'set_accessible_label(concurrency, "Maximum simultaneous downloads")',
        'set_accessible_label(entry, "Download URL")',
        'set_accessible_label(checksum_entry, "Optional checksum")',
        'set_accessible_label(dropdown, "Download quality")',
        'set_accessible_label(audio_dropdown, "Alternate audio track")',
        'set_accessible_label(subtitle_dropdown, "Subtitle track")',
    ):
        assert expression in source


def test_every_icon_only_button_has_an_explicit_accessible_name() -> None:
    source = (ROOT / "app" / "mediagrab" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    icon_buttons = set()
    labelled_buttons = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if ast.unparse(node.value.func) == "Gtk.Button.new_from_icon_name":
                for target in node.targets:
                    if isinstance(target, (ast.Name, ast.Attribute)):
                        icon_buttons.add(ast.unparse(target))
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "set_accessible_label" and node.args:
            labelled_buttons.add(ast.unparse(node.args[0]))
    assert icon_buttons
    assert icon_buttons <= labelled_buttons
