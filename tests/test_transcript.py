from __future__ import annotations

import json

import pytest

from chaptergen.timefmt import fmt_ts, parse_ts
from chaptergen.transcript import Segment, Transcript, load_transcript


@pytest.mark.parametrize(
    "text, seconds",
    [("0:00", 0), ("02:03", 123), ("62:03", 3723), ("1:02:03", 3723), ("00:01:02,500", 62.5), ("1:02.25", 62.25)],
)
def test_parse_ts(text, seconds):
    assert parse_ts(text) == seconds


@pytest.mark.parametrize("bad", ["", "abc", "1:2", "01:61", "12"])
def test_parse_ts_rejects(bad):
    with pytest.raises(ValueError):
        parse_ts(bad)


def test_fmt_ts_like_youtube():
    assert fmt_ts(0) == "0:00"
    assert fmt_ts(754) == "12:34"
    assert fmt_ts(3723) == "1:02:03"
    assert fmt_ts(65, force_hours=True) == "0:01:05"


def test_load_timestamped_text(data_dir):
    t = load_transcript(data_dir / "episode.txt")
    assert len(t.segments) == 46
    assert t.segments[0].start == 0 and t.segments[-1].start == 617
    assert t.duration > 617
    assert t.as_prompt_text().splitlines()[1].startswith("[0:09] I've been posting")


def test_load_srt_merges_fragments(tmp_path):
    srt = tmp_path / "c.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,500\nHello and\n\n"
        "2\n00:00:01,500 --> 00:00:03,000\n<i>welcome back.</i>\n\n"
        "3\n00:00:05,000 --> 00:00:08,000\nToday we talk hooks.\n",
        encoding="utf-8",
    )
    t = load_transcript(srt)
    assert [(s.start, s.text) for s in t.segments] == [(0, "Hello and welcome back."), (5, "Today we talk hooks.")]
    assert t.duration == 8


def test_load_vtt(tmp_path):
    vtt = tmp_path / "c.vtt"
    vtt.write_text("WEBVTT\n\n00:01.000 --> 00:04.000\nFirst line.\n\n00:10.000 --> 00:12.000\nSecond.\n")
    assert [s.start for s in load_transcript(vtt).segments] == [1, 10]


def test_json_round_trip(tmp_path):
    t = Transcript.from_segments([Segment(0, "a"), Segment(30, "b")], duration=60)
    path = tmp_path / "t.json"
    path.write_text(json.dumps(t.to_dict()))
    loaded = load_transcript(path)
    assert loaded.duration == 60 and [s.text for s in loaded.segments] == ["a", "b"]


def test_empty_or_unreadable(tmp_path):
    (tmp_path / "e.txt").write_text("no timestamps here")
    with pytest.raises(ValueError):
        load_transcript(tmp_path / "e.txt")
    with pytest.raises(ValueError):
        Transcript.from_segments([Segment(0, "   ")])


def test_hours_in_prompt_for_long_recordings():
    t = Transcript.from_segments([Segment(0, "a"), Segment(3700, "b")])
    assert t.as_prompt_text().splitlines() == ["[0:00:00] a", "[1:01:40] b"]
