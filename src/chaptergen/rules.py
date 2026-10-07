"""YouTube's chapter rules, enforced in code rather than trusted to the model.

YouTube only shows chapters when the description lists at least three
timestamps in ascending order, the first is 0:00, and every chapter is at
least 10 seconds long. A model gets these wrong often enough (a first
chapter at 0:04, two chapters 3 seconds apart, a timestamp past the end) that
the output is always repaired and checked here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MIN_CHAPTERS = 3
MIN_CHAPTER_SECONDS = 10
MAX_TITLE_CHARS = 60


@dataclass
class Chapter:
    start: float
    title: str


@dataclass
class Clip:
    start: float
    end: float
    hook: str
    reason: str = ""


@dataclass
class RepairReport:
    fixes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _clean_title(title: str) -> str:
    title = " ".join(str(title).replace("\n", " ").split()).strip(" -–—:|")
    if len(title) > MAX_TITLE_CHARS:
        cut = title[: MAX_TITLE_CHARS - 1].rsplit(" ", 1)[0]
        title = cut.rstrip(" ,;:-") + "…"
    return title


def repair_chapters(chapters: list[Chapter], duration: float) -> tuple[list[Chapter], RepairReport]:
    """Return chapters that satisfy YouTube's rules, and what had to change."""
    report = RepairReport()
    items = [Chapter(start=float(c.start), title=_clean_title(c.title)) for c in chapters if _clean_title(c.title)]

    outside = [c for c in items if c.start < 0 or c.start >= duration]
    if outside:
        report.fixes.append(f"dropped {len(outside)} chapter(s) outside the video")
        items = [c for c in items if 0 <= c.start < duration]

    ordered = sorted(items, key=lambda c: c.start)
    if [c.start for c in ordered] != [c.start for c in items]:
        report.fixes.append("put chapters in time order")
    items = ordered

    if not items or items[0].start != 0:
        if items and items[0].start < MIN_CHAPTER_SECONDS:
            report.fixes.append(f"moved the first chapter from {items[0].start:.0f}s to 0:00")
            items[0].start = 0
        else:
            report.fixes.append("added an 'Intro' chapter at 0:00")
            items.insert(0, Chapter(start=0, title="Intro"))

    # Merge chapters that are too short into the one before them.
    merged: list[Chapter] = []
    for ch in items:
        if merged and (ch.start - merged[-1].start) < MIN_CHAPTER_SECONDS:
            report.fixes.append(f"merged '{ch.title}' into the previous chapter (too close)")
            continue
        merged.append(ch)
    # The last chapter must also last 10 seconds.
    if len(merged) > 1 and duration - merged[-1].start < MIN_CHAPTER_SECONDS:
        report.fixes.append(f"merged '{merged[-1].title}' into the previous chapter (too close to the end)")
        merged.pop()

    seen: set[str] = set()
    for ch in merged:
        key = ch.title.lower()
        if key in seen:
            report.warnings.append(f"duplicate chapter title '{ch.title}'")
        seen.add(key)

    if len(merged) < MIN_CHAPTERS:
        hint = " (normal for short videos: chapters are for videos of a few minutes or more)" if duration < 180 else ""
        report.warnings.append(
            f"only {len(merged)} chapter(s); YouTube needs at least {MIN_CHAPTERS} to show chapters{hint}"
        )
    return merged, report


def is_valid(chapters: list[Chapter], duration: float) -> list[str]:
    """List every YouTube rule the chapters break (empty list = valid)."""
    problems = []
    if len(chapters) < MIN_CHAPTERS:
        problems.append(f"needs at least {MIN_CHAPTERS} chapters")
    if not chapters or chapters[0].start != 0:
        problems.append("first chapter must start at 0:00")
    starts = [c.start for c in chapters]
    if starts != sorted(starts):
        problems.append("chapters must be in ascending order")
    ends = starts[1:] + [duration]
    if any(e - s < MIN_CHAPTER_SECONDS for s, e in zip(starts, ends, strict=True)):
        problems.append(f"every chapter must be at least {MIN_CHAPTER_SECONDS} seconds long")
    return problems


def repair_clips(
    clips: list[Clip], duration: float, *, min_len: float = 15, max_len: float = 90, limit: int = 5
) -> list[Clip]:
    """Keep clips inside the video, between min_len and max_len seconds, without overlaps."""
    result: list[Clip] = []
    for clip in sorted(clips, key=lambda c: c.start):
        start = max(0.0, float(clip.start))
        end = min(float(clip.end), duration)
        if end - start < min_len:
            end = min(start + min_len, duration)
        if end - start > max_len:
            end = start + max_len
        if end - start < min_len or not clip.hook.strip():
            continue
        if result and start < result[-1].end:
            continue
        result.append(Clip(start=start, end=end, hook=clip.hook.strip(), reason=clip.reason.strip()))
    return result[:limit]
