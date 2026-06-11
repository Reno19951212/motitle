# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This file is the authoritative development reference for Claude Code.
**Update this file whenever a new feature is completed.**

---

## Development Commands

### Prerequisites

Python 3.8+ (3.11 recommended) and FFmpeg must be on PATH before running `setup.sh`.

**Windows** — install via winget (the default `python` in PATH is a Microsoft Store stub; it does not work):
```powershell
winget install --id Python.Python.3.11 -e --source winget
winget install --id Gyan.FFmpeg -e --source winget
```
Restart the shell after install so PATH updates take effect.

**macOS**: `brew install python@3.11 ffmpeg`
**Linux (apt)**: `sudo apt-get install python3 python3-venv ffmpeg`

### Setup
```bash
./setup.sh                          # First-time: creates backend/venv, installs deps
```

> On Windows, `whisper-streaming` (plus its transitive `pyalsaaudio` + `opus-fast-mosestokenizer`) fails to build — ALSA is Linux-only and the Moses tokenizer needs a C++ toolchain. Streaming mode was removed in v2.0 and the import is guarded in `app.py`, so install the other packages directly:
> ```bash
> source backend/venv/Scripts/activate   # Windows Git Bash path
> pip install openai-whisper faster-whisper flask flask-cors flask-socketio \
>   werkzeug eventlet numpy torch torchaudio ffmpeg-python python-socketio \
>   gevent gevent-websocket pysbd opencc-python-reimplemented librosa soundfile
> ```

### Windows CUDA runtime (GPU acceleration)

If you want GPU transcription on Windows and hit `Library cublas64_12.dll is not found or cannot be loaded`, install the CUDA runtime via pip (venv-only, no system install):
```bash
pip install nvidia-cublas-cu12==12.4.5.8 nvidia-cudnn-cu12
```
`app.py` registers these DLL directories on startup (guarded, Windows-only). After install, Profile `device: "auto"` or `"cuda"` will just work.

- The full NVIDIA CUDA Toolkit is **not** required — ctranslate2 4.7.x only needs `cublas64_12.dll` + `cudnn64_9.dll` runtime, which those two pip wheels provide.
- Do **not** use `winget install Nvidia.CUDA` — the winget package is v13, whose DLLs are named `cublas64_13.dll` and will not satisfy ctranslate2 4.7.
- Full README troubleshooting (three routes: pip / CPU-only / full Toolkit) is in README.md under "Windows 常見問題".

### V6 Qwen3 subprocess timeout (`R5_QWEN3_TIMEOUT_SEC`)

V6 pipelines spawn a py3.11 Qwen3-ASR subprocess via `backend/engines/transcribe/qwen3_vad_engine.py`. Since v3.20 the parent enforces a wall-clock timeout to bound any future subprocess hang or runaway model load. Env var `R5_QWEN3_TIMEOUT_SEC` (default `900` = 15 min, ~1.5× the healthy 4-6 min broadcast budget) controls the cap. On expiry the parent runs `proc.terminate()` → 3s grace → `proc.kill()` and raises `RuntimeError`, which propagates to `JobQueue` and marks the job `status='failed'` with the timeout message in `error_msg`. The poison-pill retry cap (`R5_MAX_JOB_RETRY=3` from v3.13) prevents auto-retry loops. Set in `backend/.env` for clips that legitimately exceed 15 min wall time:
```bash
R5_QWEN3_TIMEOUT_SEC=1800   # 30 min cap for longer broadcasts
```

### Running the backend
```bash
# Via start.sh (recommended — activates venv + opens browser)
./start.sh

# Manually (from backend/)
source venv/bin/activate            # macOS/Linux
source venv/Scripts/activate        # Windows (Git Bash)
python app.py                       # Runs on http://localhost:5001
```

### Running tests
```bash
cd backend
source venv/bin/activate

pytest tests/                       # Run all tests
pytest tests/test_asr.py            # Run a single test file
pytest tests/test_asr.py::test_whisper_engine_get_info   # Run a single test
pytest tests/ -k "not api_"         # Skip Flask-dependent API tests
```

> Note: API-level tests (`test_api_*`) require `flask` in the active venv. Unit tests run without it.

**CI**: `.github/workflows/ci.yml` runs the 4 cross-platform abstraction unit tests (`test_platform_backend`, `test_ffmpeg_locate`, `test_asr_profiles_platform`, `test_qwen_venv_path`) on `ubuntu-latest` + `macos-14` via GitHub Actions — pure-logic, no GPU/model deps, just `pytest`.

### curl smoke tests
```bash
curl http://localhost:5001/api/health
curl http://localhost:5001/api/asr/engines
curl http://localhost:5001/api/asr/engines/whisper/params
curl http://localhost:5001/api/translation/engines/mock/models
```

---

## Project Overview

A browser-based broadcast subtitle production pipeline that converts English video content into Traditional Chinese (Cantonese or formal) subtitles. The pipeline: English ASR → Translation → Proof-reading → Burnt-in subtitle output (MP4/MXF).

**Tech stack:**
- Backend: Python 3.8+, Flask, Flask-SocketIO, faster-whisper/openai-whisper, Ollama (local LLM)
- Frontend: Vanilla HTML/CSS/JS (no build step), Socket.IO client
- ASR: Whisper (via faster-whisper, openai-whisper, or mlx-whisper on Apple Silicon), Qwen3-ASR and FLG-ASR stubs for production
- Translation: Ollama + Qwen2.5/3.5 (local or cloud), OpenRouter (Claude/GPT/Gemini/…), Mock engine for dev/testing
- Rendering: FFmpeg (ASS subtitle burn-in)
- Audio extraction: FFmpeg (system dependency)

---

## Repository Structure

```
motitle/
├── backend/
│   ├── app.py                  # Flask server — REST API + WebSocket events
│   ├── profiles.py             # Profile management (ASR + Translation model routing)
│   ├── beta_mode.py            # Beta test mode flag + OpenRouter API key mgmt
│   ├── glossary.py             # Glossary management (EN→ZH term mappings)
│   ├── renderer.py             # Subtitle renderer (ASS generation + FFmpeg burn-in)
│   ├── asr/                    # ASR engine abstraction
│   │   ├── __init__.py         # ASREngine ABC + factory + Word TypedDict
│   │   ├── whisper_engine.py   # faster-whisper / openai-whisper (incl. word_timestamps)
│   │   ├── mlx_whisper_engine.py # MLX-Whisper for Apple Silicon (word_timestamps supported)
│   │   ├── segment_utils.py    # split_segments() post-processor (sentence-boundary split, word partitioning)
│   │   ├── qwen3_engine.py     # Qwen3-ASR stub
│   │   └── flg_engine.py       # FLG-ASR stub
│   ├── translation/            # Translation engine abstraction
│   │   ├── __init__.py         # TranslationEngine ABC + factory
│   │   ├── ollama_engine.py    # Ollama/Qwen + few-shot prompts + optional Pass 2 enrichment
│   │   ├── openrouter_engine.py # OpenRouter (OpenAI-compatible): Claude / GPT / Gemini / etc.
│   │   ├── mock_engine.py      # Mock engine for dev/testing
│   │   ├── crosslang_mt.py     # Generic cross-lang MT (per-segment 1:1, injected llm_call) — output_lang flow
│   │   ├── sentence_pipeline.py # Sentence-aware merge/redistribute + time-gap guard
│   │   ├── alignment_pipeline.py # Phase 6: LLM-anchored alignment (marker injection + fallback)
│   │   └── post_processor.py   # Subtitle length / hallucination post-checks
│   ├── output_lang_router.py   # route_output / whisper_direct_params / content_asr_lang (output_lang routing)
│   ├── output_lang_aligned.py  # O1 1:1 paired bilingual grid (derive_aligned_output / build_aligned_bilingual)
│   ├── output_lang_postprocess.py # apply_script (OpenCC) / clause_split_all / formal_refine
│   ├── output_lang_persist.py  # build_output_translations (by_lang + {lang}_text mirror)
│   ├── language_config.py      # Per-language ASR/translation parameters
│   ├── config/                 # Configuration files
│   │   ├── settings.json       # Active profile pointer
│   │   ├── profiles/           # Profile JSON files
│   │   ├── glossaries/         # Glossary JSON files
│   │   ├── mt_style_prompts/   # racing.txt / sportsnews.txt / generic.txt (mt_style picker)
│   │   └── languages/          # Per-language config (en.json, zh.json)
│   ├── tests/                  # Test suite
│   ├── data/                   # Runtime: uploads, registry, renders (gitignored)
│   └── requirements.txt        # Python dependencies
├── frontend/
│   ├── index.html              # Main dashboard — upload, transcribe, translate
│   ├── proofread.html          # Proof-reading editor — review, edit, approve, render
│   ├── user.html               # Account page — 左側分頁導航（我的帳戶 / 用戶管理 / 審計日誌）、全闊 panes、用戶管理 inline 操作（刪除確認 / 重設密碼 / 備註）、結構化審計日誌（可展開詳情 + 搜尋/篩選）；per-user remarks 由管理員編輯、用戶可喺「我的帳戶」查看自己嘅備註。
│   ├── Glossary.html           # Glossary management page
│   ├── Files.html              # Files library page (login-required)
│   ├── login.html              # Login form
│   └── js/
│       ├── font-preview.js     # Shared module: syncs subtitle overlay with active Profile font config
│       ├── queue-panel.js      # Right-side job queue panel (3s /api/queue poll)
│       ├── step-diagram.js     # Kind-agnostic step-diagram renderer
│       └── files-page.js       # Files.html logic
├── docs/superpowers/           # Design specs and implementation plans
├── docs/deployment/            # Operator runbooks
│   └── macos-server.md         # macOS Apple Silicon server-appliance install (launchd)
├── packaging/macos/            # LaunchDaemon plists + launcher + service management CLI
├── setup.sh                    # One-shot environment setup
├── setup-mac.sh                # macOS Apple Silicon server setup (deps + venv + admin user + launchd)
├── start.sh                    # Start backend + open browser
├── CLAUDE.md                   # This file
└── README.md                   # User-facing documentation (Traditional Chinese)
```

> **macOS server-appliance deployment** — `setup-mac.sh` installs Homebrew deps, mlx-whisper venv, bootstraps the admin user, writes `backend/.env` (FLASK_SECRET_KEY), generates a self-signed HTTPS cert, pulls `qwen3.5:35b-a3b-mlx-bf16`, and optionally installs two LaunchDaemons (`com.motitle.server` + `com.motitle.ollama`) via `packaging/macos/motitle-service.sh`. Full operator runbook: [docs/deployment/macos-server.md](docs/deployment/macos-server.md).

---

## Architecture

### Pipeline Flow

```
English Video (MP4/MXF)
    │
    ▼ FFmpeg audio extraction
English Audio (16kHz WAV)
    │
    ▼ ASR Engine (Whisper / Qwen3-ASR / FLG-ASR)
English Transcript [{start, end, text}]
    │
    ▼ Translation Engine (Ollama Qwen / Mock) + Glossary
Chinese Translation [{start, end, en_text, zh_text}]
    │
    ▼ Proof-reading Editor (human review + edit + approve)
Approved Translations
    │
    ▼ Subtitle Renderer (ASS + FFmpeg burn-in)
Output Video with burnt-in Chinese subtitles (MP4 / MXF ProRes)
```

### Backend Modules

**`app.py`** — Flask server, REST API, WebSocket events, file registry, orchestration

**`profiles.py`** — Profile CRUD. Each profile defines ASR engine + Translation engine + Font config. JSON file storage in `config/profiles/`. One profile is active at a time.

**`glossary.py`** — Glossary CRUD. EN→ZH term mappings injected into translation prompts. JSON file storage in `config/glossaries/`. CSV import/export supported.

**`renderer.py`** — Generates ASS subtitle files from approved translations + font config, then invokes FFmpeg to burn subtitles into video. Supports MP4 (H.264) and MXF (ProRes 422 HQ) output.

**`asr/`** — Unified ASR interface. `ASREngine` ABC with `transcribe(audio_path, language)` method returning `[{start, end, text, words: [Word]}]`. Factory function creates the correct engine from profile config. WhisperEngine (faster-whisper / openai-whisper) and MLXWhisperEngine are fully implemented; Qwen3 and FLG are stubs. Optional `word_timestamps` flag in Profile ASR config enables DTW word-level alignment used by the LLM-anchored alignment pipeline.

**`translation/`** — Unified translation interface. `TranslationEngine` ABC with `translate(segments, glossary, style, batch_size, temperature, progress_callback, parallel_batches)` method. Implementations:
- **`OllamaTranslationEngine`** — Local Ollama + Qwen2.5/3.5 (incl. cloud variants via `ollama signin`). Uses few-shot prompts with sentence scope context and optional Pass 2 enrichment (`translation_passes: 2`).
- **`OpenRouterTranslationEngine`** — Subclasses Ollama engine, overrides only the HTTP call to hit OpenRouter's OpenAI-compatible `/chat/completions`. Inherits all batching/retry/glossary/prompt logic. Bearer-auth, 9 curated models (Claude Opus/Sonnet/Haiku, GPT-4o/mini, Gemini 2.5, DeepSeek, Qwen, Llama) plus user-supplied free-form model ids.
- **`MockTranslationEngine`** — dev/testing.
- **`sentence_pipeline.py`** — `merge_to_sentences` (pySBD + time-gap guard, `MAX_MERGE_GAP_SEC=1.5`) → translate → `redistribute_to_segments`. Opt-in via `use_sentence_pipeline: true` or `alignment_mode: "sentence"`.
- **`alignment_pipeline.py`** — `translate_with_alignment`: sentence merge + LLM marker injection (`[N]` anchors), LLM places markers in Chinese output, then splits back to original ASR segments. Chinese-punctuation-snap fallback if marker parsing fails. Opt-in via `alignment_mode: "llm-markers"`.
- **`post_processor.py`** — `[LONG]` detection (>28 chars/line) + hallucination heuristic (>40 chars likely drift).

**`language_config.py`** — Per-language ASR segmentation params (max_words_per_segment, max_segment_duration) and translation params (batch_size, temperature). JSON file storage in `config/languages/`. Validated ranges enforced.

### Backend (`app.py`)

**Model loading (`get_model`)** — Legacy path for direct Whisper model loading. Maintains dual caches for faster-whisper and openai-whisper. Used when active profile doesn't specify a whisper ASR engine.

**Transcription pipeline (`transcribe_with_segments`)** — Extracts audio from video via FFmpeg, then delegates to ASR engine from active profile. Reads language from profile config. Emits `subtitle_segment` WebSocket events per segment. After transcription completes, auto-triggers translation via `_auto_translate()`.

**Auto-translation (`_auto_translate`)** — Called after transcription. Reads active profile's translation config, loads glossary if configured, calls translation engine, stores results in file registry.

**WebSocket events (server → client)**
| Event | Payload | When |
|---|---|---|
| `connected` | `{sid}` | On connect |
| `model_loading` | `{model, status}` | Model load started |
| `model_ready` | `{model, status}` | Model load complete |
| `model_error` | `{error}` | Model load failed |
| `transcription_status` | `{status, message}` | Extraction/transcription phase |
| `subtitle_segment` | `{id, start, end, text, words[], progress, eta_seconds, total_duration}` | Each segment as it's ready |
| `transcription_complete` | `{text, language, segment_count}` | Transcription done |
| `transcription_error` | `{error}` | Any failure |
| `file_added` | `{id, original_name, ...}` | New file uploaded |
| `file_updated` | `{id, status, translation_status, ...}` | File status changed |
| `profile_updated` | `{font: {family, size, color, outline_color, outline_width, margin_bottom}}` | Active profile activated or font config updated |
| `translation_progress` | `{file_id, completed, total, percent, elapsed_seconds}` | Each translation batch completes |
| `pipeline_timing` | `{file_id, asr_seconds: float\|null, translation_seconds: float, total_seconds: float}` | Translation completes (auto-translate path only) |
| `pipeline_segment` | `{file_id, idx, total, text, lang}` | V6 last-refiner emits each refined segment (live caption) |
| `pipeline_progress` | `{file_id, pipeline_kind, stages[], stage_index, stage_state, pct, stage_label}` | Unified progress contract (all pipeline kinds; backward-compatible, add-only) |
| `pipeline_stage_start` / `pipeline_stage_progress` / `pipeline_stage_done` | V6 native stage events (routed through `report_from_v6_stage`) | V6 DAG stage transitions |

**WebSocket events (client → server)**
| Event | Payload |
|---|---|
| `load_model` | `{model}` |

**REST endpoints**
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Server status, loaded models |
| GET | `/Files.html` | Files library page (login-required static page) |
| GET | `/api/models` | Available Whisper model list |
| POST | `/api/transcribe` | Upload + async transcription → auto-translate. Form fields: `output_languages` (JSON, 1-2 of `{yue,zh,cmn,en,ja}` → forces `active_kind=output_lang`), `source_language` (`{yue,cmn,en,ja}`), `script` (`trad`/`simp`, default `trad`), `mt_style` (`racing`/`sportsnews`/`generic`), `glossary_ids` (JSON array, ordered glossary ids), `glossary_llm` (`"1"`/`"0"`, default `"1"`) |
| GET | `/api/files` | List all uploaded files with status（2026-06-10 起每檔附 `output_languages/source_language/script/mt_style/glossary_ids/glossary_llm` — 重新處理 popup 預填用） |
| GET | `/api/files/<id>/media` | Serve original media file |
| GET | `/api/files/<id>/subtitle.<fmt>` | Download subtitle (srt/vtt/txt)；接 `?source=` + `?order=` query params |
| PATCH | `/api/files/<id>` | Update file-level settings (subtitle_source / bilingual_order) |
| GET | `/api/files/<id>/segments` | Get transcription segments |
| PATCH | `/api/files/<id>/segments/<seg_id>` | Update segment text |
| DELETE | `/api/files/<id>` | Delete file |
| GET | `/api/profiles` | List all profiles |
| POST | `/api/profiles` | Create profile |
| GET | `/api/profiles/active` | Get active profile |
| GET | `/api/profiles/<id>` | Get profile |
| PATCH | `/api/profiles/<id>` | Update profile |
| DELETE | `/api/profiles/<id>` | Delete profile |
| POST | `/api/profiles/<id>/activate` | Set active profile |
| GET | `/api/settings/font` | Global subtitle-font preset (used by render + live preview when no active profile — V6 / output_lang) |
| PUT | `/api/settings/font` | Update the global font preset (settings.json `font`); emits `profile_updated` |
| GET | `/api/fonts` | List uploaded subtitle fonts (`fonts: [{file, family}]`) + `system_fonts: [...]` (CJK families the burn-in renderer can actually use on this host — daemon-safe; drives the font picker + `@font-face` injection) |
| POST | `/api/fonts` | Upload a custom subtitle font (.ttf/.otf; validates extension + size ≤32MB + sfnt magic bytes); returns `{file, family}` (family read from the font `name` table via fontTools) |
| DELETE | `/api/fonts/<filename>` | Delete an uploaded custom font (resolved-path confined to `assets/fonts/`) |
| GET | `/fonts/<filename>` | Serve a font file (for `@font-face` live preview + libass `:fontsdir` burn-in) |
| GET | `/api/asr/engines` | List ASR engines with availability |
| GET | `/api/asr/engines/<name>/params` | Get param schema for ASR engine |
| POST | `/api/translate` | Translate a file's segments |
| POST | `/api/files/<id>/translate-second` | V6 only — on-demand 加第二語言（body `{lang}`；202 + job_id；非 V6 / 同源語言 / 無方向 template → 400） |
| GET | `/api/translation/engines` | List translation engines with availability |
| GET | `/api/translation/engines/<name>/params` | Get param schema for translation engine |
| GET | `/api/translation/engines/<name>/models` | List available models for translation engine |
| GET | `/api/glossaries` | List all glossaries |
| POST | `/api/glossaries` | Create glossary |
| GET | `/api/glossaries/<id>` | Get glossary with entries |
| PATCH | `/api/glossaries/<id>` | Update glossary |
| DELETE | `/api/glossaries/<id>` | Delete glossary |
| POST | `/api/glossaries/<id>/entries` | Add glossary entry |
| PATCH | `/api/glossaries/<id>/entries/<eid>` | Update entry |
| DELETE | `/api/glossaries/<id>/entries/<eid>` | Delete entry |
| POST | `/api/glossaries/<id>/import` | Import CSV |
| GET | `/api/glossaries/<id>/export` | Export CSV |
| POST | `/api/files/<id>/glossary-scan` | Scan translations for glossary violations (string match) |
| POST | `/api/files/<id>/glossary-apply` | Apply glossary corrections via LLM smart replacement |
| POST | `/api/files/<id>/glossary-reapply` | output_lang only — 重新套用詞彙表，由 cached content base 1:1 re-derive（無 re-ASR）；非 output_lang / 無 content base / 未知 glossary → 400 |
| POST | `/api/files/<id>/segments/<pos>/split` | output_lang only — split cue at 0-indexed `pos` into two; body `{mode: "ai"\|"mechanical"}` (ai = LLM semantic split, mechanical = 50/50 midpoint + duplicate text); syncs segments/translations/aligned_bilingual/content_asr_segments; 400 non-output_lang / <0.4s, 409 render-in-progress / concurrent-edit |
| POST | `/api/files/<id>/segments/<pos>/merge-next` | output_lang only — merge cue `pos` with `pos+1` (join text, union time, reset pending); 400 last-cue / non-output_lang, 409 render-in-progress |
| POST | `/api/files/<id>/ai-edit` | output_lang only — AI 輔助修改（suggest-only）：body `{pos, role: first\|second, instruction ≤500字}`；LLM 按指令重寫該段該語言字幕，回 `{text, source_text}`；**唔寫 registry**（前端經 PATCH /translations/<idx> 套用）；400 非 output_lang/壞參數、404 段落唔存在、422 LLM 輸出無法解析、502 LLM 冇回應 |
| POST | `/api/files/<id>/transcribe` | 重跑整條 pipeline。**2026-06-10 起接受 optional body** `{output_languages, source_language, script, mt_style, glossary_ids, glossary_llm}`（重新處理 popup — 覆寫檔案設定並 force output_lang；驗證同 /api/transcribe 一致）；無 body 時 output_lang 檔保留自有設定、其他 kind re-snapshot 現時 active；AI Rerun 進行中 409 |
| PATCH | `/api/files/<id>/segments/<pos>/timing` | output_lang only — 調整 cue In/Out：body `{in_ms?, out_ms?}`（絕對毫秒，至少一個）；**roll-on-contact**（相連邊界連鄰段一齊郁，0.4s floor）、gap clamp 永不重疊；四庫同步（translations/segments/content_asr_segments/aligned_bilingual）；**批核狀態保留**；回 `{rows:[{idx,start,end}…], clamped}`；409 render/rerun 中 |
| POST | `/api/files/<id>/rerun` | output_lang only — AI Rerun：body `{positions:[int,…]}`；對每段重截音訊（短 cue pad 至 ≥1.2s）→ mlx-whisper 重轉錄 → derive 所有輸出語言（pass/refine/MT+OpenCC+詞彙表）→ 直接寫入並 reset pending；202 `{job_id,total}`；400 非 output_lang/壞 positions、409 渲染中/已有 rerun |
| GET | `/api/reruns/<job_id>` | Rerun job 進度 `{status, total, done, current_pos, done_positions, failed_positions}`（in-memory，仿 render job） |
| DELETE | `/api/reruns/<job_id>` | 取消 rerun（現段做完即停，已完成段保留） |
| GET | `/api/languages` | List language configs |
| GET | `/api/languages/<id>` | Get language config |
| PATCH | `/api/languages/<id>` | Update language config |
| GET | `/api/files/<id>/translations` | Get translations with approval status |
| PATCH | `/api/files/<id>/translations/<idx>` | Update translation text (auto-approve) |
| POST | `/api/files/<id>/translations/<idx>/approve` | Approve single translation |
| POST | `/api/files/<id>/translations/<idx>/unapprove` | Flip a single translation back to `pending` |
| POST | `/api/files/<id>/translations/approve-all` | Approve all pending |
| GET | `/api/files/<id>/translations/status` | Get approval progress |
| POST | `/api/render` | Start subtitle burn-in render job (format: `mp4` / `mxf` / `mxf_xdcam_hd422`)；接 `subtitle_source` + `bilingual_order`；response 含 `warning_missing_zh` |
| GET | `/api/renders/<id>` | Check render job status |
| DELETE | `/api/renders/<id>` | Cancel an in-flight render job (sets `cancelled` flag, status flips to `'cancelled'` on completion) |
| GET | `/api/renders/in-progress` | List active render jobs (optional `?file_id=` filter) — used by Proofread page to re-attach after reload |
| GET | `/api/renders/<id>/download` | Download rendered file |
| GET | `/api/license` | Get license status — `{state, unlocked, customer, plan, expires_at, days_left, grace_days, features, install_id}` (login-required; `install_id` is what the owner needs to mint a token) |
| POST | `/api/license/activate` | Admin-only — body `{token}`; verifies signature + machine-bind + not-past-grace BEFORE persisting, then returns the new status; 400 `invalid` / `wrong_machine` / `expired` |
| POST | `/api/license/deactivate` | Admin-only — clear the installed token (re-locks the app); audits `license.deactivate` |

> Admin `POST /api/admin/users` (create) and `POST /api/admin/users/<id>/reset-password` now return **400** (not 500) on a weak/empty password — the ValueError from password-strength validation is mapped to a clean 400. Policy (≥8 chars, not a common password) is shown in `user.html`.
>
> `PATCH /api/admin/users/<id>/remarks` — Admin-only: set a user's remarks (≤500 chars); audits `user.update_remarks`; 404 for unknown user / 400 for over-length.
>
> `GET /api/me` now also returns the caller's own `remarks` (read-only, shown on 我的帳戶 tab).
>
> `GET /api/admin/beta-mode` — Admin-only: Beta test mode status `{enabled, key_configured, llm_model}`.
>
> `PUT /api/admin/beta-mode` — Admin-only: toggle Beta mode and/or set OpenRouter API key; body `{enabled?: bool, api_key?: string}`; enabling without a key configured → 400.

### Frontend

**`index.html`** — Main dashboard. File upload, transcription with progress, auto-translation, profile selector, transcript display (auto-switches to Chinese when translations available), subtitle overlay on video playback.

**`proofread.html`** — Standalone proof-reading editor. Side-by-side layout: video player (left) + segment table (right). Inline editing of Chinese translations, per-segment and bulk approval, keyboard shortcuts, format picker (MP4/MXF), render with progress polling and download. Segment rail rows show **In + Out** timecodes (stacked); **clicking a row seeks the video** (`setCursor(i, true)`, same as the timeline). Layout is fill-chain robust — `.rv-b` uses `grid-template-rows: minmax(0,1fr)` and the `.proofread-*-pane` wrappers are flex columns so 詞彙表/字幕設定 panels scroll internally and the **時間軸 (waveform) stays pinned visible** at the bottom across all widths/zoom (was overflowing off-screen).

**Subtitle display default (2026-06-05, display-only)** — `resolveSubtitleSource` (in both `index.html` + `proofread.html`) defaults the **no-override** case to **雙語 when the file has ≥2 language tracks, else the single 第一語言** (read from `fileEntry.languages`). It is shown as the *selected* default (proofread dropdown + dashboard source-toggle highlight) and remains fully switchable to 第一/第二/雙語/auto. Only the display default changed; `pickSubtitleText` still mirrors the backend, and **backend `resolve_segment_text` (export/render) is unchanged** — export/render `auto` stays translation-preferred and overridable per-file.

### Pipeline Progress Contract（v3.20+）

統一 progress 訊號 contract，畀所有 pipeline kind（Profile / V6 / 未來）共用。詳見 [docs/superpowers/architecture/pipeline-progress-contract.md](docs/superpowers/architecture/pipeline-progress-contract.md)。

**核心 invariants**：
- 新增 pipeline kind 時，frontend `queue-panel.js` **零修改** — 全部變化集中喺 backend handler 或 adapter shim
- Native events (`subtitle_segment`, `translation_progress`, `pipeline_stage_*`) 唔可以改 payload，只可以加 field
- `queue_changed` 永遠 zero-payload，純 trigger refetch
- `pipeline_progress` payload schema backward-compatible，加 field OK，改名 / 刪 field 直接 break clients

**喺 backend 加新 pipeline kind 嘅 recipe**：[呢個 architecture 文件嘅 Section 9](docs/superpowers/architecture/pipeline-progress-contract.md#adding-a-new-pipeline-kind--step-by-step-recipe)。

---

## Development Guidelines

- Do not add a build system unless the frontend grows to multiple files requiring it
- All new backend routes must handle errors and return JSON `{error: "..."}` with appropriate HTTP status
- The `get_model()` function is the legacy model loading path; new code should use `asr/` engines via profiles
- Test both faster-whisper and openai-whisper code paths when modifying transcription logic
- Glossary entries are injected into translation prompts as few-shot examples
- Main process targets Python 3.8+ (use `List`/`Dict`/`Optional` from `typing` for 3.9 compat); the V6 Qwen3-ASR subprocess runs under a separate py3.11 venv

### Engine Architecture

- ASR 同 Translation 引擎完全解耦，透過 ABC + Factory 模式
- 新增引擎只需：實現 ABC 介面 + 加入 Factory mapping + 加入 tests
- 引擎選擇可由前端即時傳入，Profile 作為「快速預設」而非硬性綁定
- **ASREngine** 必須實現：`transcribe()`, `get_info()`, `get_params_schema()`
- **TranslationEngine** 必須實現：`translate()`, `get_info()`, `get_params_schema()`, `get_models()`

**注意**：output_lang pipeline **唔會**將 cross-family 翻譯路由經 `TranslationEngine` ABC — 佢用 `output_lang_router.route_output()` + `crosslang_mt.translate_segments()`（注入式 `llm_call`，per-cue 1:1）。`TranslationEngine` ABC + Factory 仍然管治 Profile-mode 翻譯。

### Validation-First Mode（修改 ASR / MT 必須遵守）

**任何涉及後端 ASR 引擎或翻譯引擎（MT, machine translation）嘅改動，必須先做 Validation-First 驗證，confirm empirical evidence 之後先寫 plan + 落代碼。** 唔可以憑感覺直接 ship。

**範圍涵蓋：**
- `backend/asr/*.py`（ASR engine ABC、Whisper / mlx-whisper / Qwen3-ASR / FLG / segment_utils）
- `backend/translation/*.py`（TranslationEngine ABC、Ollama / OpenRouter / Mock / sentence_pipeline / alignment_pipeline / post_processor）
- `backend/translation/crosslang_mt.py`（output_lang flow 嘅 generic cross-lang MT）
- `backend/output_lang_router.py`、`backend/output_lang_aligned.py`、`backend/output_lang_postprocess.py`（output_lang 路由 + 後處理鏈）
- `config/mt_style_prompts/{racing,sportsnews,generic}.txt`（mt_style prompt 改動）
- `backend/language_config.py` 嘅 `asr` / `translation` block
- Profile JSON 嘅 `asr` / `translation` block schema 變動
- 翻譯 prompt template 改動
- Char cap / segmentation algorithm（包括 split_segments、redistribute、line wrap 嘅 cap）

**Workflow（強制）：**
1. **每個假設逐個驗證** — 寫小型 prototype script 跑出量化結果（量度 char distribution / follow rate / hallucination rate / 等）
2. **記錄結果** — 結果寫入 `docs/superpowers/specs/YYYY-MM-DD-validation-tracker.md`，標 ✅ Validated / ❌ Rejected / ⚠️ Partial
3. **Confirm 之後** — 通過 user review 之後先進入 brainstorming → spec → plan
4. **Production stack 對齊** — 驗證測試使用同 production 一致嘅 model（ASR: mlx-whisper medium；MT: OpenRouter `qwen/Qwen3.5-35B-A3B`），唔可以用更細 model 推斷 production 行為（細 model 結論可作 directional reference 但唔可作為 production 決策依據）

**之前累積嘅 validation evidence：**
- v3.8 line-wrap 嘅 V0-V3 完整 11 項 empirical validation：[docs/superpowers/specs/2026-04-30-validation-tracker.md](docs/superpowers/specs/2026-04-30-validation-tracker.md)、[2026-04-30-line-wrap-design.md](docs/superpowers/specs/2026-04-30-line-wrap-design.md)
- 已 reject 嘅方案（max_new_tokens cap、jieba 切繁體、pre-segment + per-cue translate、Direct subtitle JSON）— 任何將來方案如果踩返同樣 trap，要 cite 返已知 evidence 解釋點解仍要 retry，否則直接 reject

### Verification Gates

每個功能完成後必須通過 4 個 gate（詳見 `docs/PRD.md` 第 6 節）：
1. **代碼質素** — pytest 全部 PASS，有對應 test，無 hardcode
2. **功能正確性** — curl 測試 API，前後端格式一致，edge cases 處理
3. **整合驗證** — 相關 pipeline 走通，無 regression
4. **文檔完整性** — CLAUDE.md + README.md 已更新

可選使用 `/ralph-loop` 自動化閉環迭代（適用於多步驟整合工作）。

### Mandatory documentation updates on every feature change

Whenever a new feature is completed or existing functionality is modified, you **must** update:

1. **CLAUDE.md** (this file) — Architecture, REST endpoints, current state (full history → [docs/history.md](docs/history.md))
2. **README.md** (user-facing, **must be written in Traditional Chinese**)
3. **docs/PRD.md** — Update feature status markers (📋 → ✅). Note: PRD.md predates the `output_lang` pipeline and may be stale for pipeline features — treat its pipeline sections as historical and prefer this file's Current State section.
4. **Validation-First tracker** — for any ASR/MT change, a `docs/superpowers/specs/YYYY-MM-DD-...-validation-tracker.md` recording empirical results (✅ Validated / ❌ Rejected / ⚠️ Partial)
5. **Design + plan pair** — a matching `docs/superpowers/specs/...-design.md` and `docs/superpowers/plans/...-plan.md`

---

## Current State & Recent Highlights

Full chronological feature/version history → [docs/history.md](docs/history.md).

This section summarises the CURRENT behaviour a developer needs; older entries live in history.md.

### Token Licensing (on-prem offline activation)

- **What it is**: a fully offline, per-deployment software licence. The whole app is gated behind a signed Ed25519 token so an unlicensed install is locked (read-only auth + licence-management surface only). No phone-home — verification is 100% local against an embedded public key.
- **Modules** (`backend/licensing/`, each independently testable):
  - `token.py` — pure crypto: `sign(payload, sk_b64)` / `verify_signature(token) -> claims` / `InvalidToken`. Canonical-JSON payload, Ed25519 signature, no I/O.
  - `keys.py` — the embedded `PUBLIC_KEY_B64` (baked by `scripts/licensing/keygen.py`). The ONLY trust anchor shipped in the binary.
  - `license_state.py` — the only module that touches `config/license.json`. Owns `install_id` (random per-machine uuid), the installed `token`, and a `last_seen` monotonic ratchet (anti clock-rollback). Atomic temp-file writes; throttled `last_seen` persistence.
  - `validator.py` — pure decision logic: `evaluate() -> LicenseStatus(state, unlocked, …)`. States: `active` / `grace` / `expired` / `wrong_machine` / `invalid` / `none`. **Fail-closed** (any error → `invalid`/locked). Honours a 300s clock-skew window and a per-token `grace_days` (default 30) after `exp`.
  - `gate.py` — the only Flask-aware piece: a `before_request` enforcer. Allowlists health + auth (`/login`, `/logout`, `/api/me`) + the licence surface (`/api/license*`, `/license.html`) + `/js/`,`/css/` static. Everything else needs `evaluate().unlocked` → API calls get **403** `{error, license_state}`, page loads get redirected to `/license.html`. Test-only `R5_LICENSE_BYPASS` mirrors the `R5_AUTH_BYPASS` pattern (autouse in conftest so the existing API suites keep running; never set in production).
- **Install-id binding**: every token embeds the target machine's `install_id`; activating a token minted for a different machine returns `wrong_machine`. To move machines, re-issue against the new install-id.
- **Grace**: after `exp` the app stays `unlocked` for `grace_days` (banner shown) then flips to `expired`/locked.
- **Defense-in-depth**: AI workers call `_license_guard_or_raise()` and refuse to run (`RuntimeError`) if the licence is not unlocked, even if the HTTP gate were bypassed.
- **Owner CLI** (`scripts/licensing/`, NOT shipped to customers):
  - `keygen.py` — one-time keypair gen. Private key → `~/.motitle-licensing/private_key` (0600, never commit); public key pasted into `keys.py`.
  - `sign_license.py --customer … --plan {sub-3mo|sub-1yr|perpetual} --install-id …` — mints a token and appends a row to `issued_licenses.csv` (audit ledger; token stored only as a sha256 prefix).
- **Gitignored, per-deployment**: `backend/config/license.json` (the activated state) and `scripts/licensing/issued_licenses.csv` (the owner's ledger) are never committed.

### Output-language pipeline (primary flow)

- **`output_lang` is the primary user flow** (`active_kind='output_lang'`). User picks a video → upload popup → output languages; the old MT-job + V6-DAG dispatch is bypassed for this flow.
- **ASR language is SOURCE-DRIVEN** (`content_asr_lang(source)`: yue→`yue`, cmn→`zh`, en→`en`, ja→`ja`) — the output language NEVER changes the ASR. The content audio is transcribed ONCE; each output is a 1:1 derive (no index-merge): passthrough (same language) / `formal_refine` (書面語·普通話 from a Chinese base) / `crosslang_mt` (cross-family) + OpenCC 繁/簡 (`script`).
- **`source='yue'` runs entirely through the bound-base path** (`_run_output_lang_bound_base`, `do_clause_split=False` so the 口語 track is byte-identical to a direct yue transcription): one Whisper-`yue` base → derive 口語=passthrough / 書面語·普通話=refine / 英·日=MT. This **replaced the former Whisper-`zh`-direct for 書面語** (Validation-First 2026-06-04: meaning-error 77%→33%, register equally clean, confirmed by 2 independent judge models + a 3-flow live integration). `cmn`/`en`/`ja` sources keep the per-output whisper-direct path (source-driven == output-driven there). Cross-FAMILY files (e.g. +英文) use the same bound-base derive WITH clause-split.
- **`aligned_bilingual`** (O1) = the 1:1 paired base-grid (every cue carries all output languages, length == base) used for bilingual export/render so paired cues are construction-perfect aligned (no drift). Single-language `by_lang` / `{lang}_text` mirror data model is unchanged.

**Dev quick-reference** (full user-facing tables + prompt contents + flow examples → [README.md「輸出語言 Pipeline 路由」](README.md)):

- **Two models only**: ASR = **mlx-whisper large-v3** (`_output_lang_asr_override`); LLM = **Ollama `qwen3.5:35b-a3b-mlx-bf16`** (MoE, 35.1B total / **A3B = 3B active**) @ temp 0.3 (`_make_ollama_llm_call`) — **shared by MT + refiner**, only the prompt differs.
- **Derive matrix** (`output_lang_aligned.derive_mode(content, output)`): `yue`→{yue:pass, zh/cmn:**refine**, en/ja:**mt**}; `cmn`→{cmn:pass, zh:refine, yue/en/ja:mt}; `en`→{en:pass, else:mt}; `ja`→{ja:pass, else:mt}.
- **Prompt selection**:
  - **refine** → `output_lang_postprocess.formal_refine(segs, llm, style)`: `racing` → `config/prompt_templates_v5/refiner/zh_written_register_v6.json`; else (default) → `…/zh_written_register_generic.json` (neutral, forbids domain-term injection).
  - **mt** → `translation/crosslang_mt.build_mt_system_prompt(src, out, style)`: `en→zh/cmn` → `config/mt_style_prompts/{generic,racing,sportsnews}.txt`; else → `_MT_SYS` (generic broadcast MT) + `_ZH_WRITTEN_RULES` when out∈{zh,cmn}.
  - **pass** → no LLM; copy text, then OpenCC `apply_script` (Chinese outputs only).
- **Byte-for-byte preservation** (names/places/English/numbers) is a PROMPT RULE in both MT (`保留專有名詞`) and the refiners (rule 6), not a separate step.
- **Key files**: `output_lang_router.py` (`route_output`/`content_asr_lang`/`whisper_direct_params`) · `output_lang_aligned.py` (`derive_mode`/`derive_aligned_output`) · `output_lang_postprocess.py` (`formal_refine`/`apply_script`/`clause_split_all`) · `translation/crosslang_mt.py` (MT) · dispatch in `app.py` (`_run_output_lang` / `_run_output_lang_bound_base` / `_run_output_lang_second`).

### Upload-popup output-language selection rules (NEW)

- **First output language is LOCKED to the source-language family** via `syncFirstLangToSource` + `OL_FIRST_BY_SOURCE`: 英/普/日 → a single disabled option; **粵語 → choose 口語廣東話 OR 中文書面語, default 中文書面語**.
- **Second output language EXCLUDES any language in the SAME family as the source** (中文系 = `yue`/`cmn`/`zh`) via `OL_FAMILY` — this prevents same-family index-merge drift. To get two Chinese forms, run the file twice.
- **翻譯風格 picker** (馬會賽馬 / 體育新聞 / 通用, default 通用) → `mt_style`, drives BOTH the en→zh/cmn cross-lang MT prompt AND the 書面語 refiner (`formal_refine`): default/通用 → **neutral de-raced** refiner (`zh_written_register_generic.json`, forbids domain-term injection), 馬會賽馬 → racing refiner (`zh_written_register_v6.json`). Fixed 2026-06-04 — the refiner was previously always-racing and mistranslated non-racing content into racing (女事主打嚟 → 由女騎師策騎); validation in the yue-base tracker follow-up.

### Dashboard progress (#topProgress replaced the pipeline strip)

- Dashboard topbar shows **per-target-language processing progress** via `#topProgress` (`renderStatusCard` + `langProgressRows`), driven by the 3s `/api/queue` poll + a completion-refresh of `/api/files` (`{files:[...]}` shape). It REPLACED the pipeline strip.
- **mlx-whisper does not stream** → a frontend asymptotic TIME-ESTIMATE (1s ticker) advances `#topProgress` + the top card during ASR (snaps to 100% on real completion); 翻譯/other stages use the backend `pct`.

### MT prompt / style + ops fixes

- **`racing.txt` (馬會賽馬 style)** upgraded to the qwen3.5-validated HKJC-persona racing-register prompt, incl. a no-省略號-on-fragments rule + `crosslang_mt._clean` trailing-ellipsis strip.
- **Admin reset-password / create-user** map a weak/empty-password `ValueError` to a clean **400** (was 500); the policy (≥8 chars, not a common password) is shown in `user.html`.
- **Settings gear (`#settingsGearBtn`) REMOVED** from the dashboard topbar (only 管理 + 登出 in the user chip). 語言配置 management (`openLangConfigManageModal`) has NO UI entry anymore (its gear + the strip step-menu entry are both gone) — it is RETIRED; the remaining modal/function/strip JS is dead code.

### Proofread segment split / merge (output_lang)

- Each segment row has two left-side buttons — **AI 切割** (Ollama `qwen3.5:35b-a3b` splits every language at one aligned semantic/punctuation boundary; time split by content-language char ratio clamped 0.15–0.85) and **機械式硬切割** (50/50 midpoint, both halves duplicate the text) — plus a right-side **合併下一段**. Keyboard: `Ctrl+Shift+S` / `Ctrl+Shift+D` / `Ctrl+Shift+M`. Buttons are gated to output_lang rows only; rows under 0.4 s have split buttons disabled.
- Pure logic in `backend/segment_split.py`; routes in `app.py` (AI path snapshots under `_registry_lock`, calls the LLM lock-free, re-acquires + conflict-checks). The cascade keeps `segments`/`translations`/`aligned_bilingual`/`content_asr_segments` positionally aligned and renumbers `translations[].idx`, so SRT export / render / glossary-reapply / add-second-language stay correct. AI failure (bad JSON, reconstruction mismatch, empty source part) falls back to mechanical automatically.

### Proofread AI 輔助修改 (output_lang, NEW 2026-06-10)

- Detail panel 每個語言欄 label 行有「✦ AI」掣（output_lang 檔先出現；第二語言欄要檔案真係有第二語言）→ ae-* popup：修改前 → 快速 chips（對照翻譯／改更書面／改更口語／精簡句子，填入指令框可再修改）→ 生成（`POST /api/files/<id>/ai-edit`，suggest-only）→ 修改後預覽 → 套用（行現有 `PATCH /translations/<idx>` + `{text, role}`，auto-approve）。生成中閂 modal 再開另一段，舊 response 會被 identity-guard 棄置（唔會錯綁）。
- LLM 同 output_lang pipeline 共用 `_make_ollama_llm_call()`（qwen3.5:35b-a3b @0.3；Beta 模式自動行 OpenRouter）。Prompt／解析喺 `backend/ai_edit.py`（pure module，`tests/test_ai_edit.py` 19 tests）。Prompt 有 register-preserve 規則（Validation-First 2026-06-10：「精簡」曾將書面語 drift 去口語，已修 — 見 [docs/superpowers/specs/2026-06-10-proofread-ai-edit-validation-tracker.md](docs/superpowers/specs/2026-06-10-proofread-ai-edit-validation-tracker.md)）。
- **PATCH 同步修正**：`PATCH /translations/<idx>` 而家會同步 `aligned_bilingual[idx].by_lang[lang]`（之前單欄文字編輯唔會反映落雙語匯出／render — 已修，手動編輯同 AI 套用都受惠）。

### Proofread AI Rerun + 已批核綠色行 (output_lang, NEW 2026-06-10)

- **單段**：detail head「✓ 已批核」badge 左邊「⟳ AI Rerun」掣；**批量**：段落表 header「⟳ Rerun 未批核 (N)」掣（進度 `done/total` + 取消）。兩者同一條路：`POST /api/files/<id>/rerun {positions}` → in-memory job（`_rerun_jobs`，仿 `_render_jobs`）+ daemon thread 逐段做 → 前端 1.5s poll。
- **全鏈**：ffmpeg 截 `[start,end]`（`segment_rerun.padded_window` — <1.2s cue 對稱 pad，sub-second slice 會幻聽，validation 2026-06-10）→ mlx-whisper（`content_asr_lang`）→ `derive_aligned_output([cue])` per 輸出語言 → `_registry_lock` 內原子寫 segments/content_asr_segments/translations/aligned_bilingual/text 五位同步，row reset pending。Cue start/end 永不變（grid 安全）。
- **互鎖**：rerun ↔ render/split/merge/glossary-reapply 雙向 409。單段失敗記 `failed_positions` 唔斷批次；worker 有 top-level crash safety net（防 job 卡 running 永久 409）。
- **已知限制**（tracker: [2026-06-10-proofread-ai-rerun-validation-tracker.md](docs/superpowers/specs/2026-06-10-proofread-ai-rerun-validation-tracker.md)）：真實邊界 cue（≥1s）質量好（間中修正原 ASR 錯誤）；clause-split 插值超短 cue 結果反映窗口真實音訊（可能同原文字分配唔同）— 建議先「合併下一段」再 rerun。
- **已批核行全綠**：`.rv-b-rail-item.ap` 成行淺綠背景（hover 加深）+ 兩行字幕文字 `var(--success)` 綠色（取代舊 opacity 0.6；所有檔案類型生效）。批量 Rerun 掣住喺段落表 header 之下嘅專屬欄 `.rv-b-rail-rerun`（唔同 header 爭位）。段落導航：`↑`/`↓`（IME-safe）+ `J`/`K`。
- Pure 邏輯 `backend/segment_rerun.py`（`tests/test_segment_rerun.py` 18 tests）。

### Proofread segment timing trim (output_lang, NEW 2026-06-11)

- 時間軸有**縮放**（`.rv-b-tlh-r` toolbar：⊡全片/−/＋/⌖對焦本段；viewport+`#waveformInner` 結構，放大後橫向捲動，peaks 按 zoom 重取樣 `?bins=`、ticks 自適應）。縮放全 kind 可用；以下編輯功能 output_lang only。
- **調整 cue In/Out 三種方法**：①當前段 region 左右**拖拉把手**（拖拉中 suppress regions 重建、浮動 timecode、視窗外鬆手自動 commit、拖完 stray click 被 capture guard 截）②`I`/`O` 鍵 + ctrl row `⤓I`/`⤓O` 掣 = 設為播放頭（有 modifier guard — Ctrl+O 等組合鍵唔會誤觸）③ctrl row `#curIn`/`#curOut` 變 editable timecode input（MM:SS.ss，秒 ≥60 拒絕）。
- 全部寫入 `PATCH /segments/<pos>/timing`（roll-on-contact 語義；planner 喺 `backend/segment_timing.py`，end-first 雙邊 clamp + 最終 invariant guard；`tests/test_segment_timing.py` 16 tests）。PATCH 串行化防亂序 reconcile。
- UX 研究 + 用戶兩輪 mockup 反饋：[docs/superpowers/specs/2026-06-11-segment-timing-ux-research.md](docs/superpowers/specs/2026-06-11-segment-timing-ux-research.md)。

### Subtitle custom-font upload (NEW, 2026-06-06)

- The subtitle font system is **bundled-font driven**: drop/upload `.ttf`/`.otf` into `backend/assets/fonts/` → `GET /api/fonts` lists them → `font-preview.js` injects one `@font-face` per file (live preview) AND `renderer.py` passes `:fontsdir=<FONTS_DIR>` to libass (burn-in), so preview glyphs match the rendered output.
- **Custom fonts can now be uploaded in-app** (no more manual server file-drop). The 字幕設定 panel on **proofread + index** has a **「＋ 新增字型」** button → `POST /api/fonts` (validates extension + size ≤32MB + sfnt magic bytes; `secure_filename` with a uuid fallback for CJK filenames). The font `<select>` is now driven by `/api/fonts` (actually-available fonts, grouped 「已上載字型」/「系統字型」) via `FontPreview.fontOptionsHtml()` / `refreshFonts()` / `getFonts()` — so switching a font produces a real change instead of silently falling back to a system font. `DELETE /api/fonts/<file>` removes one.
- `fonttools` (in `requirements.txt`) reads the **real family name** from each font's `name` table, so the picker value == the `@font-face` family == the ASS Style family libass resolves via `:fontsdir`. Font config (family/size/color/outline/margin) still persists to the active Profile or `settings.json` `font` via the existing 「儲存為預設」 flow.

#### Daemon-safe CJK font resolution (NEW, 2026-06-09)

macOS subtitle burn-in runs through libass's **CoreText** provider, and the production server is a **session-less LaunchDaemon**. In that context CoreText CANNOT load **on-demand AssetsV2 fonts** (`PingFang` lives under `/System/Library/AssetsV2/`) NOR absent fonts (`Noto Sans TC` is not installed on macOS) — both silently fall back to **Helvetica → Chinese renders as tofu (□)**, only ASCII digits survive. Only `/System/Library/Fonts/` **proper** CJK fonts (**STHeiti** = `Heiti TC`/`Heiti SC`) load reliably under a daemon (empirically confirmed; even bundling `PingFang.ttc` via `:fontsdir=` fails — CoreText shadows the known family). Two pieces fix this:

- **`platform_backend.resolve_subtitle_font_family(family, info)`** — on darwin, remaps absent + AssetsV2 CJK families (`Noto*`/`Microsoft*`/`Source Han*`/`PingFang*`/`Songti*`/`Kaiti*`/`STSong`…) to `Heiti TC`/`Heiti SC`. Non-darwin and unknown families (uploaded brand fonts) pass through. Applied in **`renderer.generate_ass`** (the single burn-in chokepoint, which also scrubs `,{}`/newlines out of the Fontname field). It is a rescue allowlist for legacy/out-of-band values, not the primary guard.
- **`platform_backend.available_subtitle_fonts(info)`** — the picker's source of truth. On darwin it returns only families whose file is present in `/System/Library/Fonts/` proper (`Heiti TC`/`Heiti SC`; `PingFang`/`Noto` excluded), file-verified at runtime. Exposed via `GET /api/fonts` as **`system_fonts`**; `font-preview.js` builds the 「系統字型」 group from it (no more hard-coded per-page font arrays), so the picker never offers a family that would tofu. Win/Linux fall back to a curated best-effort list (not host-verified yet).

### Admin Beta 測試模式 (LLM-only, NEW)

- Global toggle stored as `settings.json:beta_openrouter` (boolean, default `false`). Managed by `ProfileManager.get_beta_mode()` / `set_beta_mode()` and surfaced via `GET/PUT /api/admin/beta-mode` (admin-only).
- **When ON**: the output_lang pipeline's LLM (`_make_ollama_llm_call`) routes to **OpenRouter `qwen/qwen3.5-35b-a3b`** @ temp 0.3 (via `OpenRouterTranslationEngine`) instead of local Ollama. This covers both cross-lang MT and the 書面語 refiner — both share the same `_make_ollama_llm_call` injection point.
- **ASR stays LOCAL** (mlx-whisper large-v3) in Beta mode. Routing ASR to OpenRouter was investigated and **REJECTED** — OpenRouter's `/api/v1/audio/transcriptions` does not return segment/word timestamps, which the subtitle pipeline requires. Evidence: Validation-First Phase 0, 2026-06-07 — see [docs/superpowers/specs/2026-06-07-beta-openrouter-validation-tracker.md](docs/superpowers/specs/2026-06-07-beta-openrouter-validation-tracker.md).
- **Hard-fail, no automatic fallback**: a failed OpenRouter LLM call marks the job `failed` with the error surfaced. Enabling the toggle without an API key → HTTP 400.
- **API key**: entered in the admin UI (password field, write-only), persisted to `backend/.env` as `OPENROUTER_API_KEY` (gitignored) and set in `os.environ` immediately. Loaded at app boot by `_load_env_file()` so it survives a restart.
- **New module** `backend/beta_mode.py`: constants (`BETA_LLM_MODEL = "qwen/qwen3.5-35b-a3b"`), `key_status()`, `set_key()`.
- **Frontend**: admin-only 「Beta 測試模式」 nav tab in `user.html` (我的帳戶 page) — enable toggle, API key input, and status display. States clearly that ASR stays local.
- **2026-06-11 起 UI 全面唔顯示引擎/型號/供應商名**（Whisper/mlx/qwen/OpenRouter/Ollama/雲端）：4 頁假 health pills（`WHISPER mlx-whisper`/`CLOUD qwen3.5`）已剷；index 動態 pills 剩 連線+佇列；V6 stage 標籤改「語音識別」「時間對齊」（`progress_adapter.py` + index `_COLD_STAGES` 兩邊）；inspector Pipeline 組唔再列 ASR/MT 引擎名；Beta pane 用「外部 AI 服務」「API 金鑰」中性字眼（後端 `auth/admin.py` 錯誤字串同步）；死代碼 OpenRouter modal 加 `display:none` 防 innerText/a11y 漏字。內部代碼/註釋/死代碼識別字唔受影響。

### Retired UI / removed dead code (cleaned up 2026-06-06)

Full audit: [docs/superpowers/specs/2026-06-06-project-health-audit.md](docs/superpowers/specs/2026-06-06-project-health-audit.md). ~6,800 lines removed; verified `import app` + suite clean.

- **Removed (frontend)**: the pipeline-strip subgraph (`renderPipelineStrip` / `renderPipelineStripV6` / `renderStripLanguageSelector` / `togglePipelineSteps` + ~17 call sites + CSS), the `openLangConfigManageModal` language-config modal, dead JS helpers (`stagesForFile` / `restartService` / `fmtSec` / `loadFontConfig` / etc.), and orphan pages `proofread.old.html` + `mockup-media-bin.html`.
- **Removed (backend)**: the dead+broken live-streaming ASR subsystem (5 socket handlers + `/api/streaming/available` + the `WHISPER_STREAMING_AVAILABLE` block), the never-registered `routes/` blueprint package (12 duplicate modules + `register_blueprints`; the 4 live ones — pipelines/refiner_profiles/transcribe_profiles/llm_profiles — kept), `asr/repetition_guard.py`, and `asr_profiles.py`.
- **Still present but legacy/inert** (NOT retired — kept pending product decision): the V5 DAG path (`pipeline_runner.run()` v5 branches, v4 stages, `translator_profiles.py` / `verifier_profiles.py` managers) + its config (`config/{asr_profiles,translator_profiles}/`, left uncommitted) + 2 inert V5 pipelines. Activation only accepts `profile` / `pipeline_v6`, so V5 never runs at runtime. **`backend/scripts/v5_prototype/venv_qwen/` is NOT v5 — it is the LIVE V6 Qwen3-ASR py3.11 venv (gitignored; never delete).**
