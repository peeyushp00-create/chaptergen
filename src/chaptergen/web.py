"""A one-page local web app: drop a file, get chapters. Standard library only.

Runs on 127.0.0.1 so only your own computer can reach it.
"""

from __future__ import annotations

import json
import tempfile
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from .cli import TRANSCRIPT_EXTENSIONS
from .llm import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, ChaptergenError, GeminiLLM
from .output import render_text, youtube_chapters
from .pipeline import generate, transcribe
from .transcript import load_transcript

MAX_UPLOAD = 1024 * 1024 * 1024  # 1 GB
ALLOWED = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS | TRANSCRIPT_EXTENSIONS

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>chaptergen</title>
<style>
  :root { --bg:#f7f7f5; --card:#fff; --ink:#1d1d1f; --muted:#6b6b70; --line:#e4e4e0; --accent:#c4302b; }
  @media (prefers-color-scheme: dark) { :root { --bg:#151517; --card:#1f1f22; --ink:#ececee; --muted:#9a9aa1; --line:#2e2e33; } }
  * { box-sizing:border-box } body { margin:0; font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink) }
  main { max-width:760px; margin:0 auto; padding:40px 16px 64px }
  h1 { font-size:28px; margin:0 0 4px } .sub { color:var(--muted); margin:0 0 24px }
  #drop { border:2px dashed var(--line); border-radius:14px; background:var(--card); padding:40px 16px; text-align:center; cursor:pointer }
  #drop.over { border-color:var(--accent) } #drop strong { display:block; font-size:18px }
  #drop span { color:var(--muted); font-size:14px }
  #status { margin:16px 0; color:var(--muted); min-height:24px }
  section { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px; margin-top:16px }
  h2 { font-size:15px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); margin:0 0 10px; display:flex; justify-content:space-between; align-items:center }
  pre { margin:0; white-space:pre-wrap; font:15px/1.6 ui-monospace,Menlo,Consolas,monospace }
  button { font:inherit; font-size:13px; border:1px solid var(--line); background:transparent; color:var(--ink); border-radius:8px; padding:4px 10px; cursor:pointer }
  ol { margin:0; padding-left:20px } li { margin:4px 0 } .why { color:var(--muted) }
  .hidden { display:none }
</style></head><body><main>
<h1>chaptergen</h1>
<p class="sub">Drop a video, podcast or caption file to get YouTube chapters, a summary, title ideas and clip ideas.</p>
<label id="drop"><strong>Drop a file here or click to choose</strong>
  <span>MP4, MOV, MP3, WAV, M4A &middot; or captions: SRT, VTT, TXT</span>
  <input id="file" type="file" class="hidden"></label>
<div id="status"></div>
<div id="out" class="hidden">
  <section><h2>Chapters <button data-copy="chapters">Copy</button></h2><pre id="chapters"></pre></section>
  <section><h2>Summary</h2><p id="summary"></p></section>
  <section><h2>Title ideas</h2><ol id="titles"></ol></section>
  <section><h2>Clip ideas</h2><ol id="clips"></ol></section>
  <section><h2>Everything as text <button data-copy="all">Copy</button></h2><pre id="all"></pre></section>
</div>
<script>
const $ = (id) => document.getElementById(id);
const drop = $("drop"), input = $("file"), status = $("status");
const show = (msg) => { status.textContent = msg; };
["dragenter","dragover"].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add("over"); }));
["dragleave","drop"].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", ev => ev.dataTransfer.files[0] && run(ev.dataTransfer.files[0]));
input.addEventListener("change", () => input.files[0] && run(input.files[0]));
document.querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", async () => {
  await navigator.clipboard.writeText($(b.dataset.copy).textContent); b.textContent = "Copied"; setTimeout(() => b.textContent = "Copy", 1500);
}));
const li = (text, extra) => { const el = document.createElement("li"); el.textContent = text;
  if (extra) { const s = document.createElement("span"); s.className = "why"; s.textContent = " — " + extra; el.append(s); } return el; };
async function run(file) {
  $("out").classList.add("hidden");
  show("Uploading " + file.name + "… transcribing and finding chapters can take a minute or two.");
  try {
    const res = await fetch("/api/run", { method: "POST", body: file, headers: { "X-Filename": encodeURIComponent(file.name) } });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Something went wrong");
    const r = data.result;
    $("chapters").textContent = data.chapters;
    $("summary").textContent = r.summary;
    $("titles").replaceChildren(...r.titles.map(t => li(t)));
    $("clips").replaceChildren(...r.clips.map(c => li(c.time + "  “" + c.hook + "”", c.reason)));
    $("all").textContent = data.text;
    $("out").classList.remove("hidden");
    show((r.warnings || []).join(" ") || "Done.");
  } catch (err) { show("Error: " + err.message); }
}
</script></main></body></html>
"""


def make_handler(model: str):
    lock = threading.Lock()  # one job at a time: keeps API usage predictable

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter console
            pass

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path not in ("/", "/index.html"):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/api/run":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            name = Path(unquote(self.headers.get("X-Filename", "upload"))).name
            suffix = Path(name).suffix.lower()
            length = int(self.headers.get("Content-Length") or 0)
            if suffix not in ALLOWED:
                self._json(400, {"error": f"Unsupported file type '{suffix}'."})
                return
            if not 0 < length <= MAX_UPLOAD:
                self._json(400, {"error": "The file is empty or larger than 1 GB."})
                return
            with tempfile.TemporaryDirectory(prefix="chaptergen-") as tmp:
                path = Path(tmp) / f"upload{suffix}"
                with open(path, "wb") as f:
                    remaining = length
                    while remaining:
                        chunk = self.rfile.read(min(remaining, 1 << 20))
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining -= len(chunk)
                try:
                    with lock:
                        llm = GeminiLLM(model=model)
                        transcript = (
                            load_transcript(path) if suffix in TRANSCRIPT_EXTENSIONS else transcribe(llm, path)
                        )
                        result = generate(llm, transcript)
                except (ChaptergenError, ValueError) as err:
                    self._json(400, {"error": str(err)})
                    return
            self._json(200, {"result": result.to_dict(), "chapters": youtube_chapters(result),
                             "text": render_text(result)})

    return Handler


def serve(model: str, port: int = 8765, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(model))
    url = f"http://127.0.0.1:{port}/"
    print(f"chaptergen is running at {url}  (press Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
