"""Timestamped transcripts: loading existing captions and turning them into prompt text."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .timefmt import fmt_ts, parse_ts


@dataclass
class Segment:
    """A stretch of speech: start time in seconds and what was said."""

    start: float
    text: str
    end: float | None = None


@dataclass
class Transcript:
    segments: list[Segment]
    duration: float  # seconds; end of the last segment if not known otherwise

    def as_prompt_text(self) -> str:
        """One line per segment, "[MM:SS] text", which the model can cite back."""
        force_hours = self.duration >= 3600
        return "\n".join(f"[{fmt_ts(s.start, force_hours=force_hours)}] {s.text}" for s in self.segments)

    def text_between(self, start: float, end: float) -> str:
        return " ".join(s.text for s in self.segments if start <= s.start < end)

    def to_dict(self) -> dict:
        return {"duration": self.duration, "segments": [asdict(s) for s in self.segments]}

    @classmethod
    def from_segments(cls, segments: list[Segment], duration: float | None = None) -> "Transcript":
        segments = sorted((s for s in segments if s.text.strip()), key=lambda s: s.start)
        if not segments:
            raise ValueError("the transcript is empty")
        last = segments[-1]
        known_end = max((s.end or s.start) for s in segments)
        guess = known_end if last.end else last.start + 5
        return cls(segments=segments, duration=max(duration or 0, guess))


_CUE_TIME = re.compile(r"(\S+)\s*-->\s*(\S+)")
_TAGS = re.compile(r"<[^>]+>|\{\\[^}]*\}")
TIMESTAMPED_LINE = re.compile(r"^\s*[\[(]?((?:\d+:)?\d{1,2}:\d{2}(?:[.,]\d+)?)[\])]?\s*[-–:]?\s*(.+)$")


def load_transcript(path: str | Path) -> Transcript:
    """Load captions you already have: .srt, .vtt, .json (from `--save-transcript`),
    or a .txt with one "[MM:SS] text" / "MM:SS text" line per segment."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(text)
        return Transcript.from_segments([Segment(**s) for s in data["segments"]], data.get("duration"))
    if suffix in (".srt", ".vtt"):
        return Transcript.from_segments(_parse_cues(text))
    return Transcript.from_segments(_parse_timestamped_lines(text))


def _parse_cues(text: str) -> list[Segment]:
    segments: list[Segment] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = [line for line in block.strip().split("\n") if line.strip()]
        for i, line in enumerate(lines):
            m = _CUE_TIME.search(line)
            if not m:
                continue
            body = " ".join(_TAGS.sub("", t).strip() for t in lines[i + 1 :]).strip()
            if body:
                start = _flex_ts(m.group(1))
                end = _flex_ts(m.group(2))
                segments.append(Segment(start=start, end=end, text=body))
            break
    if not segments:
        raise ValueError("no subtitles found in the file")
    return _merge_short(segments)


def _flex_ts(value: str) -> float:
    # SRT/VTT allow "00:01:02,345" and "01:02.345"; parse_ts handles both.
    return parse_ts(value)


def _parse_timestamped_lines(text: str) -> list[Segment]:
    segments = []
    for line in text.splitlines():
        m = TIMESTAMPED_LINE.match(line)
        if m:
            segments.append(Segment(start=parse_ts(m.group(1)), text=m.group(2).strip()))
    if not segments:
        raise ValueError('no timestamped lines found (expected lines like "[01:23] text")')
    return segments


def _merge_short(segments: list[Segment], min_len: float = 4.0) -> list[Segment]:
    """Captions are often 1-2 second fragments; join them into ~sentence-sized segments
    so the prompt is shorter and boundaries land on whole thoughts."""
    merged: list[Segment] = []
    for seg in segments:
        prev = merged[-1] if merged else None
        if prev and (seg.start - prev.start) < min_len and not prev.text.endswith((".", "?", "!", "।")):
            prev.text = f"{prev.text} {seg.text}"
            prev.end = seg.end
        else:
            merged.append(Segment(start=seg.start, end=seg.end, text=seg.text))
    return merged
