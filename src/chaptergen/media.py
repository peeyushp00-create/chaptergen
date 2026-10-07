"""Optional ffmpeg helpers.

With ffmpeg installed, video is reduced to a small mono audio track before
upload: a 1-hour MP4 becomes ~15 MB of audio, which uploads faster and costs
far fewer tokens than sending the video. Without ffmpeg, files are sent as-is.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .llm import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, ChaptergenError


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def check_media(path: Path) -> None:
    if not path.exists():
        raise ChaptergenError(f"file not found: {path}")
    if path.suffix.lower() not in AUDIO_EXTENSIONS | VIDEO_EXTENSIONS:
        raise ChaptergenError(
            f"unsupported file type '{path.suffix}'. Use an audio or video file, or a caption file (.srt, .vtt, .txt)"
        )


def probe_duration(path: Path) -> float | None:
    """Length in seconds via ffprobe, or None if ffprobe isn't available."""
    if not ffmpeg_available():
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout.strip()
        return float(out)
    except (subprocess.SubprocessError, ValueError):
        return None


def prepare_audio(path: Path) -> tuple[Path, bool]:
    """Return (file to upload, whether it's a temporary file the caller should delete)."""
    if not ffmpeg_available() or path.suffix.lower() in {".mp3", ".m4a", ".ogg", ".opus"}:
        return path, False
    tmp = Path(tempfile.mkstemp(prefix="chaptergen-", suffix=".mp3")[1])
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(path),
             "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", str(tmp)],
            capture_output=True, timeout=3600, check=True,
        )
    except subprocess.SubprocessError:
        tmp.unlink(missing_ok=True)
        return path, False
    return tmp, True
