from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from chaptergen import cli, web

from .conftest import FakeLLM


@pytest.fixture(autouse=True)
def no_real_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


@pytest.fixture
def fake_gemini(monkeypatch, episode_response):
    """Make GeminiLLM() return a FakeLLM loaded with the canned episode response."""
    monkeypatch.setattr(cli, "GeminiLLM", lambda model=None: FakeLLM(episode_response))
    monkeypatch.setattr(web, "GeminiLLM", lambda model=None: FakeLLM(episode_response))


def test_run_on_transcript_prints_chapters_and_saves(fake_gemini, data_dir, tmp_path, capsys):
    out = tmp_path / "result.json"
    code = cli.main(["run", str(data_dir / "episode.txt"), "-o", str(out)])
    stdout, stderr = capsys.readouterr()
    assert code == 0
    assert stdout.startswith("CHAPTERS") and "0:00 Intro" in stdout
    assert "fixed:" in stderr
    assert json.loads(out.read_text(encoding="utf-8"))["chapters"][1]["time"] == "0:52"


def test_run_formats(fake_gemini, data_dir, capsys):
    cli.main(["run", str(data_dir / "episode.txt"), "--format", "md"])
    assert capsys.readouterr().out.startswith("## Chapters")


def test_helpful_errors(data_dir, tmp_path, capsys):
    assert cli.main(["run", str(tmp_path / "missing.mp4")]) == 1
    assert "file not found" in capsys.readouterr().err
    (tmp_path / "notes.pdf").write_bytes(b"%PDF")
    assert cli.main(["run", str(tmp_path / "notes.pdf")]) == 1
    assert "unsupported file type" in capsys.readouterr().err
    assert cli.main(["run", str(data_dir / "episode.txt")]) == 1  # no API key set
    assert "aistudio.google.com" in capsys.readouterr().err


def test_eval_single_and_folder(data_dir, tmp_path, fake_gemini, capsys):
    pred = tmp_path / "episode.json"
    cli.main(["run", str(data_dir / "episode.txt"), "-o", str(pred)])
    capsys.readouterr()
    assert cli.main(["eval", str(pred), str(data_dir / "episode.reference.txt")]) == 0
    out = capsys.readouterr().out
    assert "precision" in out and "0.92" in out

    (tmp_path / "episode.reference.txt").write_text((data_dir / "episode.reference.txt").read_text())
    assert cli.main(["eval", str(tmp_path)]) == 0
    assert "episode" in capsys.readouterr().out


def test_web_page_and_api(fake_gemini, data_dir):
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler("test-model"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "<title>chaptergen</title>" in page

        body = (data_dir / "episode.txt").read_bytes()
        req = urllib.request.Request(base + "/api/run", data=body, method="POST",
                                     headers={"X-Filename": "episode.txt", "Content-Type": "application/octet-stream"})
        data = json.loads(urllib.request.urlopen(req).read())
        assert data["chapters"].splitlines()[0] == "0:00 Intro"
        assert data["result"]["titles"]

        bad = urllib.request.Request(base + "/api/run", data=b"x", method="POST", headers={"X-Filename": "a.exe"})
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(bad)
        assert err.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
