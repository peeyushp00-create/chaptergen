"""Prompts and JSON schemas sent to the model."""

from __future__ import annotations

TRANSCRIBE_SYSTEM = (
    "You are a careful transcriber. Transcribe speech exactly as spoken, in the language spoken "
    "(keep Hindi, Hinglish or any mix as it is; do not translate). Do not summarise or skip parts."
)

TRANSCRIBE_PROMPT = (
    "Transcribe this recording. Split it into segments of one or two sentences, and give each "
    "segment's start time measured from the beginning of the recording, as MM:SS "
    "(or H:MM:SS past one hour). Leave out long silences and music."
)

TRANSCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Start time, MM:SS or H:MM:SS"},
                    "text": {"type": "string"},
                },
                "required": ["start", "text"],
            },
        }
    },
    "required": ["segments"],
}

CHAPTERS_SYSTEM = (
    "You create YouTube chapters and show notes from timestamped transcripts. You only use "
    "timestamps that appear in the transcript, and you never invent content that is not in it."
)

CHAPTERS_PROMPT = """Below is a timestamped transcript of a {kind} that is {duration} long.

Create:
1. chapters: one chapter each time the topic clearly changes. Aim for roughly one chapter every
   {spacing}, fewer if the topic stays the same. The first chapter starts at 0:00. Each "start"
   must be copied from a [timestamp] in the transcript where the new topic begins. Titles are
   short (2-7 words), specific to what is discussed, and written in the language of the video.
   Avoid vague titles like "Discussion" or "Part 2".
2. summary: 2-3 sentences on what the viewer learns.
3. titles: {n_titles} title ideas for the video, under 70 characters, no clickbait that the
   content doesn't deliver.
4. clips: up to {n_clips} moments of 20-60 seconds that would work as a standalone Short/Reel
   (a strong claim, a surprising fact, a story with a payoff). "hook" quotes the opening line
   from the transcript; "reason" says in a few words why it works.

Transcript:
{transcript}
"""

CHAPTERS_SCHEMA = {
    "type": "object",
    "properties": {
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Timestamp copied from the transcript"},
                    "title": {"type": "string"},
                },
                "required": ["start", "title"],
            },
        },
        "summary": {"type": "string"},
        "titles": {"type": "array", "items": {"type": "string"}},
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "hook": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["start", "end", "hook"],
            },
        },
    },
    "required": ["chapters", "summary", "titles", "clips"],
}

MERGE_PROMPT = """These are chapter candidates found in consecutive parts of one {kind} that is
{duration} long. Some adjacent candidates describe the same topic because the parts overlap.
Return the final chapter list: merge duplicates (keep the earlier timestamp), keep timestamps
exactly as given, keep roughly one chapter every {spacing}, and make titles consistent in style.
Also write the summary, {n_titles} title ideas and keep the best {n_clips} clips.

Candidates (JSON):
{candidates}
"""
