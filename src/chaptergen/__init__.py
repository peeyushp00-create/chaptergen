"""chaptergen: YouTube chapters, summaries, titles and clip ideas from videos and podcasts."""

from .evaluate import load_chapters, score
from .llm import DEFAULT_MODEL, ChaptergenError, GeminiLLM
from .pipeline import Options, Result, generate, transcribe
from .rules import Chapter, Clip, is_valid, repair_chapters
from .transcript import Segment, Transcript, load_transcript

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_MODEL", "Chapter", "ChaptergenError", "Clip", "GeminiLLM", "Options", "Result", "Segment",
    "Transcript", "generate", "is_valid", "load_chapters", "load_transcript", "repair_chapters", "score",
    "transcribe", "__version__",
]
