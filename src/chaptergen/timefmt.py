"""Timestamps. Internally everything is whole seconds (float for sub-second precision)."""

from __future__ import annotations

import re

_TS = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d+))?\s*$")


def parse_ts(text: str) -> float:
    """Parse "1:02:03", "62:03", "02:03", "2:03.5" or "00:02:03,500" into seconds."""
    m = _TS.match(str(text))
    if not m:
        raise ValueError(f"invalid timestamp {text!r}")
    hours, minutes, seconds, fraction = m.groups()
    value = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
    if int(seconds) > 59:
        raise ValueError(f"invalid timestamp {text!r}")
    if fraction:
        value += int(fraction) / 10 ** len(fraction)
    return float(value)


def fmt_ts(seconds: float, *, force_hours: bool = False) -> str:
    """Format like YouTube does: 0:00, 12:35, 1:02:03."""
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours or force_hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
