from __future__ import annotations

from chaptergen.rules import Chapter, Clip, is_valid, repair_chapters, repair_clips


def starts(chapters):
    return [c.start for c in chapters]


def test_valid_chapters_are_untouched():
    chapters = [Chapter(0, "Intro"), Chapter(60, "Main"), Chapter(300, "Outro")]
    fixed, report = repair_chapters(chapters, duration=400)
    assert starts(fixed) == [0, 60, 300]
    assert report.fixes == [] and report.warnings == []
    assert is_valid(fixed, 400) == []


def test_first_chapter_moved_to_zero_or_intro_added():
    fixed, report = repair_chapters([Chapter(4, "Hook"), Chapter(60, "A"), Chapter(120, "B")], 300)
    assert starts(fixed) == [0, 60, 120] and fixed[0].title == "Hook"
    assert "0:00" in report.fixes[0]

    fixed, report = repair_chapters([Chapter(45, "A"), Chapter(90, "B"), Chapter(150, "C")], 300)
    assert [(c.start, c.title) for c in fixed][:2] == [(0, "Intro"), (45, "A")]


def test_sorted_and_too_close_merged():
    chapters = [Chapter(0, "Intro"), Chapter(120, "B"), Chapter(60, "A"), Chapter(65, "A again")]
    fixed, report = repair_chapters(chapters, 300)
    assert starts(fixed) == [0, 60, 120]
    assert any("time order" in f for f in report.fixes)
    assert any("A again" in f for f in report.fixes)


def test_outside_video_and_too_close_to_end_removed():
    chapters = [Chapter(0, "Intro"), Chapter(100, "Main"), Chapter(295, "End"), Chapter(400, "Ghost")]
    fixed, report = repair_chapters(chapters, 300)
    assert starts(fixed) == [0, 100]
    assert any("outside" in f for f in report.fixes)
    assert any("End" in f for f in report.fixes)
    assert any("at least 3" in w for w in report.warnings)


def test_titles_cleaned_and_shortened():
    long = "A really long chapter title that keeps going well past what fits in the progress bar"
    fixed, _ = repair_chapters([Chapter(0, "  Intro\n"), Chapter(60, long), Chapter(120, "- Q&A -")], 300)
    assert fixed[0].title == "Intro"
    assert len(fixed[1].title) <= 60 and fixed[1].title.endswith("…")
    assert fixed[2].title == "Q&A"


def test_is_valid_lists_every_problem():
    problems = is_valid([Chapter(5, "a"), Chapter(8, "b")], 100)
    assert len(problems) == 3


def test_repair_clips():
    clips = [
        Clip(10, 12, "too short: extended to 15 s"),
        Clip(20, 400, "overlaps the first clip: dropped"),
        Clip(100, 130, ""),  # no hook text: dropped
        Clip(250, 400, "too long: cut to 90 s"),
        Clip(595, 700, "only 5 s left before the end: dropped"),
    ]
    fixed = repair_clips(clips, duration=600)
    assert [(c.start, c.end) for c in fixed] == [(10, 25), (250, 340)]


def test_repair_clips_limit():
    clips = [Clip(i * 100, i * 100 + 30, f"clip {i}") for i in range(6)]
    assert len(repair_clips(clips, duration=1000, limit=3)) == 3
