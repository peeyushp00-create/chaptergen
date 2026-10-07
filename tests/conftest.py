from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

DATA = Path(__file__).parent / "data"


class FakeLLM:
    """Stands in for Gemini: returns queued responses and records every request."""

    def __init__(self, *responses: dict[str, Any]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, *, prompt, schema, system=None, media=None):
        self.calls.append({"prompt": prompt, "schema": schema, "system": system, "media": media})
        if not self.responses:
            raise AssertionError("FakeLLM ran out of responses")
        return self.responses.pop(0)


@pytest.fixture
def data_dir() -> Path:
    return DATA


@pytest.fixture
def episode_response() -> dict[str, Any]:
    return json.loads((DATA / "episode.response.json").read_text(encoding="utf-8"))
