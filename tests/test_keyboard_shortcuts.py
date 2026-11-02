"""Tests for stable, non-conflicting core keyboard shortcut bindings."""

from mediagrab.shortcuts import SHORTCUTS


def test_core_shortcuts_cover_add_search_and_history() -> None:
    assert SHORTCUTS == {
        "add-download": "<Control>n",
        "focus-search": "<Control>f",
        "open-history": "<Control><Shift>h",
    }


def test_shortcut_accelerators_are_unique() -> None:
    assert len(SHORTCUTS.values()) == len(set(SHORTCUTS.values()))
