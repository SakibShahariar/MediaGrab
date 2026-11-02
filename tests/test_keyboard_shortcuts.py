"""Tests for stable, non-conflicting core keyboard shortcut bindings."""

from mediagrab.shortcuts import COMMAND_PALETTE_ACTIONS, SHORTCUTS


def test_core_shortcuts_cover_add_search_history_and_diagnostics() -> None:
    assert SHORTCUTS == {
        "add-download": "<Control>n",
        "focus-search": "<Control>f",
        "open-history": "<Control><Shift>h",
        "open-command-palette": "<Control>k",
        "open-diagnostics": "<Control><Shift>d",
        "toggle-focused-download": "<Control><Shift>p",
        "retry-focused-download": "<Control><Shift>r",
        "cancel-focused-download": "<Control><Shift>x",
        "open-focused-file": "<Control><Shift>o",
    }


def test_shortcut_accelerators_are_unique() -> None:
    assert len(SHORTCUTS.values()) == len(set(SHORTCUTS.values()))


def test_command_palette_exposes_core_actions() -> None:
    assert COMMAND_PALETTE_ACTIONS == (
        ("Add download", "add-download"),
        ("Search downloads", "focus-search"),
        ("Open history", "open-history"),
        ("Open diagnostics", "open-diagnostics"),
        ("Pause or resume focused download", "toggle-focused-download"),
        ("Retry focused download", "retry-focused-download"),
        ("Cancel focused download", "cancel-focused-download"),
        ("Open focused completed file", "open-focused-file"),
    )
