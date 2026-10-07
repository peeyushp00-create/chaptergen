"""Measure chapter quality against chapters a human wrote.

"Is the AI output good?" needs a number, not a feeling. For each video the
predicted chapter boundaries are matched one-to-one with the human ones
(within a tolerance, default 30 s). From that:

- precision: share of predicted boundaries that match a human one
- recall:    share of human boundaries the model found
- F1:        balance of the two
- offset:    how far off matched boundaries are, on average (seconds)

The 0:00 chapter is ignored because every list starts there.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .rules import Chapter
from .timefmt import parse_ts
from .transcript import TIMESTAMPED_LINE


@dataclass
class Score:
    precision: float
    recall: float
    f1: float
    mean_offset: float | None
    predicted: int
    reference: int


def load_chapters(path: str | Path) -> list[Chapter]:
    """Chapters from chaptergen's JSON output, or a text file with "0:00 Title" lines
    (the format of a YouTube description)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        items = data["chapters"] if isinstance(data, dict) else data
        return [Chapter(start=float(c["start"]) if not isinstance(c["start"], str) else parse_ts(c["start"]),
                        title=c["title"]) for c in items]
    chapters = []
    for line in text.splitlines():
        m = TIMESTAMPED_LINE.match(line)
        if m:
            chapters.append(Chapter(start=parse_ts(m.group(1)), title=m.group(2).strip()))
    return chapters


def score(predicted: list[Chapter], reference: list[Chapter], tolerance: float = 30.0) -> Score:
    pred = sorted(c.start for c in predicted if c.start > 0)
    ref = sorted(c.start for c in reference if c.start > 0)

    # Greedy one-to-one matching, closest pairs first.
    pairs = sorted(((abs(p - r), i, j) for i, p in enumerate(pred) for j, r in enumerate(ref)), key=lambda x: x[0])
    used_p: set[int] = set()
    used_r: set[int] = set()
    offsets = []
    for dist, i, j in pairs:
        if dist > tolerance:
            break
        if i in used_p or j in used_r:
            continue
        used_p.add(i)
        used_r.add(j)
        offsets.append(dist)

    matched = len(offsets)
    precision = matched / len(pred) if pred else (1.0 if not ref else 0.0)
    recall = matched / len(ref) if ref else (1.0 if not pred else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return Score(
        precision=precision, recall=recall, f1=f1,
        mean_offset=sum(offsets) / matched if matched else None,
        predicted=len(predicted), reference=len(reference),
    )


def evaluate_folder(folder: str | Path, tolerance: float = 30.0) -> list[tuple[str, Score]]:
    """Score every NAME.json (chaptergen output) against NAME.reference.txt in a folder."""
    folder = Path(folder)
    results = []
    for ref_path in sorted(folder.glob("*.reference.txt")):
        name = ref_path.name[: -len(".reference.txt")]
        pred_path = folder / f"{name}.json"
        if pred_path.exists():
            results.append((name, score(load_chapters(pred_path), load_chapters(ref_path), tolerance)))
    return results
