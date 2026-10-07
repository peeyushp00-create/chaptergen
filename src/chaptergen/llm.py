"""The only module that talks to an AI model.

Everything else depends on the small `LLM` protocol, so tests can swap in a
fake that replays recorded responses and run without an API key or network.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Protocol

DEFAULT_MODEL = "gemini-3.5-flash-lite"


class ChaptergenError(Exception):
    """A problem the user can act on (shown without a traceback)."""


class LLM(Protocol):
    def generate_json(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        system: str | None = None,
        media: Path | None = None,
    ) -> dict[str, Any]: ...


def _media_kind(path: Path) -> str:
    return "video" if path.suffix.lower() in VIDEO_EXTENSIONS else "audio"


AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".aiff", ".webm"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".mpeg", ".mpg", ".wmv", ".flv", ".3gp"}


class GeminiLLM:
    """Gemini through the official google-genai SDK (Interactions API).

    The API key is read from GEMINI_API_KEY or GOOGLE_API_KEY.
    """

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None, temperature: float = 0.2):
        try:
            from google import genai
        except ImportError as err:  # pragma: no cover - dependency is installed with the package
            raise ChaptergenError("the google-genai package is missing: pip install google-genai") from err
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ChaptergenError(
                "No Gemini API key found. Get a free key at https://aistudio.google.com/apikey and set it:\n"
                '  Windows PowerShell:  $env:GEMINI_API_KEY = "your-key"\n'
                '  macOS / Linux:       export GEMINI_API_KEY="your-key"'
            )
        self.client = genai.Client(api_key=key)
        self.model = model
        self.temperature = temperature

    def _upload(self, path: Path) -> Any:
        uploaded = self.client.files.upload(file=str(path))
        # Video (and sometimes long audio) is processed before it can be used.
        deadline = time.monotonic() + 600
        while str(getattr(uploaded, "state", "ACTIVE")).upper().endswith("PROCESSING"):
            if time.monotonic() > deadline:
                raise ChaptergenError("Gemini took too long to process the uploaded file")
            time.sleep(3)
            uploaded = self.client.files.get(name=uploaded.name)
        if str(getattr(uploaded, "state", "")).upper().endswith("FAILED"):
            raise ChaptergenError("Gemini could not process this file; try converting it to MP3 first")
        return uploaded

    def generate_json(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        system: str | None = None,
        media: Path | None = None,
    ) -> dict[str, Any]:
        uploaded = self._upload(media) if media else None
        try:
            parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
            if uploaded is not None:
                parts.append({"type": _media_kind(media), "uri": uploaded.uri, "mime_type": uploaded.mime_type})
            request: dict[str, Any] = {
                "model": self.model,
                "input": parts,
                "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
                "generation_config": {"temperature": self.temperature},
            }
            if system:
                request["system_instruction"] = system

            last_error: Exception | None = None
            for _attempt in range(2):  # one retry if the model returns malformed JSON
                try:
                    interaction = self.client.interactions.create(**request)
                except Exception as err:  # SDK raises various error types; surface the message
                    raise ChaptergenError(f"Gemini request failed: {err}") from err
                text = getattr(interaction, "output_text", None) or ""
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as err:
                    last_error = err
                    continue
                if isinstance(data, dict):
                    return data
                last_error = ValueError("expected a JSON object")
            raise ChaptergenError(f"Gemini returned an unreadable response ({last_error})")
        finally:
            if uploaded is not None:
                try:  # don't leave the user's recording stored on Google's side
                    self.client.files.delete(name=uploaded.name)
                except Exception:
                    pass
