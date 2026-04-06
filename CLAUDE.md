# CLAUDE.md — Whisper AI Subtitle App

This file is the authoritative development reference for Claude Code.
**Update this file whenever a new feature is completed.**

---

## Project Overview

A browser-based web application that uses OpenAI Whisper for automatic speech recognition (ASR), converting spoken audio/video into Traditional Chinese subtitles in real time. The app supports both pre-recorded file upload and live camera/screen capture.

**Tech stack:**
- Backend: Python 3.8+, Flask, Flask-SocketIO, eventlet, openai-whisper, faster-whisper (optional)
- Frontend: Vanilla HTML/CSS/JS (single file, no build step), Socket.IO client
- Audio extraction: FFmpeg (system dependency)

---

## Repository Structure

```
Whisper 開發/
├── backend/
│   ├── app.py              # Flask server — REST API + WebSocket events
│   └── requirements.txt    # Python dependencies
├── frontend/
│   └── index.html          # Complete single-page web app
├── setup.sh                # One-shot environment setup
├── start.sh                # Start backend + open browser
├── CLAUDE.md               # This file
└── README.md               # User-facing documentation (Traditional Chinese)
```

---

## Architecture

### Backend (`backend/app.py`)

**Model loading (`get_model`)**
- Maintains two separate caches: `_openai_model_cache` and `_faster_model_cache`
- `backend='auto'` prefers `faster-whisper` when installed (int8 quantisation, 4–8× faster)
- Falls back to `openai-whisper` gracefully if `faster-whisper` is not installed
- Thread-safe via `_model_lock`

**Transcription pipeline (`transcribe_with_segments`)**
- For video files (mp4/mov/avi/mkv/webm): extracts 16kHz mono WAV via FFmpeg first
- Emits `subtitle_segment` WebSocket events per segment as they arrive (streaming UX)
- Supports both faster-whisper and openai-whisper output formats

**Live transcription (`transcribe_chunk`)**
- Receives base64-encoded WebM audio blobs from browser every 3 seconds
- Saves to temp file, transcribes, emits `live_subtitle` events back to client
- Uses `tiny` model by default for lowest latency

**WebSocket events (server → client)**
| Event | Payload | When |
|---|---|---|
| `connected` | `{sid}` | On connect |
| `model_loading` | `{model, status}` | Model load started |
| `model_ready` | `{model, status}` | Model load complete |
| `model_error` | `{error}` | Model load failed |
| `transcription_status` | `{status, message}` | Extraction/transcription phase |
| `subtitle_segment` | `{id, start, end, text, words[]}` | Each segment as it's ready |
| `transcription_complete` | `{text, language, segment_count}` | All done |
| `transcription_error` | `{error}` | Any failure |
| `live_subtitle` | `{text, start, end, timestamp}` | Live mode subtitle |

**WebSocket events (client → server)**
| Event | Payload |
|---|---|
| `load_model` | `{model}` |
| `live_audio_chunk` | `{audio: base64, model}` |

**REST endpoints**
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Server status, loaded models |
| GET | `/api/models` | Available model list |
| POST | `/api/transcribe` | Async file transcription (streams via WS) |
| POST | `/api/transcribe/sync` | Sync transcription (small files) |

**Important implementation notes**
- Always capture `request.sid` before spawning a background thread — Flask request context is not available inside threads
- `socketio.emit(..., room=sid)` must be used from threads, never bare `emit()`
- Temp files are cleaned up in `finally` blocks

### Frontend (`frontend/index.html`)

Single self-contained file. No build step required.

**Subtitle sync (file playback)**
- `timeupdate` event on `<video>` scans `segments[]` array each tick
- Display window: `videoTime >= segment.start + delay` AND `videoTime <= segment.end + delay + 0.3`
- `delay` is the user-controlled slider (0–5 s); positive delay shifts subtitles to appear later, compensating for processing lag

**Live audio capture**
- `MediaRecorder` records the audio track at 3-second intervals
- Each blob is base64-encoded in chunks of 8192 bytes (avoids stack overflow on large buffers)
- Sent to server via `live_audio_chunk` WebSocket event
- Received `live_subtitle` events are displayed after `subtitleDelay` ms

**Export formats**
- SRT: standard subtitle format, compatible with most video players
- VTT: WebVTT format, native HTML5 `<track>` element format
- TXT: plain transcript, one line per segment

---

## Development Guidelines

- Do not add a build system unless the frontend grows to multiple files requiring it
- Keep all frontend logic in `index.html` until complexity warrants splitting
- All new backend routes must handle errors and return JSON `{error: "..."}` with appropriate HTTP status
- New WebSocket events must be documented in the table above
- The `get_model()` function must remain the single entry point for model loading
- Test both faster-whisper and openai-whisper code paths when modifying transcription logic

---

## Completed Features

### v1.0 — Initial Build
- File upload mode: drag-and-drop or file picker, supports MP4/MOV/AVI/MKV/WebM/MP3/WAV/M4A/AAC/FLAC/OGG
- Live mode: camera or screen share via `getUserMedia` / `getDisplayMedia`
- Real-time Traditional Chinese subtitles overlaid on video
- Subtitle delay slider (0–5 s) for audio/subtitle sync compensation
- Subtitle display duration control (1–10 s)
- Subtitle font size control (14–48 px)
- Segment-by-segment transcript panel with timestamps
- Model selector: tiny / base / small / medium / large / turbo
- Model pre-load button
- SRT export
- TXT export

### v1.1 — Bug Fixes & Reliability
- Fixed subtitle sync direction: delay now correctly shifts subtitles *later* (was inverted)
- Removed duplicate `timeupdate` event listeners accumulating per segment
- Fixed `emit()` called from background thread without request context (captured `sid` before thread spawn)
- Fixed large audio buffer base64 conversion stack overflow (chunked loop, 8192 bytes per call)
- Moved `import base64` to module level

### v1.2 — faster-whisper & WebVTT
- Added optional `faster-whisper` backend (4–8× faster, int8 quantised, auto-selected when installed)
- Dual model cache: separate caches for openai-whisper and faster-whisper
- Fixed live chunk temp file extension (`.webm` instead of `.wav`)
- Fixed health endpoint referencing deleted `_model_cache` variable
- Added WebVTT (`.vtt`) export format
