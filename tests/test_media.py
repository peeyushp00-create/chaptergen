from __future__ import annotations

import subprocess

import pytest

from chaptergen.media import ffmpeg_available, prepare_audio, probe_duration

needs_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg is not installed")


@needs_ffmpeg
def test_video_becomes_small_audio(tmp_path):
    video = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest", str(video)],
        check=True,
    )
    assert probe_duration(video) == pytest.approx(3, abs=0.2)
    audio, is_temp = prepare_audio(video)
    try:
        assert is_temp and audio.suffix == ".mp3"
        assert audio.stat().st_size < video.stat().st_size
        assert probe_duration(audio) == pytest.approx(3, abs=0.2)
    finally:
        audio.unlink(missing_ok=True)


@needs_ffmpeg
def test_mp3_is_sent_as_is(tmp_path):
    mp3 = tmp_path / "a.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=1", str(mp3)], check=True)
    assert prepare_audio(mp3) == (mp3, False)


def test_without_ffmpeg_files_are_sent_as_is(tmp_path, monkeypatch):
    monkeypatch.setattr("chaptergen.media.ffmpeg_available", lambda: False)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    assert prepare_audio(video) == (video, False)
    assert probe_duration(video) is None
