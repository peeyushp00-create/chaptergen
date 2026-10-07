"""From a recording (or existing captions) to chapters, summary, titles and clips."""

from __future__ import annotations

import bisect
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import prompts
from .llm import LLM, ChaptergenError
from .media import check_media, prepare_audio, probe_duration
from .rules import Chapter, Clip, RepairReport, repair_chapters, repair_clips
from .timefmt import fmt_ts, parse_ts
from .transcript import Segment, Transcript

# Transcripts longer than this (characters) are processed in overlapping windows.
CHUNK_CHARS = 120_000
WINDOW_SECONDS = 40 * 60
OVERLAP_SECONDS = 2 * 60


@dataclass
class Options:
    kind: str = "video"  # "video" or "podcast", used in the prompt
    titles: int = 3
    clips: int = 3


@dataclass
class Result:
    chapters: list[Chapter]
    summary: str
    titles: list[str]
    clips: list[Clip]
    transcript: Transcript
    report: RepairReport = field(default_factory=RepairReport)

    def to_dict(self) -> dict:
        return {
            "duration": self.transcript.duration,
            "chapters": [{"start": c.start, "time": fmt_ts(c.start), "title": c.title} for c in self.chapters],
            "summary": self.summary,
            "titles": self.titles,
            "clips": [
                {"start": c.start, "end": c.end, "time": f"{fmt_ts(c.start)}-{fmt_ts(c.end)}", "hook": c.hook,
                 "reason": c.reason}
                for c in self.clips
            ],
            "fixes": self.report.fixes,
            "warnings": self.report.warnings,
        }


# ------------------------------------------------------------ transcription


def transcribe(llm: LLM, media: Path) -> Transcript:
    """Speech to timestamped segments using the model's audio understanding."""
    check_media(media)
    duration = probe_duration(media)
    upload, is_temp = prepare_audio(media)
    try:
        data = llm.generate_json(
            prompt=prompts.TRANSCRIBE_PROMPT,
            schema=prompts.TRANSCRIPT_SCHEMA,
            system=prompts.TRANSCRIBE_SYSTEM,
            media=upload,
        )
    finally:
        if is_temp:
            upload.unlink(missing_ok=True)
    segments = []
    for item in data.get("segments", []):
        try:
            segments.append(Segment(start=parse_ts(item["start"]), text=str(item["text"]).strip()))
        except (KeyError, ValueError):
            continue  # skip a malformed segment rather than failing the whole run
    if not segments:
        raise ChaptergenError("no speech was found in this recording")
    return Transcript.from_segments(segments, duration)


# ------------------------------------------------------------ chapters


def _spacing(duration: float) -> str:
    minutes = duration / 60
    if minutes <= 12:
        return "1-2 minutes"
    if minutes <= 60:
        return "3-6 minutes"
    return "6-12 minutes"


def _duration_text(duration: float) -> str:
    minutes = round(duration / 60)
    return f"{minutes} minutes" if minutes < 120 else f"{duration / 3600:.1f} hours"


class _Snapper:
    """Moves a model-given time onto the nearest real segment start."""

    def __init__(self, transcript: Transcript):
        self.starts = [s.start for s in transcript.segments]
        self.moved = 0

    def __call__(self, t: float) -> float:
        i = bisect.bisect_left(self.starts, t)
        candidates = [self.starts[j] for j in (i - 1, i) if 0 <= j < len(self.starts)]
        snapped = min(candidates, key=lambda s: abs(s - t)) if candidates else t
        if snapped != t:
            self.moved += 1
        return snapped


def _parse_chapters(items: list[dict], snap: _Snapper) -> list[Chapter]:
    chapters = []
    for item in items:
        try:
            chapters.append(Chapter(start=snap(parse_ts(item["start"])), title=str(item["title"])))
        except (KeyError, ValueError):
            continue
    return chapters


def _parse_clips(items: list[dict], snap: _Snapper) -> list[Clip]:
    clips = []
    for item in items:
        try:
            clips.append(Clip(
                start=snap(parse_ts(item["start"])), end=parse_ts(item["end"]),
                hook=str(item.get("hook", "")), reason=str(item.get("reason", "")),
            ))
        except (KeyError, ValueError):
            continue
    return clips


def _windows(transcript: Transcript) -> list[Transcript]:
    windows, start = [], 0.0
    while start < transcript.duration:
        end = start + WINDOW_SECONDS
        segs = [s for s in transcript.segments if start <= s.start < end + OVERLAP_SECONDS]
        if segs:
            windows.append(Transcript(segments=segs, duration=transcript.duration))
        start = end
    return windows


def generate(llm: LLM, transcript: Transcript, options: Options | None = None) -> Result:
    """Chapters, summary, titles and clips for a transcript, checked against YouTube's rules."""
    opts = options or Options()
    duration = transcript.duration
    fill = {
        "kind": opts.kind, "duration": _duration_text(duration), "spacing": _spacing(duration),
        "n_titles": opts.titles, "n_clips": opts.clips,
    }

    if len(transcript.as_prompt_text()) <= CHUNK_CHARS:
        data = llm.generate_json(
            prompt=prompts.CHAPTERS_PROMPT.format(transcript=transcript.as_prompt_text(), **fill),
            schema=prompts.CHAPTERS_SCHEMA,
            system=prompts.CHAPTERS_SYSTEM,
        )
    else:
        # Long recordings: chapter each window, then let the model merge the candidates.
        candidates: dict[str, list] = {"chapters": [], "clips": []}
        for window in _windows(transcript):
            part = llm.generate_json(
                prompt=prompts.CHAPTERS_PROMPT.format(transcript=window.as_prompt_text(), **fill),
                schema=prompts.CHAPTERS_SCHEMA,
                system=prompts.CHAPTERS_SYSTEM,
            )
            candidates["chapters"].extend(part.get("chapters", []))
            candidates["clips"].extend(part.get("clips", []))
        data = llm.generate_json(
            prompt=prompts.MERGE_PROMPT.format(candidates=json.dumps(candidates, ensure_ascii=False), **fill),
            schema=prompts.CHAPTERS_SCHEMA,
            system=prompts.CHAPTERS_SYSTEM,
        )

    snap = _Snapper(transcript)
    chapters, report = repair_chapters(_parse_chapters(data.get("chapters", []), snap), duration)
    if snap.moved:
        report.fixes.insert(0, f"moved {snap.moved} chapter time(s) to the nearest sentence start in the transcript")
    clips = repair_clips(_parse_clips(data.get("clips", []), snap), duration, limit=opts.clips)
    titles = [t.strip() for t in data.get("titles", []) if str(t).strip()][: opts.titles]
    return Result(
        chapters=chapters, summary=str(data.get("summary", "")).strip(), titles=titles, clips=clips,
        transcript=transcript, report=report,
    )
