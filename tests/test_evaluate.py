from __future__ import annotations

import json

import pytest

from chaptergen.evaluate import evaluate_folder, load_chapters, score
from chaptergen.rules import Chapter


def chapters(*starts):
    return [Chapter(s, f"c{s}") for s in starts]


def test_perfect_match():
    s = score(chapters(0, 60, 120), chapters(0, 60, 120))
    assert (s.precision, s.recall, s.f1, s.mean_offset) == (1, 1, 1, 0)


def test_within_and_outside_tolerance():
    s = score(chapters(0, 70, 300), chapters(0, 60, 120), tolerance=30)
    assert s.precision == 0.5 and s.recall == 0.5 and s.mean_offset == 10


def test_one_to_one_matching():
    # Two predictions near one reference boundary only count once.
    s = score(chapters(0, 58, 62), chapters(0, 60))
    assert s.precision == 0.5 and s.recall == 1


def test_zero_is_ignored_and_empty_lists():
    assert score(chapters(0), chapters(0)).f1 == 1
    assert score(chapters(0), chapters(0, 60)).recall == 0


def test_load_from_text_and_json(tmp_path):
    (tmp_path / "ref.txt").write_text("Chapters:\n0:00 Intro\n1:30 Main part\nnot a chapter\n12:05 - Outro\n")
    assert [(c.start, c.title) for c in load_chapters(tmp_path / "ref.txt")] == [
        (0, "Intro"), (90, "Main part"), (725, "Outro")
    ]
    predicted = {"chapters": [{"start": 0, "title": "a"}, {"start": "1:00", "title": "b"}]}
    (tmp_path / "p.json").write_text(json.dumps(predicted))
    assert [c.start for c in load_chapters(tmp_path / "p.json")] == [0, 60]


def test_evaluate_folder(tmp_path):
    (tmp_path / "ep1.reference.txt").write_text("0:00 A\n1:00 B\n2:00 C\n")
    (tmp_path / "ep1.json").write_text(json.dumps({"chapters": [{"start": 0, "title": "A"}, {"start": 65, "title": "B"},
                                                                {"start": 120, "title": "C"}]}))
    (tmp_path / "ep2.reference.txt").write_text("0:00 A\n")  # no prediction: skipped
    rows = evaluate_folder(tmp_path)
    assert [name for name, _ in rows] == ["ep1"]
    assert rows[0][1].f1 == pytest.approx(1)
