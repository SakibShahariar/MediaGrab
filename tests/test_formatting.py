"""Tests for progress ETA formatting."""

import pytest

from mediagrab.formatting import format_eta


@pytest.mark.parametrize(("seconds", "expected"), [(0, "0s remaining"), (59.9, "59s remaining"), (60, "1m 00s remaining"), (125, "2m 05s remaining"), (3600, "1h 00m remaining"), (90061, "1d 1h remaining")])
def test_format_eta(seconds: float, expected: str) -> None:
    assert format_eta(seconds) == expected


@pytest.mark.parametrize("seconds", [None, -1, float("nan"), float("inf")])
def test_unavailable_eta_returns_none(seconds: float | None) -> None:
    assert format_eta(seconds) is None
