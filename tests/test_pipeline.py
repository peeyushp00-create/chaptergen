"""The full pipeline with a fake model: prompts, parsing, repair and output."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chaptergen import pipeline
from chaptergen.evaluate import load_chapters, score
from chaptergen.llm import ChaptergenError
from chaptergen.output import render_json, render_markdown, render_text, youtube_chapters
from chaptergen.pipeline import Options, generate, transcribe
from chaptergen.rules import is_valid
from chaptergen.transcript import Segment, Transcript, load_transcript

from .conftest import FakeLLM


def test_generate_repairs_model_output(data_dir, episode_response):
    transcript = load_transcript(data_dir / "episode.txt")
    llm = FakeLLM(episode_response)
    result = generate(llm, transcript)

    # One request, carrying the transcript and the schema.
    assert len(llm.calls) == 1
    assert "[2:12] Now let me show you the hook formula" in llm.calls[0]["prompt"]
    assert llm.calls[0]["schema"]["required"] == ["chapters", "summary", "titles", "clips"]

    # The response had a first chapter at 0:03, a time not in the transcript (7:11)
    # and two chapters 5 s apart; the result follows YouTube's rules regardless.
    assert is_valid(result.chapters, transcript.duration) == []
    assert youtube_chapters(result).splitlines()[:3] == [
        "0:00 Intro",
        "0:52 Why most reels die in 3 seconds",
        "2:12 The Problem, Proof, Promise hook formula",
    ]
    assert "7:12 Does posting time matter?" in youtube_chapters(result)
    assert any("nearest sentence" in f for f in result.report.fixes)
    assert any("first-frame" in f for f in result.report.fixes)

    # Clips stay inside the recording.
    assert all(c.end <= transcript.duration for c in result.clips)
    assert len(result.titles) == 3 and result.summary


def test_quality_against_human_chapters(data_dir, episode_response):
    result = generate(FakeLLM(episode_response), load_transcript(data_dir / "episode.txt"))
    s = score(result.chapters, load_chapters(data_dir / "episode.reference.txt"))
    assert s.f1 > 0.9 and s.mean_offset < 10


def test_options_reach_the_prompt(data_dir, episode_response):
    llm = FakeLLM(episode_response)
    result = generate(llm, load_transcript(data_dir / "episode.txt"), Options(kind="podcast", titles=1, clips=1))
    assert "transcript of a podcast" in llm.calls[0]["prompt"]
    assert len(result.titles) == 1 and len(result.clips) == 1


def test_malformed_items_are_skipped():
    transcript = Transcript.from_segments([Segment(i * 60, f"part {i}") for i in range(10)])
    response = {
        "chapters": [{"start": "0:00", "title": "Start"}, {"start": "banana", "title": "Bad"}, {"title": "No time"},
                     {"start": "3:00", "title": "Middle"}, {"start": "6:00", "title": "Late"}],
        "summary": "s", "titles": ["t", ""], "clips": [{"start": "nope", "end": "1:00", "hook": "x"}],
    }
    result = generate(FakeLLM(response), transcript)
    assert [c.title for c in result.chapters] == ["Start", "Middle", "Late"]
    assert result.titles == ["t"] and result.clips == []


def test_long_recordings_are_chunked_then_merged(monkeypatch):
    monkeypatch.setattr(pipeline, "CHUNK_CHARS", 500)
    transcript = Transcript.from_segments([Segment(i * 30, f"sentence number {i} " * 3) for i in range(200)])
    window = {"chapters": [{"start": "0:00", "title": "x"}], "summary": "", "titles": [], "clips": []}
    final = {"chapters": [{"start": "0:00", "title": "One"}, {"start": "40:00", "title": "Two"},
                          {"start": "80:00", "title": "Three"}], "summary": "s", "titles": ["t"], "clips": []}
    n_windows = len(pipeline._windows(transcript))
    llm = FakeLLM(*([window] * n_windows), final)
    result = generate(llm, transcript)
    assert n_windows == 3
    assert len(llm.calls) == n_windows + 1
    assert "chapter candidates" in llm.calls[-1]["prompt"]
    assert [c.title for c in result.chapters] == ["One", "Two", "Three"]


def test_transcribe_sends_audio_and_parses_segments(tmp_path, monkeypatch):
    audio = tmp_path / "talk.wav"
    audio.write_bytes(b"RIFF....WAVE")
    monkeypatch.setattr(pipeline, "probe_duration", lambda p: 95.0)
    monkeypatch.setattr(pipeline, "prepare_audio", lambda p: (p, False))
    llm = FakeLLM({"segments": [{"start": "00:00", "text": "Namaste dosto"}, {"start": "bad", "text": "skip"},
                                {"start": "01:10", "text": "Aaj ka topic"}]})
    t = transcribe(llm, audio)
    assert llm.calls[0]["media"] == audio
    assert "do not translate" in llm.calls[0]["system"]
    assert [(s.start, s.text) for s in t.segments] == [(0, "Namaste dosto"), (70, "Aaj ka topic")]
    assert t.duration == 95


def test_transcribe_rejects_silence_and_bad_files(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "probe_duration", lambda p: None)
    monkeypatch.setattr(pipeline, "prepare_audio", lambda p: (p, False))
    audio = tmp_path / "silence.mp3"
    audio.write_bytes(b"ID3")
    with pytest.raises(ChaptergenError, match="no speech"):
        transcribe(FakeLLM({"segments": []}), audio)
    with pytest.raises(ChaptergenError, match="unsupported"):
        transcribe(FakeLLM(), Path(__file__))


def test_renderers(data_dir, episode_response):
    result = generate(FakeLLM(episode_response), load_transcript(data_dir / "episode.txt"))
    text = render_text(result)
    assert text.startswith("CHAPTERS") and "TITLE IDEAS" in text and "CLIP IDEAS" in text
    md = render_markdown(result)
    assert "## Chapters" in md and "| Time | Hook | Why |" in md
    data = json.loads(render_json(result))
    assert data["chapters"][0] == {"start": 0.0, "time": "0:00", "title": "Intro"}
    assert data["fixes"]
