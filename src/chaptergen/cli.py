"""chaptergen command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .evaluate import evaluate_folder, load_chapters, score
from .llm import DEFAULT_MODEL, ChaptergenError, GeminiLLM
from .media import check_media
from .output import RENDERERS
from .pipeline import Options, generate, transcribe
from .rules import is_valid
from .transcript import load_transcript

TRANSCRIPT_EXTENSIONS = {".srt", ".vtt", ".txt", ".json"}


def _say(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chaptergen",
        description="Turn videos and podcasts into YouTube chapters, a summary, title ideas and clip ideas.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"chaptergen {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    run = sub.add_parser("run", help="create chapters for a recording or a transcript")
    run.add_argument("input", help="audio/video file (mp3, wav, m4a, mp4...) or captions (.srt, .vtt, .txt, .json)")
    run.add_argument("-o", "--output", metavar="FILE", help="also save the result to FILE (format from extension)")
    run.add_argument("--format", choices=sorted(RENDERERS), default="text", help="what to print (default: text)")
    run.add_argument("--kind", choices=("video", "podcast"), default="video", help="wording used in the prompt")
    run.add_argument("--titles", type=int, default=3, metavar="N", help="number of title ideas (default 3)")
    run.add_argument("--clips", type=int, default=3, metavar="N", help="number of clip ideas (default 3)")
    run.add_argument("--model", default=os.environ.get("CHAPTERGEN_MODEL", DEFAULT_MODEL),
                     help=f"Gemini model (default {DEFAULT_MODEL}, or $CHAPTERGEN_MODEL)")
    run.add_argument("--save-transcript", metavar="FILE",
                     help="save the transcript as JSON, to re-run chaptering later without transcribing again")

    ev = sub.add_parser("eval", help="score chapters against human-written ones")
    ev.add_argument("predicted", help="chaptergen JSON output, or a folder of NAME.json + NAME.reference.txt pairs")
    ev.add_argument("reference", nargs="?", help='human chapters: a text file with "0:00 Title" lines')
    ev.add_argument("--tolerance", type=float, default=30, metavar="SEC", help="how close counts as a match (30)")

    web = sub.add_parser("web", help="open a simple web page to drop files on")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--model", default=os.environ.get("CHAPTERGEN_MODEL", DEFAULT_MODEL))
    web.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    return parser


def cmd_run(args: argparse.Namespace) -> int:
    path = Path(args.input)
    is_transcript = path.suffix.lower() in TRANSCRIPT_EXTENSIONS
    if is_transcript:
        if not path.exists():
            raise ChaptergenError(f"file not found: {path}")
    else:
        check_media(path)  # fail on a wrong path or file type before asking for an API key
    llm = GeminiLLM(model=args.model)

    if is_transcript:
        _say(f"Reading transcript {path.name}...")
        transcript = load_transcript(path)
    else:
        _say(f"Transcribing {path.name} with {args.model} (this can take a minute)...")
        transcript = transcribe(llm, path)
        if args.save_transcript:
            Path(args.save_transcript).write_text(json.dumps(transcript.to_dict(), ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
            _say(f"Saved transcript to {args.save_transcript}")

    _say("Finding chapters, clips and titles...")
    result = generate(llm, transcript, Options(kind=args.kind, titles=args.titles, clips=args.clips))
    for fix in result.report.fixes:
        _say(f"  fixed: {fix}")
    for warning in result.report.warnings:
        _say(f"  warning: {warning}")

    sys.stdout.write(RENDERERS[args.format](result))
    if args.output:
        out = Path(args.output)
        fmt = {".json": "json", ".md": "md"}.get(out.suffix.lower(), "text")
        out.write_text(RENDERERS[fmt](result), encoding="utf-8")
        _say(f"Saved {out}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    target = Path(args.predicted)
    if target.is_dir():
        rows = evaluate_folder(target, args.tolerance)
        if not rows:
            raise ChaptergenError("no NAME.json + NAME.reference.txt pairs found in that folder")
    else:
        if not args.reference:
            raise ChaptergenError("give a reference file: chaptergen eval predicted.json reference.txt")
        rows = [(target.stem, score(load_chapters(target), load_chapters(args.reference), args.tolerance))]

    width = max(len(name) for name, _ in rows)
    print(f"{'video'.ljust(width)}  precision  recall    F1   offset  chapters (pred/ref)")
    for name, s in rows:
        offset = f"{s.mean_offset:5.1f}s" if s.mean_offset is not None else "   - "
        counts = f"{s.predicted}/{s.reference}"
        print(f"{name.ljust(width)}  {s.precision:9.2f}  {s.recall:6.2f}  {s.f1:4.2f}  {offset}  {counts}")
    if len(rows) > 1:
        avg = lambda attr: sum(getattr(s, attr) for _, s in rows) / len(rows)  # noqa: E731
        print(f"{'average'.ljust(width)}  {avg('precision'):9.2f}  {avg('recall'):6.2f}  {avg('f1'):4.2f}")
    if not target.is_dir():
        problems = is_valid(load_chapters(target), duration=float("inf"))
        if problems:
            print("YouTube rules: " + "; ".join(problems))
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    from .web import serve

    serve(model=args.model, port=args.port, open_browser=not args.no_browser)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    try:
        return {"run": cmd_run, "eval": cmd_eval, "web": cmd_web}[args.command](args)
    except ChaptergenError as err:
        _say(f"chaptergen: {err}")
        return 1
    except (ValueError, OSError) as err:
        _say(f"chaptergen: {err}")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
