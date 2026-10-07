<div align="center">

# chaptergen

**Turn videos and podcasts into YouTube chapters, a summary, title ideas and Shorts/Reels clip ideas — with Gemini.**

[![CI](https://github.com/peeyushp00-create/chaptergen/actions/workflows/ci.yml/badge.svg)](https://github.com/peeyushp00-create/chaptergen/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)

</div>

## Why

Chapters make a long video easier to watch and easier to find: YouTube shows them in the progress bar, in search and in "key moments". But writing them means scrubbing through the whole video and noting where each topic starts — 20–30 minutes per upload — so most creators skip it. Podcasters have the same problem with show notes.

chaptergen listens to the recording and does it for you, and then checks the result against YouTube's rules before handing it back.

## What you get

```console
$ chaptergen run tests/data/episode.txt
Reading transcript episode.txt...
Finding chapters, clips and titles...
  fixed: moved 3 chapter time(s) to the nearest sentence start in the transcript
  fixed: merged 'The first-frame mistake' into the previous chapter (too close)

CHAPTERS (paste into your YouTube description)
0:00 Intro
0:52 Why most reels die in 3 seconds
2:12 The Problem, Proof, Promise hook formula
3:20 Three real examples: what worked and what flopped
5:08 Editing for retention: a change every 2 seconds
7:12 Does posting time matter?
8:47 Q&A: trending audio, length, hashtags, consistency

SUMMARY
A data-backed breakdown of why short-form videos lose viewers in the first seconds, the three-part
hook formula that doubled the creator's views, and the editing and posting habits that keep people watching.

TITLE IDEAS
1. The 3-Second Rule That Doubled My Reel Views
2. Why Your Reels Get 200 Views (And the Fix)
3. I Tested 400 Reels: Here's What Actually Works

CLIP IDEAS (for Shorts / Reels)
4:06 - 4:35  "Same content, same edit, only the first sentence was different."  (clear before/after with numbers)
4:36 - 4:54  "Nobody scrolls past a question they can't answer."  (quotable one-liner)
```

<sub>This example uses the 10-minute sample episode in [`tests/data`](tests/data): a script written for testing, run against a hand-written model response that is deliberately imperfect so the repair steps show up. Point it at your own video or audio file to get real results.</sub>

## Install

```bash
pip install git+https://github.com/peeyushp00-create/chaptergen.git
```

Then get a free API key at **[aistudio.google.com/apikey](https://aistudio.google.com/apikey)** and set it:

```powershell
$env:GEMINI_API_KEY = "your-key"        # Windows PowerShell
```
```bash
export GEMINI_API_KEY="your-key"        # macOS / Linux
```

Optional: install [ffmpeg](https://ffmpeg.org/download.html) (`winget install ffmpeg`, `brew install ffmpeg`, `sudo apt install ffmpeg`). With it, video is reduced to a small audio track before upload — a one-hour MP4 becomes about 15 MB — which is faster and uses far fewer tokens.

## Usage

```bash
chaptergen run episode.mp4                     # video or audio: mp4, mov, mkv, mp3, wav, m4a, ...
chaptergen run captions.srt                    # or captions you already have: .srt, .vtt, .txt
chaptergen run episode.mp3 --kind podcast -o notes.md
chaptergen web                                 # drag-and-drop page in your browser
```

| Option | What it does |
| --- | --- |
| `-o FILE` | Also save the result (`.md`, `.json` or `.txt`, chosen by extension) |
| `--format text\|md\|json` | What to print |
| `--kind video\|podcast` | Wording used when talking to the model |
| `--titles N`, `--clips N` | How many title and clip ideas (default 3) |
| `--save-transcript FILE` | Keep the transcript, so you can re-run chaptering later without transcribing again |
| `--model NAME` | Gemini model (default `gemini-3.5-flash-lite`; also `$CHAPTERGEN_MODEL`) |

Starting from captions skips transcription entirely: if YouTube already auto-captioned your video, download the captions from YouTube Studio and run chaptergen on the `.srt`.

### Web page

`chaptergen web` opens a page on your own computer (`127.0.0.1`, not reachable from other devices) where you drop a file and get the chapters back with copy buttons.

## How it works

```
recording ──► ffmpeg (optional) ──► Gemini: timestamped transcript ──┐
captions (.srt/.vtt/.txt) ──────────────────────────────────────────┤
                                                                     ▼
              Gemini: chapters + summary + titles + clips (JSON, fixed schema)
                                                                     ▼
       snap times to real sentence starts ─► enforce YouTube rules ─► output
```

1. **Transcribe.** Gemini understands audio directly, so there's no separate speech-to-text service. It returns segments with timestamps in a fixed JSON schema, keeping Hindi, Hinglish or any other language as spoken.
2. **One structured request** produces chapters, summary, titles and clips. Responses are constrained by a JSON schema, and a malformed response is retried once.
3. **Never trust a timestamp blindly.** Every time the model gives is moved to the nearest real sentence start in the transcript, so a chapter can't begin mid-sentence or at a moment that doesn't exist.
4. **Enforce YouTube's rules in code**: the first chapter at 0:00, ascending order, at least 10 seconds each, at least three, nothing past the end. Problems are repaired and reported (`fixed: …`) instead of silently passed on.
5. **Long recordings** (roughly two hours of speech or more) are processed in overlapping 40-minute windows, and the candidates are merged in a final request.

Uploaded recordings are deleted from Google's servers as soon as the request finishes.

## Measuring quality

How good are the chapters? `chaptergen eval` compares them with chapters a human wrote:

```console
$ chaptergen eval episode.json episode.reference.txt
video    precision  recall    F1   offset  chapters (pred/ref)
episode       1.00    0.86  0.92    4.3s  7/8
```

Each predicted boundary is matched to at most one human boundary within a tolerance (default 30 s). **Precision** is the share of predicted chapters that match a real topic change, **recall** the share of real topic changes that were found, and **offset** how many seconds off the matches are on average.

To track quality across many videos — for example when changing the prompt or the model — put `NAME.json` (chaptergen output) next to `NAME.reference.txt` (your chapters, in YouTube-description format) in a folder and run `chaptergen eval that-folder/` for a table and averages.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The tests never call the real API: a stand-in model returns prepared responses, so every request, the parsing, the repair rules, chunking, the evaluation maths, the CLI and the web page are tested for free and give the same result every time. Another test checks the exact request sent through the official `google-genai` SDK. CI runs on Linux, Windows and macOS.

## Costs and limits

- Gemini's [free tier](https://ai.google.dev/gemini-api/docs/pricing) is enough to try it; check the current limits on your account.
- Audio uses about 32 tokens per second (roughly 115,000 tokens per hour of recording).
- Only use recordings you have the rights to. chaptergen doesn't download from YouTube; for your own uploads, download the original or the captions from YouTube Studio.

## License

[MIT](LICENSE) © 2026 Peeyush
