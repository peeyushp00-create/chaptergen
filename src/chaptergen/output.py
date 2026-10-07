"""Turning a Result into text people paste somewhere."""

from __future__ import annotations

import json

from .pipeline import Result
from .timefmt import fmt_ts


def _times(result: Result):
    force = result.transcript.duration >= 3600
    return lambda t: fmt_ts(t, force_hours=force)


def youtube_chapters(result: Result) -> str:
    """Exactly what goes in a YouTube description."""
    ts = _times(result)
    return "\n".join(f"{ts(c.start)} {c.title}" for c in result.chapters)


def render_text(result: Result) -> str:
    ts = _times(result)
    out = ["CHAPTERS (paste into your YouTube description)", youtube_chapters(result), ""]
    if result.summary:
        out += ["SUMMARY", result.summary, ""]
    if result.titles:
        out += ["TITLE IDEAS"] + [f"{i}. {t}" for i, t in enumerate(result.titles, 1)] + [""]
    if result.clips:
        out.append("CLIP IDEAS (for Shorts / Reels)")
        for c in result.clips:
            why = f"  ({c.reason})" if c.reason else ""
            out.append(f'{ts(c.start)} - {ts(c.end)}  "{c.hook}"{why}')
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_markdown(result: Result) -> str:
    ts = _times(result)
    out = ["## Chapters", "", "```", youtube_chapters(result), "```", ""]
    if result.summary:
        out += ["## Summary", "", result.summary, ""]
    if result.titles:
        out += ["## Title ideas", ""] + [f"{i}. {t}" for i, t in enumerate(result.titles, 1)] + [""]
    if result.clips:
        out += ["## Clip ideas", "", "| Time | Hook | Why |", "| --- | --- | --- |"]
        for c in result.clips:
            hook = c.hook.replace("|", "\\|")
            out.append(f"| {ts(c.start)}–{ts(c.end)} | {hook} | {c.reason.replace('|', '/')} |")
        out.append("")
    return "\n".join(out)


def render_json(result: Result) -> str:
    return json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n"


RENDERERS = {"text": render_text, "md": render_markdown, "json": render_json}
