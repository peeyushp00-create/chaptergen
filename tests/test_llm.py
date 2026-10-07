"""GeminiLLM against a stand-in SDK client: checks the exact request we send."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chaptergen.llm import ChaptergenError, GeminiLLM


class FakeFiles:
    def __init__(self, states):
        self.states = list(states)
        self.deleted = []

    def _file(self):
        return SimpleNamespace(name="files/abc", uri="https://files/abc", mime_type="audio/mpeg",
                               state=self.states.pop(0))

    def upload(self, file):
        return self._file()

    def get(self, name):
        return self._file()

    def delete(self, name):
        self.deleted.append(name)


class FakeInteractions:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return SimpleNamespace(output_text=out)


def make(monkeypatch, outputs, states=("ACTIVE",)):
    llm = GeminiLLM(model="m", api_key="k")
    llm.client = SimpleNamespace(files=FakeFiles(states), interactions=FakeInteractions(outputs))
    monkeypatch.setattr("chaptergen.llm.time.sleep", lambda s: None)
    return llm


def test_request_shape_for_text(monkeypatch):
    llm = make(monkeypatch, ['{"ok": true}'])
    assert llm.generate_json(prompt="hi", schema={"type": "object"}, system="sys") == {"ok": True}
    req = llm.client.interactions.requests[0]
    assert req["model"] == "m"
    assert req["input"] == [{"type": "text", "text": "hi"}]
    assert req["response_format"] == {"type": "text", "mime_type": "application/json", "schema": {"type": "object"}}
    assert req["system_instruction"] == "sys"
    assert req["generation_config"] == {"temperature": 0.2}


def test_media_is_uploaded_waited_for_and_deleted(monkeypatch, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    llm = make(monkeypatch, ['{"segments": []}'], states=["PROCESSING", "PROCESSING", "ACTIVE"])
    llm.generate_json(prompt="p", schema={}, media=video)
    parts = llm.client.interactions.requests[0]["input"]
    assert parts[1] == {"type": "video", "uri": "https://files/abc", "mime_type": "audio/mpeg"}
    assert llm.client.files.deleted == ["files/abc"]


def test_retries_once_on_bad_json_then_fails(monkeypatch):
    llm = make(monkeypatch, ["not json", '{"a": 1}'])
    assert llm.generate_json(prompt="p", schema={}) == {"a": 1}

    llm = make(monkeypatch, ["nope", "[1, 2]"])
    with pytest.raises(ChaptergenError, match="unreadable"):
        llm.generate_json(prompt="p", schema={})


def test_api_errors_become_readable(monkeypatch, tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    llm = make(monkeypatch, [RuntimeError("quota exceeded")])
    with pytest.raises(ChaptergenError, match="quota exceeded"):
        llm.generate_json(prompt="p", schema={}, media=audio)
    assert llm.client.files.deleted == ["files/abc"]  # cleaned up even on failure


def test_failed_processing(monkeypatch, tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    llm = make(monkeypatch, [], states=["FAILED"])
    with pytest.raises(ChaptergenError, match="could not process"):
        llm.generate_json(prompt="p", schema={}, media=audio)


def test_missing_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ChaptergenError, match="GEMINI_API_KEY"):
        GeminiLLM()
