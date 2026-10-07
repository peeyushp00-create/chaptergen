# Changelog

## 0.1.0

First release.

- Transcribe audio and video with Gemini (Hindi, Hinglish and other languages kept as spoken)
- Or start from captions you already have: SRT, VTT, timestamped text, or a saved transcript
- Chapters, summary, title ideas and Shorts/Reels clip ideas in one request
- YouTube chapter rules enforced in code: 0:00 start, ascending, 10-second minimum, at least 3
- Model timestamps snapped to real sentence starts; long recordings chunked and merged
- `chaptergen eval`: precision / recall / F1 / offset against human-written chapters
- `chaptergen web`: local drag-and-drop page
- Optional ffmpeg: video is reduced to a small audio track before upload
