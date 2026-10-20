"""Formatting helpers for download progress and status display."""

from __future__ import annotations


def format_eta(seconds: float | None) -> str | None:
    if seconds is None or seconds < 0 or seconds != seconds or seconds == float("inf"):
        return None
    remaining = int(seconds)
    if remaining < 60:
        return f"{remaining}s remaining"
    minutes, seconds = divmod(remaining, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s remaining"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes:02d}m remaining"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h remaining"
