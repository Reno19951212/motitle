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
│   │   ├── sentence_pipeline.py # Sentence-aware merge/redistribute + time-gap guard
│   │   ├── alignment_pipeline.py # Phase 6: LLM-anchored alignment (marker injection + fallback)
│   │   └── post_processor.py   # Subtitle length / hallucination post-checks
│   ├── language_config.py      # Per-language ASR/translation parameters
│   ├── config/                 # Configuration files
│   │   ├── settings.json       # Active profile pointer
│   │   ├── profiles/           # Profile JSON files
│   │   ├── glossaries/         # Glossary JSON files
│   │   └── languages/          # Per-language config (en.json, zh.json)
│   ├── tests/                  # Test suite (375 tests)
│   ├── data/                   # Runtime: uploads, registry, renders (gitignored)
│   └── requirements.txt        # Python dependencies
├── frontend.old/               # Legacy vanilla HTML/CSS/JS pages (v4.0 A5 sub-phase 砍走)
│   ├── index.html              # Main dashboard — kept for transition only
│   ├── proofread.html          # Proof-reading editor — kept until A4 ships replacement
│   ├── login.html / admin.html / Glossary.html
│   ├── js/font-preview.js      # Shared module (still imported by .old pages)
│   └── tests/                  # Playwright suite (kept until A5)
├── frontend/                   # NEW v4.0 A3 — Vite + React 18 + TypeScript SPA
│   ├── package.json            # npm scripts (dev/build/test/test:e2e)
│   ├── vite.config.ts          # Proxies /api + /socket.io + /fonts to Flask :5001
│   ├── src/
│   │   ├── main.tsx, App.tsx, router.tsx, index.css
│   │   ├── lib/                # api fetch + socket events + zod schemas + utils
│   │   ├── stores/             # Zustand: auth, pipeline-picker, ui (toasts)
│   │   ├── providers/          # AuthProvider + SocketProvider
│   │   ├── pages/              # Login, Dashboard, Pipelines, AsrProfiles, MtProfiles, Glossaries, Admin, ProofreadPlaceholder
│   │   └── components/         # FileCard, UploadDropzone, PipelinePicker, StageEditor, EntityTable/Form, ConfirmDialog, Layout/TopBar/SideNav + ui/ shadcn primitives
│   └── tests-e2e/              # Playwright suite (new — auth + dashboard scenarios)
├── docs/superpowers/           # Design specs and implementation plans
├── setup.sh                    # One-shot environment setup
├── start.sh                    # Start backend + open browser
├── CLAUDE.md                   # This file
└── README.md                   # User-facing documentation (Traditional Chinese)
```

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

**WebSocket events (client → server)**
| Event | Payload |
|---|---|
| `load_model` | `{model}` |

**REST endpoints**
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Server status, loaded models |
| GET | `/api/models` | Available Whisper model list |
| POST | `/api/transcribe` | Upload + async transcription → auto-translate |
| GET | `/api/files` | List all uploaded files with status |
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
| GET | `/api/asr/engines` | List ASR engines with availability |
| GET | `/api/asr/engines/<name>/params` | Get param schema for ASR engine |
| POST | `/api/translate` | Translate a file's segments |
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
| GET | `/api/asr_profiles` | List ASR profiles visible to user (v4.0 P1) |
| POST | `/api/asr_profiles` | Create ASR profile |
| GET | `/api/asr_profiles/<id>` | Get single ASR profile |
| PATCH | `/api/asr_profiles/<id>` | Update ASR profile (owner only) |
| DELETE | `/api/asr_profiles/<id>` | Delete ASR profile (owner only) |
| GET | `/api/mt_profiles` | List MT profiles visible to user (v4.0 P1) |
| POST | `/api/mt_profiles` | Create MT profile |
| GET | `/api/mt_profiles/<id>` | Get single MT profile |
| PATCH | `/api/mt_profiles/<id>` | Update MT profile (owner only) |
| DELETE | `/api/mt_profiles/<id>` | Delete MT profile (owner only) |
| GET | `/api/pipelines` | List pipelines, includes `broken_refs` annotation (v4.0 P1) |
| POST | `/api/pipelines` | Create pipeline (cascade ref check vs ASR/MT/Glossary) |
| GET | `/api/pipelines/<id>` | Get single pipeline + broken_refs |
| PATCH | `/api/pipelines/<id>` | Update pipeline (owner only, re-validates cascade refs) |
| DELETE | `/api/pipelines/<id>` | Delete pipeline (owner only) |
| POST | `/api/pipelines/<id>/run` | Enqueue pipeline run on a file (v4.0 A1) |
| POST | `/api/files/<fid>/stages/<idx>/rerun` | Re-run individual stage |
| PATCH | `/api/files/<fid>/stages/<idx>/segments/<seg_idx>` | Edit per-stage segment text |
| POST | `/api/files/<fid>/pipeline_overrides` | Set file+pipeline-level prompt overrides |

### Frontend

**`index.html`** — Main dashboard. File upload, transcription with progress, auto-translation, profile selector, transcript display (auto-switches to Chinese when translations available), subtitle overlay on video playback.

**`proofread.html`** — Standalone proof-reading editor. Side-by-side layout: video player (left) + segment table (right). Inline editing of Chinese translations, per-segment and bulk approval, keyboard shortcuts, format picker (MP4/MXF), render with progress polling and download.

---

## Development Guidelines

- Frontend will adopt Vite + React + TypeScript stack in v4.0 A3-A4 sub-phases (per design doc §14)
- All new backend routes must handle errors and return JSON `{error: "..."}` with appropriate HTTP status
- The `get_model()` function is the legacy model loading path; new code should use `asr/` engines via profiles
- Test both faster-whisper and openai-whisper code paths when modifying transcription logic
- Glossary entries are injected into translation prompts as few-shot examples
- Python 3.9 compatibility required — use `List[int]`, `Dict[str, int]`, `Optional[...]` from typing

### Engine Architecture

- ASR 同 Translation 引擎完全解耦，透過 ABC + Factory 模式
- 新增引擎只需：實現 ABC 介面 + 加入 Factory mapping + 加入 tests
- 引擎選擇可由前端即時傳入，Profile 作為「快速預設」而非硬性綁定
- **ASREngine** 必須實現：`transcribe()`, `get_info()`, `get_params_schema()`
- **TranslationEngine** 必須實現：`translate()`, `get_info()`, `get_params_schema()`, `get_models()`

### Validation-First Mode（修改 ASR / MT 必須遵守）

**任何涉及後端 ASR 引擎或翻譯引擎（MT, machine translation）嘅改動，必須先做 Validation-First 驗證，confirm empirical evidence 之後先寫 plan + 落代碼。** 唔可以憑感覺直接 ship。

**範圍涵蓋：**
- `backend/asr/*.py`（ASR engine ABC、Whisper / mlx-whisper / Qwen3-ASR / FLG / segment_utils）
- `backend/translation/*.py`（TranslationEngine ABC、Ollama / OpenRouter / Mock / sentence_pipeline / alignment_pipeline / post_processor）
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

1. **CLAUDE.md** (this file) — Architecture, REST endpoints, version history
2. **README.md** (user-facing, **must be written in Traditional Chinese**)
3. **docs/PRD.md** — Update feature status markers (📋 → ✅)

---

## Completed Features

### v4.0 A3 — Frontend foundation (in progress on `chore/asr-mt-rearchitecture-research`)
- 舊 vanilla HTML pages 移去 [frontend.old/](frontend.old/) (A5 砍走)；新 Vite + React 18 + TypeScript 嘅 SPA 喺 [frontend/](frontend/)，按 design doc [§14](docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md) 嘅 stack lock
- **Pages 全部 ship 齊**：`/login` ([src/pages/Login.tsx](frontend/src/pages/Login.tsx) RHF + zod)、`/` (Dashboard with PipelinePicker + UploadDropzone + per-stage FileCard)、`/pipelines` (drag-sortable @dnd-kit StageEditor + glossary stage + font config)、`/asr_profiles`、`/mt_profiles` (engine locked to `qwen3.5-35b-a3b`)、`/glossaries` (with entries editor + CSV import/export)、`/admin` (users + audit tabs)、`/proofread/:fileId` (placeholder — A4 實現完整 editor)
- **Auth**：React Router guard + boot `/api/me` probe + Zustand `useAuthStore`；Logout 經 TopBar
- **Realtime**：React Context + reducer 接收 Socket.IO events (`file_added` / `file_updated` / `pipeline_stage_progress` / `pipeline_stage_complete` / `pipeline_complete` / `pipeline_failed`)
- **State**：Zustand for auth + pipeline-picker (with `localStorage` persistence via `partialize`) + UI toast store；per-page local state for entity list refetch
- **Validation**：zod schemas (`AsrProfileSchema` / `MtProfileSchema` / `GlossarySchema` / `PipelineSchema` / `LoginSchema`) mirror backend validators 1:1，包括 MT same-lang refine 同 Pipeline cascade-ref shape (`asr_profile_id` + `mt_stages[]` + `glossary_stage` + `font_config`)
- **Forms**：react-hook-form + zodResolver；shared `<EntityTable>` + `<EntityForm>` + `<ConfirmDialog>` 三件套畀 5 個 entity CRUD page 共用
- **Dev mode**：`npm run dev` 喺 `frontend/` 內由 `concurrently` 同時起 Vite (5173) + Flask (5001)；Vite proxy forward `/api`, `/socket.io`, `/fonts` 去 Flask
- **Production**：`npm run build` → `frontend/dist/` → Flask `serve_index` / `serve_assets` + SPA fallback for React Router routes (`/login`, `/pipelines`, `/asr_profiles`, etc.)
- **Backend changes (minimal)**：
  - `serve_index` 改 serve `frontend/dist/index.html` if exists；6 個 React SPA route (`/login` `/pipelines` etc.) 路 SPA fallback；`/assets/<path>` 路 hashed Vite bundle；`/api/*` 404 仍返 JSON `{"error":"not found"}` 唔 fall through 入 SPA shell
  - 新 `_FRONTEND_LEGACY_DIR` constant；legacy `*.html` route (`/login.html` / `/proofread.html` / `/admin.html` / `/Glossary.html` / `/index.html`) 路 `frontend.old/`，A5 sub-phase 砍走
  - `/api/transcribe` 接 optional `pipeline_id` form field — 有 → enqueue `pipeline_run` job + payload；冇 → 行 legacy `asr` job (A5 砍走 legacy 路徑)
- **Tests**：~80 個 Vitest unit (schemas / api / auth store / SocketProvider reducer / FileCard / pipeline-picker) + Playwright E2E (auth + dashboard) — frontend 100% green；backend +10 個新 test (T3 SPA fallback / T3 serve_assets / T4 transcribe with pipeline_id) — no regressions
- **Stack locked per parent spec [§14](docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md)**：TypeScript 5.6 strict (`noUncheckedIndexedAccess: true`)、Vite 5.4、React 18.3、React Router 6.27、Zustand 5.0、shadcn/ui (copy-in)、Tailwind 3.4、react-hook-form 7.53、zod 3.23、@dnd-kit 6.1+sortable 8.0、react-dropzone 14.3、socket.io-client 4.8、Vitest 2.1、Playwright 1.48、concurrently 9.0
- **Out-of-A3 scope**（明確留 A4 / A5）：A4 proofread page (per-segment editor + render modal + glossary apply UI)；A5 cleanup (`frontend.old/` 整個 delete + legacy `/api/transcribe` 嘅 ASR-only flow + `/api/profiles` bundled endpoint + 5 個 `_FRONTEND_LEGACY_DIR` 嘅 .html route + `/js/<path>` + `/css/<path>` 靜態 route 全部砍走)
- **Spec / Plan**：[design](docs/superpowers/specs/2026-05-17-v4-A3-frontend-foundation-design.md) / [plan](docs/superpowers/plans/2026-05-17-v4-A3-frontend-foundation-plan.md)

### v4.0 A1 — Stage executor + pipeline_runner (in progress on `chore/asr-mt-rearchitecture-research`)
- 3 new stage classes ([backend/stages/asr_stage.py](backend/stages/asr_stage.py) / [backend/stages/mt_stage.py](backend/stages/mt_stage.py) / [backend/stages/glossary_stage.py](backend/stages/glossary_stage.py)) sharing `PipelineStage` ABC, per-segment-1:1 contract per design doc §4
- `PipelineRunner` ([backend/pipeline_runner.py](backend/pipeline_runner.py)) linear stage executor + Socket.IO progress at 5% granularity + fail-fast + cancel_event integration with JobQueue
- 4 new REST endpoints (run / rerun / edit / pipeline_overrides) — async via existing JobQueue `pipeline_run` handler
- `word_timestamps` field removed from ASR profile schema + Whisper engines (Q7-b)
- Per-file per-pipeline prompt override resolution (Q6-a scope)
- Emergent quality flag heuristic — Whisper avg_logprob < -1.0 → `quality_flags: ["low_logprob"]` on ASR stage output
- ~50 new backend tests (3 stage classes + runner + endpoints + integration); 935 backend tests pass + 14 pre-existing failures unchanged
- **Legacy code path zero-touch** — `transcribe_with_segments` / `_auto_translate` / `alignment_pipeline.py` 全部唔郁，A5 sub-phase 砍走

### v4.0 Phase 1 — Entity Foundation (in progress on `chore/asr-mt-rearchitecture-research`)
- 3 new manager modules ([backend/asr_profiles.py](backend/asr_profiles.py) / [backend/mt_profiles.py](backend/mt_profiles.py) / [backend/pipelines.py](backend/pipelines.py)), mirror v3.13 `ProfileManager` Phase 5 T2.8 TOCTOU lock pattern + per-resource ownership (`user_id` field per entity, admin OR owner OR shared visibility, admin OR owner edit)
- 15 new REST endpoints (5 per entity × 3 entities, all gated by `@login_required` + per-entity `@require_*_owner` decorator from [backend/auth/decorators.py](backend/auth/decorators.py))
- Pipeline validator does **cascade ref check** at create/update — references to unknown ASR/MT profile or glossary → 400 with explicit error
- Pipeline GET response includes **`broken_refs` annotation** listing sub-resources the requesting user cannot view (per design doc [§7](docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md))
- ~50 new backend tests (~31 validator + manager + ~18 endpoint integration + 1 cross-user cascade integration); `test_phase5_security.py::_restore_app_module` fixture also patched to snapshot `auth.decorators` so v4 manager closures survive module re-import during isolation tests
- **Out of P1 scope** (deferred to later phases): stage executor, pipeline_runner, migration script, frontend changes — see [docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md](docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md) for full v4.0 plan
- Legacy `/api/profiles` (bundled ASR + MT) **unchanged** in P1 — keeps running until P3 migration

### v3.18 — MT Prompt Override (削減 + per-file textarea + templates)
- **Stage 2 goal**: Reduce MT formulaic phrase over-use (research found "傷病纏身" 15× / "就此而言" 14× / "儘管" 13× / "真正" 24× across 166 Video 1 segments — caused by hardcoded EN→ZH mapping examples in the 3 system prompts). Open a frontend override path so users can fine-tune per-file. Spec: [docs/superpowers/specs/2026-05-15-stage2-prompt-override-design.md](docs/superpowers/specs/2026-05-15-stage2-prompt-override-design.md). Plan: [docs/superpowers/plans/2026-05-15-stage2-prompt-override-plan.md](docs/superpowers/plans/2026-05-15-stage2-prompt-override-plan.md).
- **A — Default constants rewritten** ([commit `cabe78a` + `603e612`](#)): 3 system prompts削減 — `alignment_pipeline.build_anchor_prompt` preamble (10 lines → 4 lines, dropped 4 EN→ZH mappings + 3 connector examples), `SINGLE_SEGMENT_SYSTEM_PROMPT` (22 lines → ~10 lines, dropped Tchouameni/Como/Aurelien name lock from 6 demos → 2 generic demos), `ENRICH_SYSTEM_PROMPT` (22 → ~14 lines, dropped 5-word idiom list + 1 demo, added explicit「毋須照搬」anti-mimic rule). Anti-formulaic rule (避免過度套用相同四字詞或固定連接詞模板) added to every prompt. Inline `# v3.18 Stage 2: formulaic over-use fix` comment above each constant prevents future re-introduction.
- **B — File-level `prompt_overrides` schema** ([Tasks 3-7]): New optional `prompt_overrides: dict|null` field on file registry entries. `PATCH /api/files/<id>` accepts the field with shared validation (extracted to [backend/translation/prompt_override_validator.py](backend/translation/prompt_override_validator.py) so profile-level + file-level layers cannot drift apart). New `_resolve_prompt_override(key, file_entry, profile)` helper implements 3-layer fallthrough (file > profile > None → engine falls back to hardcoded). `_auto_translate` calls the resolver once per job and passes the resulting dict to `engine.translate(prompt_overrides=)` for batched/single paths, and to `translate_with_alignment(custom_system_prompt=)` for llm-markers path. Sentence-pipeline branch deliberately not wired — out of Stage 2 scope.
- **B — Engine plumbing** ([Task 6, commit `c9df6d6` + rename `a66a4c8`]): `OllamaTranslationEngine.translate()` gains optional `prompt_overrides=None` kwarg. New `_resolve_prompt_override(key, runtime_overrides)` helper on the engine: kwarg > `self._config[prompt_overrides]` > None. Threaded to `_translate_single`, `_enrich_batch`, `_build_system_prompt` via new `runtime_overrides=` param (and forwarders `_translate_single_mode` / `_translate_batch` / `_retry_missing` / `_enrich_pass`). ABC + `MockTranslationEngine` updated for signature conformance. Backward-compat: legacy callers without the new kwarg keep existing behavior (default `None`).
- **C — 3 starter templates** ([Task 8-9]): `backend/config/prompt_templates/{broadcast,sports,literal}.json` — broadcast byte-equals the削減版 defaults (test enforced); sports adds sports register cues (動作描述傳神 / 攻入 / 化解); literal drops length-target and broadcast register for documentary/economy use. Loaded via `GET /api/prompt_templates` (login_required, non-admin reading allowed). Templates serve as **UI seed source** only, not a runtime fallthrough layer — picking a template + clicking "套用模板" writes its content into the textareas; the user then clicks "重新翻譯此檔案" to PATCH + trigger MT.
- **Frontend** ([Tasks 10-12]): Proofread page sidebar gains a new "自訂 Prompt" panel inside `.rv-b-vid-panels` after `subtitleSettingsPanel`. 4 textareas (one per override key), 3 expanded by default (anchor / single / enrich), pass1 folded. Template dropdown + "套用模板" button fills textareas; "重新翻譯此檔案" PATCHes file + POSTs `/api/translate`; "清空" sets `prompt_overrides: null`. Dashboard file card shows "📝 自訂 Prompt" chip via `badge--prompt` class when any non-null override is set; clicking the chip navigates to the proofread page for that file.
- **Tests**: 9 validator + 8 resolver + 6 PATCH route + 4 kwarg precedence + 6 template loader + 4 template API + 1 auto_translate integration = ~38 new backend tests. 3 new Playwright scenarios (apply template / clear PATCH null / commit triggers translate). All existing tests still pass (~780 backend + Playwright suite).
- **Validation** ([docs/superpowers/validation/v3.18-stage2-diff-report.md](docs/superpowers/validation/v3.18-stage2-diff-report.md)): **⏳ PENDING MANUAL RE-RUN** — Stage 2 skeleton committed with re-run instructions + result tables (TBD). Operator must execute the 7-step script (restart backend → clear file overrides → trigger MT on Video 1 → capture post-snapshot → diff against v3.17 baseline) and fill in formulaic phrase frequencies before merging to dev. Acceptance threshold: formulaic frequencies drop ≥60% on Video 1 AND empty rate maintained ≤6% AND no new hallucination class introduced (5 known-bad segments spot-checked manually).
- **Out-of-scope** (deferred to Stage 3+): domain context anchor (per-file 1-2 sentence subject prefix); forbidden phrases list (negative vocabulary constraint); user-self-service template publishing (admin-only in Stage 2); glossary stacking (multi-glossary support); per-file retry strategy (empty/over-cap fallback config); A/B prompt comparison (run same file with 2 prompts side-by-side); s2hk simplified-Chinese leak post-process; ASR-side fragment merge (Stage 1, explicitly skipped per user direction).
- **Files touched**: 5 backend modified (`translation/alignment_pipeline.py`, `translation/ollama_engine.py`, `translation/__init__.py`, `translation/mock_engine.py`, `profiles.py`, `app.py`), 2 new validator/util (`translation/prompt_override_validator.py`), 2 frontend modified (`proofread.html`, `index.html`), 3 new templates (`config/prompt_templates/{broadcast,sports,literal}.json`), 6 new test files (~38 backend tests + 1 Playwright). 14 commits on `chore/v3.18-stage2-prompt-override` branch.

### v3.17 — Preset Trim + ASR Cleanup + Validation
- **Part A — preset trim**：`ASR_PRESETS` 刪 `speed`（剩 `accuracy`/`debug`/`custom`）；`MT_PRESETS` 刪 `fast-draft`（剩 `broadcast-quality`/`literal-ref`/`custom`）。Playwright Test 2/3/4 reframe — Test 2 + Test 4 改用 Custom preset + `eval()` JS direct-mutate（`_pendingMt/AsrPreset` 變量喺 script scope，`page.evaluate()` 入面 eval 訪問）；Test 3 mix-and-match 改 ASR Accuracy + MT Broadcast Quality。4/4 Playwright green。
- **Part B — ASR engine cleanup**：
  - [backend/asr/whisper_engine.py](backend/asr/whisper_engine.py) + [backend/asr/mlx_whisper_engine.py](backend/asr/mlx_whisper_engine.py) 嘅 `get_params_schema()` 將 `model_size` enum 收窄到 `['large-v3']`，default 同步改 `'large-v3'`；MLX-Whisper 嘅 `MODEL_REPO` dict 同步收窄。前端 dropdown 自動跟 schema 收窄。
  - 一次性 migration script [backend/scripts/migrate_v317_asr_models.py](backend/scripts/migrate_v317_asr_models.py) 將既有 `config/profiles/*.json` 內 `asr.model_size != 'large-v3'` 嘅 normalize 做 `'large-v3'`。Idempotent。實際運行 0 個 profile 改動 — 3 個既有 profile 已經全部 large-v3。
  - Delete `backend/asr/qwen3_engine.py` + `backend/asr/flg_engine.py`（兩個 stub 自 v2.0 起一直 `raise NotImplementedError`）；`backend/asr/__init__.py` factory 移除對應 imports + factory dict mapping。Unknown engine name 仍 raise `ValueError("Unknown ASR engine: ...")`。
  - 跨 backend 清理 stub reference：`backend/profiles.py` 嘅 `VALID_ASR_ENGINES` 由 `{"whisper", "mlx-whisper", "qwen3-asr", "flg-asr"}` 改 `{"whisper", "mlx-whisper"}`；`backend/app.py` `/api/asr/engines` handler 移除 stub 條目；`backend/tests/test_asr.py` 7 個 stub 相關 test 刪除、1 個 engine list test 更新 expected count + negative assertions、1 個 `model_size='small'` fixture fix 做 `'large-v3'`。`pytest tests/` 757 pass / 15 pre-existing fail（11 Playwright E2E、1 v3.3 macOS tmpdir baseline、3 R5 Phase 5 已知 isolation 問題）— 無新 regression。
- **Part C — Validation tooling + before/after diff report**：
  - [backend/scripts/v317_validation.py](backend/scripts/v317_validation.py)（~700 行）— `capture_snapshot` 拎齊 file/segments/translations/profile/glossary-scan；13 個 metric helper（Tier 1 core 5 + Tier 2 broadcast quality 4 + Tier 3 diagnostic 5）；markdown report renderer；CLI 三個 subcommand: `snapshot` / `rerun` / `diff`。
  - [backend/tests/test_v317_validation.py](backend/tests/test_v317_validation.py) 18 個 unit test 全綠（每個 metric helper 都有 fixture-based 測試）。
  - Validation 流程：對 server 上嘅 2 條 video 做 baseline snapshot → 應用 Part A+B → re-run ASR/MT → post snapshot → 13-tier diff report → human review gate（合理化 verdict + Conclusion）。
  - Report、baseline snapshot、post snapshot 全部 commit 入 [docs/superpowers/validation/](docs/superpowers/validation/) 作 PR evidence。
- **Inline catches during validation**：
  - **`capture_snapshot` 對 `/api/profiles/active` 響應 envelope 處理**：endpoint 返 `{"profile": {...}}` 包裝，唔同 `/api/profiles/<id>` 直接返 dict。Helper 加自動 unwrap，避免下游 glossary lookup 失效。
  - **`prod-default` profile 嘅 `translation.glossary_id` stale**：value 係 `"broadcast-news"` 但實際 glossary 用 UUID。Update 為真實 UUID `08b6666e-1bcc-4df1-9005-e5dafa27c076`。
  - **`backend/translation/alignment_pipeline.py` line 78+81 用 v3.14 glossary field**：仍用 `e['en']`/`e['zh']`（v3.15 已 rename 做 `source`/`target`）— 當 active profile `alignment_mode: "llm-markers"` 時所有 MT job silent KeyError。加 backward-compat fallback `.get('source', e.get('en', ''))`。
- **Validation 結果**（詳見 [docs/superpowers/validation/v3.17-diff-report.md](docs/superpowers/validation/v3.17-diff-report.md)）：
  - Video 1（English source / 166 segments）：ASR text 100% identical baseline ↔ post；MT latency 82.0s → 65.7s（-20%）；MT empty rate 5.4%（9/166，屬於 alignment-pipeline 邊界 case 正常範圍）；glossary strict violations 8 → 5（改善）。
  - Video 2（Cantonese source baseline）：MT latency 75.5s → 24.5s（-67%）；MT empty rate 2.4%（2/85）。**注意**：baseline 用咗 Cantonese-language profile 跑（registry 冇記 `profile_id`），post snapshot 經 fallback 用 active profile（`asr.language=en`），ASR 變英文 — 屬於 profile linkage data 問題（pre-date v3.10），唔影響 v3.17 結論。
  - **Investigation phase 發現 + 解決一個 transient validation artifact**：Task 11 期間 backend swap 期間 post-snapshot 捕捉到中間 broken state（舊 PID 96344 + 新 backend FLASK_SECRET_KEY crash），令首次 diff report 誤報 61% empty。Investigation phase 加 debug logging + cleanly re-run 之後 fresh snapshot 顯示 < 6% empty 嘅正常邊界 case 率。
  - **Verdict**: ✅ Merge v3.17 to dev — zero regression，alignment_pipeline.py glossary compat fix 真實必要（v3.15 遺漏）。
- **Files touched**：3 個 frontend modified（`index.html`、`tests/test_profile_ui_guidance.spec.js`、`CLAUDE.md`），8 個 backend modified（`whisper_engine.py`、`mlx_whisper_engine.py`、`asr/__init__.py`、`profiles.py`、`app.py`、`translation/alignment_pipeline.py`、`tests/test_asr.py`、`config/profiles/prod-default.json`），2 個 backend deleted（`qwen3_engine.py`、`flg_engine.py`），3 個 new script（migrate_v317_asr_models.py + v317_validation.py + test_v317_validation.py），5 個 validation artifact（2 baseline JSON + 2 post JSON + 1 markdown report）。
- **Spec / Plan / Report**：[spec](docs/superpowers/specs/2026-05-15-preset-trim-asr-cleanup-design.md) / [plan](docs/superpowers/plans/2026-05-15-preset-trim-asr-cleanup-plan.md) / [report](docs/superpowers/validation/v3.17-diff-report.md)

### v3.16 — Per-Engine Preset + Danger Warning Refactor
- **目標**：將 Profile Save modal (`#ppsOverlay`) 由 pipeline-level bundled preset / danger warning 改為 per-engine（ASR + MT 各自獨立）。Spec: [docs/superpowers/specs/2026-05-14-per-engine-preset-design.md](docs/superpowers/specs/2026-05-14-per-engine-preset-design.md)。Plan: [docs/superpowers/plans/2026-05-14-per-engine-preset-plan.md](docs/superpowers/plans/2026-05-14-per-engine-preset-plan.md)。
- **HTML 改動**：刪走 `#ppsPresetSection` + `#ppsWarnings`（modal 頂部 bundled 容器），加兩個新 fieldset `🎙️ ASR 預設` (`#ppsAsrPresetButtons` + `#ppsAsrDangerWarnings`) + `🌐 MT 預設` (`#ppsMtPresetButtons` + `#ppsMtDangerWarnings`)，住喺現有「字幕來源預設」fieldset 後面。
- **JS data 拆分**：
  - `PROFILE_PRESETS` (5 個 bundled) → `ASR_PRESETS` (4 個：accuracy / speed / debug / custom) + `MT_PRESETS` (4 個：broadcast-quality / fast-draft / literal-ref / custom)
  - `DANGER_COMBOS` (5 個混合) → `ASR_DANGERS` (1 個：zh-cascade-risk) + `MT_DANGERS` (5 個：4 舊 MT + 1 新 cross-engine `word-timestamps-needed-for-alignment`)
- **JS state 拆分**：`_pendingPresetConfig` → `_pendingAsrPreset` + `_pendingMtPreset`，兩個獨立 state 互不覆蓋，支援用戶混搭 ASR / MT preset。
- **Cross-engine warning 擺位**：`word-timestamps-needed-for-alignment` 觸發 param (`alignment_mode=llm-markers`) 喺 MT 度，所以警告 chip render 喺 `#ppsMtDangerWarnings`；msg 文字明確指返用戶去 ASR section 開啟 word_timestamps。
- **Save flow**：`saveProfileAsPreset` 嘅 deep-merge 兩處（PATCH branch + POST branch）都由讀單一 `_pendingPresetConfig` 切到分別讀 `_pendingAsrPreset.config` + `_pendingMtPreset.config`，未揀 preset 嘅 engine 唔會 emit 對應 block，等用戶可以淨係改 ASR 而保留 MT 原狀（或反過來）。
- **CSS / dismissed-tracking 一致**：新 `_renderDangerChips()` 共用既有 `.pps-warning-chip.{critical,high,medium}` CSS rules 同既有 `_ppsWarningDismissed` Set，所以 chip 樣式 + 「忽略後唔再出現」UX 完全沿用 v3.15 行為。`MT_DANGERS` check lambda 用 `?? 1` 取代 `|| 1` 預設值，避免 `parallel_batches: 0` 等 falsy 但非 nullish 嘅值被誤判。
- **Backend / API contract**：完全不變。Profile JSON schema 不變。無 migration。
- **Tests**：`frontend/tests/test_profile_ui_guidance.spec.js` 由 2 個 test 變 4 個 — 2 個更新 selector（`#ppsAsrPresetButtons` + `#ppsMtDangerWarnings`），新加「mix-and-match」（ASR Accuracy + MT Fast Draft 同時 active）+「cross-engine warning fires」（Speed + Broadcast Quality 觸發 `word-timestamps-needed-for-alignment`）。`_openPpsModal` 測試 helper 用 API call `POST /api/profiles/prod-default/activate` 確保 `activeProfile` 已 load + `waitForFunction` 輪詢 overlay 開啟，避免依賴 user-facing button click（會被 videoPlaceholder 攔截）。

### v3.15 — Multilingual Glossary Refactor
- **Schema**: Glossary entries renamed from `{en, zh, zh_aliases}` to `{source, target, target_aliases}`. Glossary-level metadata adds `source_lang` + `target_lang` from an 8-language whitelist (`en, zh, ja, ko, es, fr, de, th`).
- **Validation**: Dropped per-language script rules (`en must contain letter` / `zh must contain CJK`). Now just non-empty + reject self-translation when source_lang==target_lang.
- **Scan two-stage**: New response shape with `strict_violations` + `loose_violations`. CJK/JA/KO/TH source languages get loose section (substring match where strict per-script word boundary missed). Latin scripts only return strict.
- **Apply prompt parameterized**: LLM prompt template reads glossary's `source_lang`/`target_lang` and substitutes language names. Default model hardcoded to `qwen3.5-35b-a3b` (overridable via `profile.translation.glossary_apply_model`).
- **CSV**: 3-col format `source,target,target_aliases` (last column optional). Old `en,zh` header rejected with explicit error.
- **Cutover**: All 5 pre-v3.15 glossary files deleted; users export-then-reimport via UI. Boot ignores files lacking `source_lang`/`target_lang` (no migration script). `applied_terms` field renamed `term_en/term_zh → term_source/term_target`; `baseline_zh → baseline_target`.
- **Auto-translate unchanged**: Translation engines still output Chinese; `_filter_glossary_for_batch` silently skips glossaries whose `source_lang != "en" OR target_lang != "zh"`.
- **Frontend**: 4 files refactored (`Glossary.html`, `proofread.html`, `index.html`, `admin.html`). Hardcoded `英文`/`中文` labels replaced with neutral `原文`/`譯文`; language pair badge `EN→ZH` shown on glossary header/dropdown.
- **New endpoint**: `GET /api/glossaries/languages` returns whitelist for dropdown sync.
- **Tests**: ~30 new pytest cases (`test_glossary_multilingual.py`) + 5 Playwright (`test_glossary_multilingual.spec.js`); existing `test_glossary.py` + `test_glossary_apply.py` renamed across.
- **Implementation tasks**: T1-T19 in [docs/superpowers/plans/2026-05-12-multilingual-glossary-plan.md](docs/superpowers/plans/2026-05-12-multilingual-glossary-plan.md). Design in [docs/superpowers/specs/2026-05-12-multilingual-glossary-design.md](docs/superpowers/specs/2026-05-12-multilingual-glossary-design.md).

### v3.14 — R6 Phase 6 security hardening (rate limiting, password policy, audit, readiness probe)
- **Rate limiting** (`backend/auth/limiter.py` — new shared singleton): Flask-Limiter 3.11 with `memory://` storage. `POST /login` — 10 req/min per IP; `GET /api/queue` — 60 req/min per IP. `RATELIMIT_ENABLED=False` config key disables limits globally (set in `conftest.py` for the test suite). Limiter registered on main app via `limiter.init_app(app)` in `app.py`.
- **Password policy** (`auth/passwords.py`): `validate_password_strength(plaintext)` — rejects passwords shorter than 8 characters (`ValueError: "at least 8"`) or matching any of 24 common passwords (`ValueError: "too common"`). Enforced at every write path in `auth/users.py`: `create_user()` and `update_password()`.
- **Failed-login audit log** (`auth/routes.py`): `POST /login` on 401 now calls `log_audit(actor_id=0, action="login_failed", target_kind="username", target_id=username)`. `actor_id=0` is the unauthenticated sentinel. 400 (missing fields) returns before credentials check — no audit entry created.
- **`/api/ready` readiness probe** (`app.py`): `GET /api/ready` — no authentication required (for load-balancer / container orchestration). Pings auth SQLite (`SELECT 1`) and checks all JobQueue worker threads alive. Returns `{"ready": true}` 200 on healthy, `{"ready": false, "error": "..."}` 503 on DB failure or dead workers. Separate from `/api/health` (liveness probe).
- **Frontend `setInterval` leak fix** (`frontend/js/queue-panel.js`): Replaced bare `setInterval` with `startQueueRefresh()` / `stopQueueRefresh()` guarded by `_queueTimerId !== null`. Prevents accumulating timers on repeated init calls. Both functions exported as `window.*` for external teardown.
- **Test suite** (`tests/test_phase6.py` — 14 new tests): `TestPasswordPolicy` × 5 (short reject, common reject, strong accept, update enforcement, direct validate); `TestFailedLoginAudit` × 3 (failed creates entry, success creates none, 400 creates none); `TestRateLimiting` × 3 (limiter registered on main app, 429 after threshold with `pytest.skip` guard for shared-singleton isolation, disabled in tests); `TestApiReady` × 3 (200 healthy, JSON content-type, no auth required).
- **Bulk test password migration**: All short test passwords (`"pw"`, `"secret"`, `"pw1"`, etc.) across 17 test files replaced with strong passwords (`"TestPass1!"`, `"NewPass1!"`, etc.) to comply with password policy enforcement at the DB layer.
- **Tests**: 686 backend pass + 1 skipped (rate limit isolation, passes in isolated run) + 12 pre-existing failures (11 Playwright E2E need browser, 1 macOS tmpdir colon-escape baseline). No regressions.
- **Remaining Phase 6 deferred items**: `/api/files` O(N) job_id lookup optimization; pytest `real_auth` marker refactor; systemd hardening (`NoNewPrivileges`, `PrivateTmp`); faster-whisper `BatchedInferencePipeline`; `app.py` / `index.html` refactor.

### v3.13 — R5 Server Mode Phase 5 (security + production hardening)
- **目標**：closes 13 issues found by Phase 5 prep investigation (5 BLOCKING bugs + 8 production-hardening items). After this phase the branch is safe to merge to main and deploy on real LAN. Plan: [docs/superpowers/plans/2026-05-10-r5-server-mode-phase5-plan.md](docs/superpowers/plans/2026-05-10-r5-server-mode-phase5-plan.md).
- **Tier 1 BLOCKING bugs (5/5 closed)**：
  - **T1.1 (B1, `7e31243`)** — `POST /login` with `{"username":null,"password":null}` was crashing with `AttributeError: 'NoneType' object has no attribute 'strip'` (500). Fix: `(data.get("username") or "").strip()` in `auth/routes.py`.
  - **T1.2 (B2, `d8cbd48`)** — SocketIO was using `cors_allowed_origins="*"`, bypassing the LAN-only Flask CORS allowlist. Now reuses `_LAN_ORIGIN_REGEX`. Also added `@socketio.on('connect')` auth check that returns False for unauthenticated clients (since Flask-SocketIO @on handlers don't go through `@login_required`).
  - **T1.3 (B3, `bb1d608`)** — `FLASK_SECRET_KEY` was silently falling back to placeholder `'change-me-on-first-deploy'` if env var unset. Now app raises `RuntimeError` at boot if env is missing or equal to placeholder. Setup scripts already write a generated key to `backend/.env`. `conftest.py` sets `test-secret-only-for-pytest-do-not-deploy` for the suite.
  - **T1.4 (B4+B5, `6c111fc`)** — `GET /api/profiles/<id>` and `GET /api/glossaries/<id>` had no ownership check (Phase 3 D4 only added `can_edit` for PATCH/DELETE). Non-owners could read any private profile/glossary by guessing the id. Added `can_view` method to `ProfileManager` + `GlossaryManager` (admin OR owner OR shared) and 403 in the GET handlers. LIST endpoints already filtered correctly.
  - **T1.5 (B6+B7, `a599b36`)** — A misconfigured handler that crashes immediately would create an infinite poison-pill loop: server crashes → boot recovery re-enqueues all 'running' → workers retry → crash → ... Fixed by adding `jobs.attempt_count` column (idempotent ALTER on existing DBs). `insert_job(parent_job_id=...)` increments the count. `recover_orphaned_running` honors `R5_MAX_JOB_RETRY` env (default 3) — orphans at-or-past cap are still failed but NOT re-enqueued. Operator must manually retry via `POST /api/queue/<id>/retry`. Standalone migration script under `backend/migrations/`.
- **Tier 2 production hardening (8/8 closed)**：
  - **T2.1 (C1, `5c1d8ff`)** — `WhisperEngine._get_model` cache key was `model_size` only, so two profiles with different `device` or `compute_type` would silently collide on the first profile's cached model. Cache key now includes `(model_size, device, compute_type)`.
  - **T2.2 (C2, `fce3b73`)** — `JobQueue.__init__` accepts optional `app=` kwarg; `_run_one` wraps each handler invocation in `app.app_context()` when set. Without this, anything in handlers that touches `current_app` raises `RuntimeError("Working outside of application context")` from the worker thread. Backward-compat: `app=None` default preserves Phase 1-4 callers.
  - **T2.3 (C3, `cddb2fd`)** — All 3 SQLite DBs (jobs, users, audit) initialized with `journal_mode=WAL`, `synchronous=NORMAL`, `temp_store=memory`. WAL allows concurrent reads while a worker writes; NORMAL trades a tiny crash-recovery window for ~2× write throughput.
  - **T2.4 (C4, `f8ddbc4`)** — `SESSION_COOKIE_SAMESITE='Lax'` (always), `SESSION_COOKIE_SECURE=(R5_HTTPS != '0')`, `SESSION_COOKIE_HTTPONLY=True` (explicit). SameSite mitigates CSRF on cross-origin POST/PATCH/DELETE.
  - **T2.5 (C5, `9dcfeff`)** — `GET /api/renders/<id>`, `GET /api/renders/<id>/download`, `DELETE /api/renders/<id>` previously had only `@login_required` — any logged-in user could read/cancel/download any render. Added `_can_access_render(render_id, user)` helper that walks render → file → user_id and 403s non-owners (admin can access any).
  - **T2.6 (C6, `c5d6a12`)** — `TranslationEngine.translate()` ABC + mock + ollama (single-segment + sequential batched paths) accept `cancel_event=None`. When set, raises `JobCancelled` at batch/segment checkpoints. OpenRouter inherits via `OllamaTranslationEngine`. `_auto_translate` threads cancel_event through. Without this, cancelling an in-flight MT job during a long batch (e.g., 30s LLM call) would still complete the rest before stopping.
  - **T2.7 (C7, `7df6aec`)** — `_atomic_set_admin` and `_atomic_delete_user` use `BEGIN IMMEDIATE` so that two concurrent demote/delete attempts of the only 2 admins serialize. Without this, both could observe `count_admins==2`, both succeed, and the system ends up with 0 admins. Routes wired to use the helpers; concurrent test (`Barrier(2)` + 2 threads) verifies count stays ≥1.
  - **T2.8 (C8, `d056ae3`)** — `ProfileManager` + `GlossaryManager` grow `update_if_owned(profile_id, user_id, is_admin, patch)` and `delete_if_owned(...)`. Per-resource lock dict (lazy-init via master lock) makes `can_edit + update/delete` atomic. Closes the TOCTOU window where a non-owner could observe `can_edit==True` against a stale snapshot, then write after the owner deletes.
- **Shared Contracts updated**: 5 new ownership-checked GET rows (`/api/profiles/<id>`, `/api/glossaries/<id>`, `/api/renders/<id>`, `/api/renders/<id>/download`, `DELETE /api/renders/<id>` all return 403 for non-owners). `jobs.attempt_count` column added to schema. 5 new default-values bullets (SECRET_KEY required, retry cap, SocketIO auth, cookie attrs, cancel latency).
- **Tests**: 673 backend tests pass + 1 known v3.3 macOS tmpdir baseline failure (no regression from Phase 5). New tests added across Phase 5: 8 phase5_security (login null + SocketIO + SECRET_KEY) + 5 phase5_ownership + 8 poison_pill_retry + 4 whisper_singleton + 3 worker_app_context + 3 sqlite_wal + 3 csrf_cookie + 5 render_ownership + 6 engine_cancel_event + 5 admin_atomic + 8 profile_glossary_toctou = ~58 new.
- **Live curl smoke verified**: T1.1 (null login → 400), T1.3 (boot crash without secret), T1.4 (admin can read), T2.4 (real `Set-Cookie: HttpOnly; SameSite=Lax`).
- **Plan adherence notes**：
  - B2 inline catch: `socketio.handlers` is an empty queue list (not a dict); real handlers live at `socketio.server.handlers['/']`. Test rewritten to use `socketio.test_client` which routes through the actual connect path.
  - B3 inline catch: `del sys.modules["app"]` in reload tests poisoned 18 downstream tests; `_restore_app_module` fixture snapshots+restores `app` and child auth/jobqueue modules.
  - B4+B5 inline catch: AUTH_DB_PATH monkeypatch didn't update the user_loader closure (captures module-level constant at boot). Fixture writes test users into the existing app DB and cleans up via `delete_user`, matching Phase 3 admin-test pattern.
- **Phase 6 deferred items — status audited 2026-05-13 (v3.15 cleanup)**:
  - ✅ DONE: rate limiting on /login + /api/queue (v3.14); password policy (v3.14); `/api/files` O(N) job_id optimization (v3.12 Phase 4 B); queue-panel.js setInterval leak (v3.14); `/api/ready` endpoint (v3.14); failed-login audit log (v3.14); pytest `real_auth` marker infrastructure (v3.15 — marker registered + fixture wired, `_REAL_AUTH_MODULES` retained as backward-compat fallback)
  - 🚫 N/A: systemd hardening (NoNewPrivileges, PrivateTmp) — project targets macOS LaunchAgent / interactive; no systemd deployment path
  - 📋 Still backlog: faster-whisper `BatchedInferencePipeline` (newer API, needs real-audio validation before shipping); `app.py` (~3700 lines) + `index.html` (~4700 lines) refactor split (multi-day architecture work); `/api/translation/engines` Ollama probe timeout (994ms outlier observed; needs HTTP timeout + memoization)

### v3.12 — R5 Server Mode Phase 4 (job_id exposure + mobile UI + cancel running)
- **目標**：closes 3 items from Phase 3 hand-off backlog — exposes job_id on `/api/files` so the dormant cancel button activates, redesigns dashboard + proofread for mobile, enables cancel of in-flight jobs (worker interrupt). Plan: [docs/superpowers/plans/2026-05-10-r5-server-mode-phase4-plan.md](docs/superpowers/plans/2026-05-10-r5-server-mode-phase4-plan.md).
- **`/api/files` job_id exposure (Phase 4 B, 3 任務)**: `GET /api/files` joins per-file active job_id from `list_jobs_for_user(status IN ('queued','running'))`. Returns `job_id: str | null` per file (null if no active job). File-card cancel button (Phase 3 E4) was guarded by `f.job_id` which was always undefined — now activates correctly.
- **Mobile responsive UI (Phase 4 C, 6 任務)**: New `frontend/css/responsive.css` with breakpoints at ≤768px (mobile, hamburger drawer + stacked file-cards + tabbed proofread editor) and ≤1024px (tablet, narrower sidebar). Vanilla `@media` queries — no framework. New IDs: `mobileHamburgerBtn`, `mobileSidebarDrawer`, `mobileSidebarOverlay`, `proofreadMobileTabVideo`, `proofreadMobileTabSegments`. Backend serves `/css/<path>` static route. Playwright tests at 1920×1080 + 375×667 (iPhone) + 768×1024 (iPad).
- **Cancel running jobs (Phase 4 D, 5 任務)**: `JobCancelled` exception class in `jobqueue/queue.py`. Per-job `threading.Event` keyed by job_id in `JobQueue._cancel_events` dict. `_run_one` creates event before invoking handler, passes via `cancel_event=` kwarg. `JobQueue.cancel_job(job_id)` sets the event. `DELETE /api/queue/<id>` for status='running' returns 202 with `{ok:true, status:"cancelling"}`; for status='queued' returns 200 (existing). `transcribe_with_segments` polls between Whisper segments (~1s). `_auto_translate` polls between MT batches (~30s worst case). Frontend cancel button activates for both queued + running; "取消中..." toast on 202.
- **Inline catches**:
  - C6 (commit `ccdbf92`): 3 CSS bugs in C1's responsive.css scaffold — cascade order (defaults after @media), drawer hide via transform vs display, overlay z-index intercepting clicks — fixed inline before suite went GREEN.
  - D3: `_auto_translate` had broad `except Exception` that would silently swallow JobCancelled — added re-raise guard so cancel propagates to `JobQueue._run_one` and flips status='cancelled'.
- **Tests**: 615 backend pass + 1 baseline. Playwright 6/6 GREEN (login + admin + 4 responsive scenarios).
- **Phase 5 hand-off backlog**: email notification on job done; admin user-settings page; job retry exponential backoff; public internet exposure (out of scope per design D6).

### v3.11 — R5 Server Mode Phase 3 (admin dashboard + per-user Profile/Glossary + cancel/retry)
- **目標**：admin can manage users + view audit log; per-user Profile + Glossary visibility/edit isolation; queued job cancel + failed job retry. Plan: [docs/superpowers/plans/2026-05-10-r5-server-mode-phase3-plan.md](docs/superpowers/plans/2026-05-10-r5-server-mode-phase3-plan.md).
- **Admin dashboard (Phase 3 B+C, 12 任務)**: `backend/auth/admin.py` blueprint — `GET /api/admin/users` (list), `POST /api/admin/users` (create + 409 on dupe), `DELETE /api/admin/users/<id>` (with self-delete + last-admin guards), `POST /api/admin/users/<id>/reset-password`, `POST /api/admin/users/<id>/toggle-admin`, `GET /api/admin/audit?limit=&actor_id=`. `auth/audit.py` adds `audit_log` SQLite table + `log_audit` / `list_audit` helpers. Frontend `frontend/admin.html` with 4 tabs (Users / Profiles / Glossaries / Audit) + `frontend/js/admin.js`. Backend serves `/admin.html` admin-only (302→login if not). Top-bar admin link visible only when `is_admin`. Phase 3 Playwright spec (admin login → user CRUD → audit visibility) GREEN.
- **Per-user Profile + Glossary (Phase 3 D, 6 任務)**: ProfileManager + GlossaryManager grow optional `user_id` field on each JSON (null = shared/admin-only-edit, non-null = owner+admin only). New methods `list_visible(user_id, is_admin)` + `can_edit(...)`. `GET /api/profiles` and `GET /api/glossaries` filtered via list_visible. Migration script `backend/scripts/migrate_owner_fields.py` backfills `user_id: null` on pre-Phase-3 entries.
- **Cancel queued + retry failed (Phase 3 E, 4 任務)**: `DELETE /api/queue/<id>` for status='queued' → marks DB cancelled + 200 (already covered Phase 1). `POST /api/queue/<id>/retry` for status='failed' → creates NEW job entry (new id) with same file_id+type, leaves failed entry in DB for audit. Frontend file-card adds Retry button on failed (`queueRetryBtn-<file_id>`).
- **Inline catches**: B6 ralph-backend touched test_admin_users.py (process violation; signature change broke 2 existing tests; pragmatic in-place fix kept suite green); C1 implementer added duplicate `_FRONTEND_DIR` at line 3036 (fixed inline) + missed B5 test_admin_users.py changes from B6 commit (included in C1 cleanup).
- **Tests**: 607 backend pass + 1 baseline. Playwright admin spec (login → create user → list → reset password → audit visible) GREEN.
- **Phase 4 hand-off backlog**: /api/files job_id field; mobile responsive UI; cancel-while-running.

### v3.10 — R5 Server Mode Phase 2 (queue end-to-end + HTTPS + Linux)
- **目標**：closes Phase 1 hand-off backlog — unifies ASR + MT through JobQueue worker, ships Linux/GB10 setup, adds self-signed HTTPS so LAN deployment can drop the cleartext caveat. Plan: [docs/superpowers/plans/2026-05-10-r5-server-mode-phase2-plan.md](docs/superpowers/plans/2026-05-10-r5-server-mode-phase2-plan.md). Validation report: [r5-progress-report.md](docs/superpowers/r5-progress-report.md).
- **ASR pipeline (Phase 2B, 7 任務)**：`_asr_handler` 由 Phase 1 stub 升級成 full pipeline — registry status='transcribing' → calls `transcribe_with_segments` → persists segments/text/backend/asr_seconds → enqueues translate job (instead of inline `_auto_translate`). `/api/files/<id>/transcribe` (re-transcribe) 同 `/api/transcribe` 一樣 enqueue + 202 + job_id；舊 `do_transcribe` inline thread 完全 drop。`/api/transcribe/sync` 加 `@admin_required` 防止 GPU concurrency bypass。Frontend: file-card 識別 `'uploaded'` status → 顯示 "排隊中" badge (`badge--awaiting-asr`) 同 `.dot` 動畫；舊嘅 `badge--enqueued` 名因為同 `badge--queued` (待翻譯) 撞 → renamed `badge--awaiting-asr`。
- **MT pipeline (Phase 2C, 7 任務)**：`_auto_translate(fid, segments, session_id)` → `_auto_translate(fid, sid=None)` — segments 由 registry 自取，sid optional 畀 worker 可以唔需要 request context。`_mt_handler(job)` 由 `NotImplementedError` stub → 真正 bridge to `_auto_translate(file_id)`。`_asr_handler` 嘅 inline `_auto_translate(file_id)` call 改為 `_job_queue.enqueue(job_type='translate')` — 利用 MT worker pool 嘅 3 個 concurrent。`/api/translate` 由 sync 改 enqueue + 202 + job_id；body 入面 file_id 所以 owner check 手寫（`@require_file_owner` 只 cover `<file_id>` URL parameter）。Test infrastructure: `client_with_admin` fixture pattern 同 B3，`_profile_manager.get_active` monkeypatch 防 test isolation pollution。
- **Linux/GB10 setup (Phase 2D, 4 任務)**：`setup-linux-gb10.sh` mirror setup-mac.sh 嘅結構 + env-driven admin bootstrap (防 shell injection)。aarch64 PyPI wheels confirmed available — `nvidia-cublas-cu12==12.4.5.8` (manylinux2014_aarch64) + `nvidia-cudnn-cu12-9.22.0.52` (manylinux_2_27_aarch64) — 直接 `pip install` 就得，唔需要 NVIDIA APT repo fallback。README 加 Linux quick-start 行。
- **Self-signed HTTPS (Phase 2E, 7 任務)**：新 `backend/scripts/generate_https_cert.py` — `generate_self_signed_cert(out_dir, common_name, days=365)` 用 mkcert 優先（auto-trusts dev CA）、openssl fallback。Idempotent — existing cert pair 直接 return path。`backend/app.py` 抽出 `_boot_socketio()` helper：`R5_HTTPS=0` opt-out；`R5_HTTPS_CERT_DIR` env 控制 cert 位置（default `backend/data/certs`）；cert 兩個文件 (`server.crt` + `server.key`) 都存在就 auto-enable `socketio.run(ssl_context=(crt, key))`。三個 setup script 都加 `python scripts/generate_https_cert.py data/certs` step；`.gitignore` exclude `backend/data/certs/`。
- **Tests**：572 backend tests pass + 1 已知 v3.3 macOS tmpdir baseline failure（無 regression from Phase 2）。新增 ~11 個 backend test 來自 Phase 2：3 ASR pipeline + 3 MT pipeline + 1 /api/translate enqueue + 4 HTTPS boot + 1 isolation guard。Phase 1 嘅 Playwright login flow re-run 1/1 GREEN。
- **Plan deviations vs prescription**（all documented in plan checkbox annotations）：(1) ralph-backend touched test files in C2 (signature change broke 2 existing tests; pragmatic in-place fix kept suite green; future iterations should escalate to ralph-tester); (2) C2 test_mt_handler_pipeline.py needed extra `_profile_manager.get_active` monkeypatch for test isolation; (3) B6 frontend reviewer caught `badge--enqueued` ↔ `badge--queued` collision pre-merge → renamed `badge--awaiting-asr`; (4) C1 spec reviewer false positives on FakeEngine/tmp_path/monkeypatch all verified inline.
- **Phase 2 known boundaries / Phase 3 hand-off**：admin dashboard CRUD UI；per-user Profile/Glossary override；email notification on job done；cancel queued job；job retry/resume after server restart。

### v3.9 — R5 Server Mode Phase 1 MVP (multi-user + auth + queue)
- **目標**：由 single-user CLI 工具升級成 self-hosted multi-client server，畀 3-5 人小團隊喺 LAN 共用同一部主機。完整 plan 喺 [docs/superpowers/plans/2026-05-09-r5-server-mode-phase1-plan.md](docs/superpowers/plans/2026-05-09-r5-server-mode-phase1-plan.md)。
- **Auth (Phase 1B, 11 任務)**：`backend/auth/` 新 package — `passwords.py`（bcrypt rounds=12）、`users.py`（SQLite users + jobs schema、`init_db` / `create_user` / `verify_credentials`）、`routes.py`（`POST /login` → 200 + session cookie / 401；`POST /logout`；`GET /api/me`）、`decorators.py`（re-export `@login_required`，加 `@require_file_owner` 同 `@admin_required`，內建 `R5_AUTH_BYPASS` config knob 畀 conftest 用）。`app.py` boot 時 init_db、bind LoginManager、register blueprint、條件性 bootstrap admin（讀 `ADMIN_BOOTSTRAP_PASSWORD` env）。所有 58 個現有 data endpoint 加 `@login_required` 或 `@require_file_owner`（公開只剩 `/api/health` + `/fonts/<path>`）。
- **Job queue (Phase 1C, 8 任務)**：`backend/jobqueue/`（package 名特意避開 stdlib `queue`，避免 worker 嘅 `import queue as stdqueue` shadow 問題）— `db.py` (jobs table CRUD + crash-recovery `recover_orphaned_running`)、`queue.py` (`JobQueue` 用 `threading.Thread` worker，1 ASR + 3 MT，daemon=True，sentinel-based shutdown，handler exception 自動 `status=failed` 加 traceback)、`routes.py` (`GET /api/queue` 按 owner filter，admin 見全部；`DELETE /api/queue/<id>` owner-only + 409 如非 queued)。`/api/transcribe` 改為 enqueue + 返 202 with `{file_id, job_id, queue_position}`，drop 原本 do_transcribe inline thread。
- **Per-user file isolation (Phase 1D, 5 任務)**：`_filter_files_by_owner` helper、`_register_file(..., user_id=)` kwarg、`/api/files` 過濾、`@require_file_owner` 應用到全部 16 個 `<file_id>` route。`_user_upload_dir(uid)` 起 `data/users/<uid>/uploads/` 目錄，registry 新欄位 `file_path` 記絕對路徑，`_resolve_file_path()` legacy fallback 去 `UPLOAD_DIR / stored_name`。一次性 migration script `backend/scripts/migrate_registry_user_id.py` 將 pre-R5 文件回填 admin（user_id=1）。
- **Frontend (Phase 1E, 6 任務)**：`frontend/login.html`（vanilla form，POST /login → redirect /）、`frontend/js/auth.js`（`fetchMe` + `logout`）、`frontend/js/queue-panel.js`（3s auto-refresh /api/queue + cancel button）。`index.html` `.b-topbar` 加 user chip + logout button（grid 由 3 cols 擴成 4 cols）；`.b-col` 加多一個 panel 顯示 job queue。Backend 加 `GET /` redirect / index.html、`GET /login.html`、`GET /js/<path>`、`GET /proofread.html` 配合靜態服務（之前 frontend 用 `file://` 開）。Playwright spec [test_login_flow.spec.js](frontend/tests/test_login_flow.spec.js) 跑通 admin → dashboard → logout 全流程。
- **LAN exposure (Phase 1F, 2 任務)**：`_is_lan_origin` helper + `_LAN_ORIGIN_REGEX`（regex string，**唔用 plan 寫嘅 lambda — flask-cors 6.0.2 會喺 `for o in origins` iterate，lambda 唔可 iter，會炸 151 個 test**）；CORS allowlist 限 localhost + 10/8 + 172.16/12 + 192.168/16 + 127/8。`if __name__ == '__main__':` 改用 `BIND_HOST` env 預設 `0.0.0.0`、`FLASK_PORT` env 預設 5001（畀 test 同 multiple instance 避免衝突）。
- **Setup scripts (Phase 1G, 3 任務)**：`setup-mac.sh`（Apple Silicon 限定，安裝 mlx-whisper）、`setup-win.ps1`（裝 ctranslate2 嘅 cublas64_12 + cudnn64_9 wheel）。兩個都互動 prompt 起 admin + 生成 `FLASK_SECRET_KEY` 寫入 `backend/.env`（gitignore）。Admin 用戶名 + 密碼透過 `os.environ` / `$env:` 傳入 python heredoc，唔做 string interpolation — 防 shell injection。
- **Tests + verification**：561 pytest pass + 1 已知 v3.3 macOS tmpdir baseline failure（無回歸）。Playwright 1/1 GREEN（2.5s，real Chromium against `BASE_URL=http://localhost:5002`）。新增 ~33 個 backend test：5 passwords、8 users、5 auth_routes、7 decorators、7 queue_db、4 queue、2 queue_routes、2 user_isolation、1 lan_cors、+ 2 R5_AUTH_BYPASS 補測。
- **Validation-First adherence**：每 task 行 RED → GREEN → 4-stage gates → ralph-validator 對 Shared Contracts 比對；任何 plan 同 production 唔 align 嘅地方（cookie_jar 改用 werkzeug 3 get_cookie API、@login_required vs Flask request context、queue 包 shadow stdlib、flask-cors callable bug、setup script shell injection）即時記入 plan annotation。
- **Phase 1 known boundaries**（明確留 Phase 2）：`_asr_handler` 只寫 user_id 入 registry，**唔 trigger** 完整 segments / status update + auto-translate（legacy `do_transcribe` wrapper 仲負責 sync 同 re-transcribe 路徑）；`_mt_handler` 直接 `raise NotImplementedError`（冇 entry point enqueue MT job）。

### v3.8 — Chinese ASR Quality (initial_prompt + s2hk + cascade fix)
- **問題**：用 mlx-whisper `language="zh"` 處理粵語廣播片時三重問題：(1) 頭幾秒嘅 training-data hallucination — 例如「中文字幕由 XXX 提供」、「粟米片」、「猫,超喜欢猫」等隨機 token 出現喺實際 audio 之前 30 秒（因為 Whisper 對非語音音訊冇處理，跌入 high-frequency training token mode）；(2) 預設輸出**簡體中文**（Whisper 中文 corpus 偏 Mandarin）；(3) **連環重複 hallucination** — 156 段入面 53 段（34%）係前段嘅原文重複，因為 ZH profile 仲開 `condition_on_previous_text=true`，decoder 將前段嘅輸出當 prompt 餵回去，唔出新內容。**呢個正係之前 EN profile 已經修咗嘅 cascade bug，但 ZH profile 一直冇 update**。Cascade 期間真實 speech content 永久遺失。
- **`initial_prompt` 暴露入 ASR engine wrapper**：mlx-whisper（[backend/asr/mlx_whisper_engine.py](backend/asr/mlx_whisper_engine.py)）同 faster-whisper / openai-whisper（[backend/asr/whisper_engine.py](backend/asr/whisper_engine.py)）兩條路徑都加 `initial_prompt` config 欄位，配合 schema entry 喺 Profile 動態參數面板顯示。Empty string 自動 normalize 做 `None`（避免空 prompt 干擾 decoder）。Prompt 三重作用：(a) 提供 context anchor 防 head hallucination；(b) prompt 用繁體字寫 → bias decoder 偏向繁體 token；(c) 提示主題（例如「香港賽馬新聞」改善專名識別）。
- **`asr.simplified_to_traditional` flag + OpenCC s2hk 後處理**：[backend/config/languages/zh.json](backend/config/languages/zh.json) 加 `"simplified_to_traditional": true`；[backend/language_config.py](backend/language_config.py) `_validate()` 強制 boolean 類型；[backend/asr/cn_convert.py](backend/asr/cn_convert.py) 新 module 用 `opencc-python-reimplemented`（已喺 requirements）做 simplified→Hong Kong Traditional 轉換。Module-level cache 避免每段重新 load OpenCC config dict。Pipeline 接駁位：[backend/app.py](backend/app.py) `transcribe_with_segments()` 入面，喺 `merge_short_segments()` 之後 conditional apply（flag false 時完全冇 import overhead）。Word-level timestamps 入面 `words[].word` 都會跟住轉換，DTW 對齊保持一致。
- **驗證樣本**：`这天新10磅仔袁幸尧出席记者会` → `這天新10磅仔袁幸堯出席記者會`（袁幸尧 → 袁幸堯 係 HK style 標準轉法）；`我们为了国家` → `我們為了國家`。Immutable transformation：原 list 唔被修改、返回新 list。
- **修復目標 Profile**：[backend/config/profiles/b877d8b5-...json](backend/config/profiles/b877d8b5-5c44-46d9-af74-bf6367eb51c0.json) — `condition_on_previous_text: true → false` + 加 `"initial_prompt": "以下係香港賽馬新聞，繁體中文。"`
- **15 個新 tests**：7 個 [test_cn_convert.py](backend/tests/test_cn_convert.py)（基本轉換 / 不變性 / 時間欄位保留 / 空文本 pass-through / word-level 轉換 / 通用 glyphs / 緩存）+ 6 個 [test_asr.py](backend/tests/test_asr.py)（mlx schema、whisper schema、faster-whisper kwarg forwarding、None 默認、空字串 normalize、openai-whisper path）+ 2 個 [test_language_config.py](backend/tests/test_language_config.py)（s2t boolean 驗證 / true & false 持久化）；改 1 個既有 test 兼容新 `initial_prompt=None` kwarg。
- **510 backend tests pass**（baseline 495 + 15 new；唯一失敗仍係 v3.3 已存在嘅 macOS tmpdir colon-escape test）。
- **未做**：VAD filter（mlx-whisper 冇 built-in，需 silero-vad 或者 faster-whisper hybrid）— 預期 `initial_prompt` 已經解 80% 頭 hallucination，VAD 係 marginal improvement，留待用戶報告為準。

### v3.8 — MT Single-Segment Mode (Strategy E, `batch_size=1`)
- **問題**：Batched translation（default `batch_size=10`）將相鄰 EN segments 一齊餵畀 LLM，LLM 做 sentence-level 翻譯然後 redistribute 落各行，引致：(a) **錯位**（極端例子：`Italian side Como.` 段嘅 ZH 變咗 `沃爾夫斯堡的穆罕默德·阿莫拉速度如閃電般迅捷。`，係下一段嘅內容），(b) **Bloat**（`it will not be an easy search.` 變 `因此，車路士要物色到合適的中場人選，將是一項艱鉅任務。` — 加咗主語、連接詞、文學形容詞），(c) **相鄰段重複**（兩段都重複介紹同一個球員）
- **`OllamaTranslationEngine` 新增 single-segment 路徑**：當 `batch_size=1` 時，bypass 既有 batched flow，每段獨立發送 LLM 請求，無 neighbour context、無 cross-segment redistribution，guarantee 1:1 對齊
- **新 `SINGLE_SEGMENT_SYSTEM_PROMPT`**：精簡規則 — 中文字數 0.4–0.7× EN、禁止加任何外部資訊、即使原文片段譯文亦要係可朗讀子句、單行直接輸出。內含 6 個 in-context example 包括 problematic case (`Italian side Como.`、`it will not be an easy search.`)
- **`_translate_single()` 同 `_translate_single_mode()` helper**：sequential 或 parallel（透過 `parallel_batches`）派送單段請求；空 EN 直接返回空譯文，唔 call LLM；glossary 按 per-segment EN 過濾（唔再對成個 batch）
- **`_parse_single_response()`**：strip `譯文：` / `中文：` / `Translation:` 前綴，取第一行非空輸出
- **`Pass 2 enrichment` 仍然兼容**：`translation_passes: 2` 喺 single-mode 之後一樣可以行，逐段 enrich
- **Empirical validation**（22 段問題段，Real Madrid clip）：
  - 平均 ZH/EN ratio 由 0.61 → 0.31（達標 0.4–0.7 區間）
  - Bloat (>0.85) 由 3/22 → **0/22**
  - 嚴重錯位（#102 Como）：完全解決，`Italian side Como.` 譯做 `意甲球會科莫。`（perfect 1:1）
  - 相鄰重複（#50/#51 Tchouameni）：完全解決，名只出現一次
  - 速度：22 段 7.9s = 0.36s/seg；推算 115 段 ~41s（< 1 分鐘）
- **EN language config default 改為 `batch_size: 1`**（廣播質量優先；用戶想快可以調返高）；ZH config 保持 `batch_size: 8`（中文翻譯 cross-segment 漂移問題冇 EN 咁明顯）
- **5 個新 unit test**：dispatch verification、label-prefix stripping、empty-text skip、per-segment glossary filter、batch>1 path 確認唔 trigger single-mode
- **既有 sliding-window test 更新**：原本用 `batch_size=1` 做 forcing function 來測 cross-batch context；改用 `batch_size=2` + 4 segments 改為 force 2 batches，繼續 cover sliding window 邏輯
- **495 automated tests pass**（baseline 489 + 5 新 single-mode + 1 修改嘅 sliding-window）

### v3.8 — ASR Sentence-Fragment Cleanup (`merge_short_segments`)
- **問題**：即使 `condition_on_previous_text=false` 解決咗 Whisper 級聯 hallucination，mlx-whisper large-v3 仍然會喺 sentence boundary / 短停頓位置產出 1–2 字嘅孤兒 fragment（例如：`'a'` / `'Tchouameni.'` / `'settle.'`），燒入字幕只顯示 0.3 秒，肉眼幾乎讀唔到，亦浪費翻譯 token
- **`asr/segment_utils.py` 新增 `merge_short_segments()`**：句子標點啟發式 — 短 segment 以 `.!?` 結尾 → 視為句尾 → backward merge 入上一段；唔以標點結尾 → 視為句頭 → forward merge 入下一段。Iterative loop（max 3 passes）直至穩定，idempotent
- **守門條件**：(a) 時間 gap > `merge_short_max_gap` 秒就跳過（預設 0.5s，避免跨越長停頓）；(b) 合併後字數會超過 `max_words_per_segment` cap 就跳過；(c) `merge_short_max_words=0` 等於停用 merge（zh.json 預設停用，因英文標點 `.!?` 唔覆蓋中文 `。！？`）
- **Word-level timestamp preservation**：當兩邊都有 DTW alignment `words` field，merge 時 concatenate，唔遺失粒度
- **Pipeline 接駁位**：`transcribe_with_segments()` 入面 chain 喺 `split_segments()` 之後 — `split` 拆長、`merge` 合短，互補
- **Language config schema**：[en.json](backend/config/languages/en.json) / [zh.json](backend/config/languages/zh.json) 加兩個 knob — `merge_short_max_words`（int 0–10，0=停用）+ `merge_short_max_gap`（float 0–10s）；[language_config.py](backend/language_config.py) `_validate()` 範圍檢查
- **EN default 啟用**（`merge_short_max_words: 2`、`merge_short_max_gap: 0.5`），ZH default **停用**（`merge_short_max_words: 0`，等中文標點支援之後再 enable）
- **Validation evidence**：File `e5e33353fb3e`（Real Madrid clip）— ASR 輸出 118 segments / 3 個 ≤2-word fragment → merge 後 115 segments / 0 fragments，3 段全部讀通；synthetic 8 個 edge case（gap、cap、chained shorts、首尾 boundary、disable、idempotent、empty）全過
- **11 個新 unit test**（`test_segment_utils.py::test_merge_*`）— 涵蓋雙向、跳過守門、鏈式 loop、word timestamp、disable、idempotency、empty input
- **289+11 = 489 automated tests pass**（baseline 478，+11 new；保留 1 個 v3.3 已知 macOS tmpdir colon-escape failure）
- 設計文件：[docs/superpowers/specs/2026-05-08-merge-short-segments-design.md](docs/superpowers/specs/2026-05-08-merge-short-segments-design.md)

### v3.0 — Modular Engine Selection (進行中)
- **引擎模塊化**: ASR 同翻譯引擎可獨立選擇、獨立配置，唔綁定 Profile
- **引擎參數 API**: 每個引擎提供 param schema + 可用模型列表
- **前端引擎選擇器**: 動態參數面板、可用性即時偵測
- **Profile 增強**: 從固定綁定改為快速預設 + 自由組合
- **Profile CRUD UI**: 側邊欄 Profile 管理介面 — 建立、編輯、刪除 Profile，15 個欄位分 4 個折疊區塊（基本資訊/ASR/翻譯/字型），active Profile 刪除保護
- **Engine Selector + Dynamic Params Panel**: ASR 同翻譯引擎選單從 API 動態載入（含可用性顯示），切換引擎時自動 fetch params schema 並渲染對應參數欄位；翻譯引擎顯示 model 載入狀態；修正原本錯誤的引擎名稱（"qwen3" → "qwen3-asr"）
- **Whisper Layer 1 Segment Control**: ASR 引擎 schema 加入三個 faster-whisper 原生分段參數（`max_new_tokens`／每句字幕長度上限、`condition_on_previous_text`、`vad_filter`），透過 Profile 表單動態參數面板控制；前端新增 boolean 類型欄位支援同 nullable integer placeholder
- **Legacy UI cleanup**: 移除 sidebar 遺留嘅 `#modelSelect` Whisper 模型選擇器及相關函數（`preloadModel()`、`populateModelSelect()`、`updateModelHint()`）；Profile 系統已接管所有引擎控制，legacy 控制項已無用
- **Ollama Cloud 模型支援**：新增 3 個 cloud engine（`glm-4.6-cloud`、`qwen3.5-397b-cloud`、`gpt-oss-120b-cloud`），透過現有 Ollama CLI `signin` 機制存取；前端 Profile 翻譯引擎 dropdown 分「本地模型」同「雲端模型（需要 ollama signin）」兩個 `<optgroup>`，未可用嘅選項顯示 `⚠` + tooltip 提示
- **MP4/MXF 渲染 Bug 修正**：修正 6 個渲染相關 bug：(1) `renderer.render()` 返回 `(bool, Optional[str])` tuple 而非 bool，FFmpeg stderr 正確傳遞；(2) render job 加入 `output_filename` 欄位（格式：`{stem}_subtitled.{ext}`）；(3) `send_file()` 加入 `download_name` 參數確保正確檔名；(4) `proofread.html` 修正 `approved` 欄位映射（`seg.status === 'approved'`）；(5) `loadMedia()` 在影片載入失敗時 resolve 而非 reject；(6) 渲染按鈕 click handler 修正 `fileId` → `state.fileId` scope 問題（關鍵 bug：`const fileId` 在 `init()` 內，click handler 在外層 scope，`'use strict'` 下拋出 `ReferenceError` 導致渲染完全失效）
- **渲染匯出參數面板**：點擊「匯出燒入字幕」開啟渲染設定 Modal；MP4 可調 CRF（0-51 slider）、編碼速度（ultrafast→veryslow）、音頻碼率、輸出解像度；MXF 可選 ProRes 規格（Proxy/LT/Standard/HQ/4444/4444XQ + 碼率說明）、音頻位深（16/24/32-bit PCM）、輸出解像度；後端 `_validate_render_options()` 完整驗證所有欄位並返回 400 + 明確錯誤信息；`render_options` 存入 job dict 並出現在 status API 響應
- **Preview Font Sync**: SVG subtitle overlays in `index.html` and `proofread.html` now reflect Active Profile font config (family, size, color, outline, margin) in real-time via Socket.IO `profile_updated` event; replaced hardcoded CSS div with SVG `<text paint-order="stroke fill">` for true per-character outline matching ASS renderer output
- **274 automated tests**（+3 new: profile_updated emit on activate, PATCH-active, PATCH-inactive）
- **Find & Replace + Apply Glossary**: Find & Replace toolbar in `proofread.html` — search zh/en columns with live highlight, match navigation (▲/▼, Enter/Shift+Enter), Replace One/All (zh_text only), 只搜未批核 checkbox, Apply Glossary (violation detection + preview modal + batch PATCH). Opened via `Cmd+F`. No backend changes.
- **Processing Time Visibility + Parallel Batch Translation**: `asr_seconds` stored in file registry after transcription; `elapsed_seconds` added to `translation_progress` event; new `pipeline_timing` WebSocket event on translation completion shows ASR/translation/total breakdown; `parallel_batches` parameter (1–8) in Profile translation block enables `ThreadPoolExecutor` parallelism in `OllamaTranslationEngine`; context window disabled in parallel mode; Profile form field with hint text.
- **Proofread 兩個新 Panel**: 影片預覽下方加入「詞彙表對照」+「字幕設定」兩個 panel。詞彙表 panel 支援從所有 glossary 中選擇、查看/新增/編輯條目（inline）；字幕設定 panel 直接編輯 active profile 嘅 font config（字型、大小、顏色、輪廓、邊距），500ms debounce 後自動 PATCH，透過 Socket.IO 即時更新 overlay
- **Glossary Apply（LLM 智能替換）**: Proofread page 詞彙表 panel 新增「套用」按鈕。Two-phase 流程：(1) `POST /api/files/<id>/glossary-scan` 用純字串匹配搵出違規（EN 包含 glossary term 但 ZH 唔包含對應翻譯）；(2) 預覽 modal 俾用戶剔選 violations（未批核預設勾選，已批核預設唔勾選）；(3) `POST /api/files/<id>/glossary-apply` 逐條調用 Ollama LLM 做智能替換（保留句子其他部分），多個違規同一 segment 時序列處理。後端會驗證 `(term_en, term_zh)` 確實屬於指定 glossary，錯誤訊息經 `app.logger.exception` 記錄並返回統一 `"LLM request failed"` 俾 client
- **304 automated tests**（+13 new: glossary-scan/apply 端到端 coverage，包含 sequential chaining、term validation、approval 狀態保留）

### v3.7 — Subtitle Source Mode (per-file EN / ZH / Bilingual)
- **`backend/subtitle_text.py`**: 新 module，shared resolver `resolve_segment_text(seg, mode, order, line_break)` + `strip_qa_prefixes` + `resolve_subtitle_source` / `resolve_bilingual_order` 三層 fallback helper（render-modal override > file > profile > `auto`）
- **`renderer.generate_ass()`**: 加 `subtitle_source` + `bilingual_order` keyword-only kwargs，default `auto`/`en_top`，預設行為同 v3.6 一樣
- **`POST /api/render`**: body 接 `subtitle_source` + `bilingual_order`；response 加 `warning_missing_zh`（zh-mode 缺 ZH 嘅段數，>0 時前端彈 amber toast）；`subtitle_source: "en"` 時跳過 approval gate（approval 係 ZH 概念）
- **`GET /api/files/<id>/subtitle.{srt,vtt,txt}`**: 加 `?source=` + `?order=` query param；冇就 fall back file → profile → auto；merge segments+translations 後過 resolver；line break 用 raw `\n`（ASS 用 `\\N`）
- **`PATCH /api/files/<id>`**: 接 `subtitle_source` + `bilingual_order`，`null` 清 override；validate enum
- **`PATCH /api/profiles/<id>`**: `font.subtitle_source` + `font.bilingual_order` 通過 `_validate_font` 驗證；新增可選 profile font 欄位：`font.subtitle_source`（`auto`/`en`/`zh`/`bilingual`）+ `font.bilingual_order`（`en_top`/`zh_top`）
- **Frontend**: file card mini dropdown（每個檔案獨立 override）、proofread header dropdown、render modal source override row、Profile save modal 新 fieldset（preset 字幕來源）；`pickSubtitleText` JS helper mirror backend resolver；dashboard overlay 同 proofread overlay 共用同一 resolver path
- **22 個 backend pytest**（helper / renderer / route / export / patch）+ **6 個 Playwright scenario** 全綠
- **469/481 backend tests pass**（12 pre-existing unrelated failures：11 Playwright E2E 需 browser、1 v3.3 macOS tmpdir colon-escape test）

### v3.6 — Live Preview / Burnt-in Output Fidelity (Phase 2 — font asset parity)
- **Background**：v3.5 將 overlay 換成 SVG `paint-order` 解決咗描邊幾何同 scaling math 兩個 fidelity gap，但 v3.5 結尾留低嘅最大缺口係 **glyph 本身**：browser 揀字行 OS font fallback chain，libass 行 fontconfig，兩邊揀到嘅可能根本唔係同一個 cut（甚至唔同 family）。Phase 2 將同一份 TTF/OTF 同時餵畀兩邊。
- **新 asset 目錄**（[backend/assets/fonts/](backend/assets/fonts/)）：用戶將 `.ttf` / `.otf` 掉入呢個目錄即生效，renderer 同 preview 即時拎到。詳細 README 喺 [backend/assets/fonts/README.md](backend/assets/fonts/README.md)：推介 Noto Sans TC / Source Han Sans TC / Noto Sans HK，全部 SIL OFL 可商用 + 重發。Repo 唔 bundle 任何字體 binary。
- **新 backend route**（[backend/app.py](backend/app.py)）：
  - `GET /api/fonts` — 列出 `assets/fonts/` 下所有 TTF/OTF，每項 `{file, family}`；family name 用 fontTools 由 font 嘅 `name` table（platform 3 / encoding 1 / langID 0x409 = Win Unicode English US 優先）抽取，fontTools 唔安裝就 fallback 去 file stem。
  - `GET /fonts/<filename>` — 透過 `send_from_directory` serve font binary；雙重防 traversal（Flask normalize + 我哋 enforce extension allowlist `{.ttf, .otf}`），唔可以攞嚟 exfiltrate 任何其他文件。
- **Renderer 加 fontsdir**（[backend/renderer.py](backend/renderer.py)）：
  - 新 `_has_bundled_fonts()` helper — boot 時掃 `assets/fonts/`。
  - 新 `_escape_for_ffmpeg_filter_arg()` helper — proper FFmpeg filter escaping（`\` → `\\`、`:` → `\:`、`'` → `\'`、`,` → `\,`）支援 Windows drive colon path。
  - `render()` 入面：有 bundled font 就 `ass={basename}:fontsdir={escaped_abs_path}`，冇就 fallback 去原本 `ass={basename}`。同 `:scale=` resolution 過濾器並存兼容（fontsdir 屬於 ass option，scale 係另一個 filter）。
- **Frontend `@font-face` injection**（[frontend/js/font-preview.js](frontend/js/font-preview.js)）：
  - `_injectBundledFonts()` 喺 `init()` 時自動 fetch `/api/fonts`，將每個 font 注入做 `@font-face` rule（`font-display: block` 防 fallback flash）。
  - `document.fonts.load()` eagerly preload 每個 face，等 first paint 已有 glyph cached，唔會 first segment 用 fallback metric 閃一格。
  - Preload 完之後 re-call `applyFontConfig()` 重 paint，確保 metric 100% 對。
- **行為總結**：
  - 用戶 drop `NotoSansTC-Regular.ttf` 入 `backend/assets/fonts/`；
  - 開 dashboard 或 proofread page → `/api/fonts` 列出 → frontend 注入 `@font-face` 用呢個文件；
  - 燒入時 → renderer 加 `fontsdir=` → libass 用同一個文件；
  - 結果：browser preview 同最後燒入嘅 video 用一模一樣嘅 glyph、metrics、kerning。
- **Optional dep**：`fontTools` — 安裝先有真 family name (`Noto Sans TC`)，唔安裝就用 file stem (`NotoSansTC-Regular`)。renderer 完全唔需要 fontTools，純 preview 體驗加分。
- **Tests**：8 個 fonts API tests（[tests/test_fonts_api.py](backend/tests/test_fonts_api.py)）— empty dir、列出 TTF + OTF + 過濾非字體、missing dir 唔 crash、serve OK / 404、extension allowlist、path traversal 防護。10 個 renderer fontsdir tests — escape helper（plain / Windows drive / quote / comma）、無 bundle font 唔加 fontsdir、有 bundle 加 fontsdir、fontsdir 同 scale resolution 並存兼容。**425 backend tests pass**（除咗 v3.3 已存在嘅 ass-colon-escape macOS tmpdir test）。

### v3.5 — Live Preview / Burnt-in Output Fidelity (Phase 1 — visual)
- **Background**：v3.4 之前 dashboard 同 proofread 兩個 page 嘅 subtitle overlay 各自用 `<div>` + 8-direction `text-shadow` 嚟模擬描邊，同 libass 真正用 FreeType `FT_Stroker` 燒入嘅輪廓有明顯落差（diagonal 唔均勻、邊緣較糊、色塊隨字大細浮動）。另外 [frontend/js/font-preview.js](frontend/js/font-preview.js) 雖然已寫成 SVG `paint-order` 方法但兩個 page 都冇 import 佢，等於 dead code。Agent teams 跑完 audit 確認三大 fidelity gap：(1) outline 幾何唔一致；(2) 兩個 page 各自做 `containerWidth/1920` scaling math，同 libass 內部按 `frame_height/PlayResY` scale 嘅口徑唔同；(3) 單獨 page 重複實作，settings panel 做 PATCH 之後要靠 Socket.IO 嚟 cross-tab 同步。
- **Phase 1 範圍**：純前端視覺改動，唔涉及 font asset bundling 或 backend renderer 變更。Phase 2（serve same TTF via `@font-face` + FFmpeg `fontsdir=` 對齊）留待之後做。
- **`font-preview.js` 完整重寫**（[frontend/js/font-preview.js](frontend/js/font-preview.js)）：
  - SVG `viewBox="0 0 1920 1080"`（hardcoded match `backend/renderer.py` 嘅 PlayResX/Y）→ overlay 入面每個座標單位 = 1 ASS pixel，`fontConfig.size` / `outline_width` / `margin_bottom` 直接 pass-through 唔需要 JS scaling。
  - `paint-order="stroke fill"` + `stroke-linejoin="round"` + `stroke-linecap="round"` — 重現 libass `FT_Stroker` 嘅 outside-glyph 輪廓幾何。
  - SVG stroke 係 path-centered，所以 `stroke-width = outline_width * 2`（fill 後畫蓋住 inner half，剩 outline_width pixel 喺外面）。
  - `text-rendering: geometricPrecision` + `-webkit-font-smoothing: antialiased` + `-moz-osx-font-smoothing: grayscale` — 將 browser LCD subpixel AA 攤平做 grayscale，更貼近 libass FreeType grayscale bitmap output。
  - Multi-line：split on `\n` 同 literal `\N`（renderer 寫入 ASS 時將 `\n` → `\\N`，preview 兩種都認），用 `<tspan x= y=>` 將底線 anchor 喺 `PlayResY - margin_bottom`、上面 stack 行高 `size * 1.2`。
  - 單一 fetch + Socket.IO `profile_updated` listener — 任何 page 嘅 settings PATCH 即時 broadcast 到所有開緊嘅 tab。
- **Dashboard overlay 重寫**（[frontend/index.html](frontend/index.html)）：
  - HTML `<div class="subtitle-overlay-text">` → `<svg id="subtitleSvg"><text id="subtitleSvgText"></text></svg>`，置於 `.video-area` 內，CSS `position: absolute; inset: 0; pointer-events: none`。
  - 刪走 `applySubtitleStyle()` 入面所有 text-shadow 8-direction 邏輯 + scaling math + ResizeObserver，改為 thin wrapper `FontPreview.applyFontConfig(fontConfig)`。`updateSubtitleOverlay()` 改用 `FontPreview.updateText(text)`。
  - 加入 `<script src="js/font-preview.js"></script>` + `FontPreview.init(socket)`（重用已有 socket 實例）。
- **Proofread overlay 重寫**（[frontend/proofread.html](frontend/proofread.html)）：
  - 同 dashboard 對等改動：HTML SVG element、CSS reset、`applySubtitleStyle()` 變 thin wrapper、segment-switch text 寫入由 `sub.textContent = ...` 改成 `FontPreview.updateText(...)`。
  - 加入 socket.io CDN script（proofread page 之前無 socket 連線）+ `font-preview.js` import + `FontPreview.init(null)`（FontPreview 內部會自己起 socket 接 `profile_updated`）。
  - 詞彙表面板 / 字幕設定 panel 嘅 PATCH 流程不變，PATCH 完照舊 call `applySubtitleStyle()` → 經 FontPreview 立即更新 SVG。
- **Backend 不變**：renderer.py / app.py / 任何 API 完全冇動。412 backend tests 全部維持通過（除 v3.3 已存在嘅 macOS tmpdir colon-escape test）。
- **點解仲未完美**：Phase 1 仍然有兩個已知差異 — (a) 字體本身：browser font fallback chain（系統字）vs libass fontconfig 揀字，可能解到唔同 glyph 出嚟；(b) compression artifact：libass output 經 H.264/MPEG-2 4:2:0 chroma subsampling 之後 colored outline 略微變糊，preview 唔會。兩個 issue 都需要 Phase 2（bundle Noto Sans TC TTF + FFmpeg `fontsdir=`）先 close 到。

### v3.4 — Structured QA Flags (Phase B — schema migration)
- **Background**：v3.3 之前 `[LONG]` / `[NEEDS REVIEW]` 兩個 QA tag 直接 prepend 入 `zh_text` 字串，會導致：(1) 字幕燒入時 tag 寫入最終視頻；(2) 前端要 regex parse 譯文先可以判斷狀態；(3) 翻譯 retry 時要 strip-then-feed-back 避免 LLM 抄返。Phase A（v3.3 中段）只係前端視覺修補 + renderer 加 strip 防護網。Phase B 將 tag 由 string prefix 改做 schema-level structured field。
- **Backend schema 變更**：`TranslatedSegment` TypedDict 加入 `flags: List[str]` 欄位（已知值：`"long"` / `"review"`）。`zh_text` 永遠 clean — 唔會再有任何 QA prefix。
- **Post-processor 重寫**（[backend/translation/post_processor.py](backend/translation/post_processor.py)）：`_flag_long_segments` 同 `_mark_bad_segments` 唔再 prepend 字串，改為 append 到 `flags` list（dedup via `_add_flag` helper）。`validate_batch` 簡化 — 唔需要 strip prefix 先計長度。
- **Sentence pipeline 重寫**（[backend/translation/sentence_pipeline.py:264-269](backend/translation/sentence_pipeline.py#L264-L269)）：retry 後仍然 bad 嘅 segment 直接 append `"review"` flag，唔再構造新 `TranslatedSegment` 加 prefix。
- **API normalization**（[backend/app.py](backend/app.py) 新 `_normalize_translation_for_api()` helper）：legacy registry 數據（v3.3 之前寫入嘅 `[LONG] xxx` 字串）會喺 API GET / PATCH / approve 響應時自動 parse 出 `flags` 同 clean `zh_text`，向前兼容唔需要 migration script。新數據已經有 `flags` 直接 pass-through。
- **PATCH 行為**：用戶手動編輯一段譯文等於覆檢過，`flags` 自動 reset 為 `[]`（避免覆檢過嘅 segment 仍然 show 警告）。`approve` 唔改譯文 → flags 保留（警告繼續顯示）。
- **Frontend 簡化**（[frontend/proofread.html](frontend/proofread.html)）：直接讀 backend 提供嘅 `flags` array，透過 `qaFlagsFromBackend()` 轉為 `{type, msg}` UI shape。Legacy `parseTranslationFlags()` 保留為 fallback path，covering 仍未經 normalize 嘅舊 cache 數據。
- **Renderer 防護網**（[backend/renderer.py](backend/renderer.py)）：`strip_qa_prefixes()` helper 保留，新 schema 下變成 no-op，但仍然防止任何 legacy 路徑或 manual data import 漏咗 prefix 燒入視頻。
- **Tests**：post_processor 12 個 tests assertions 由 string-prefix 改檢查 `flags` array；新增 6 個 proofreading API tests（normalize helper、stacked prefix parse、PATCH-clears-flags、approve-preserves-flags、legacy registry pass-through）。test_translation.py `test_retry_failure_keeps_missing_flagged` 改為 assert `"review" in flags`。**412 backend tests pass**（除咗 1 個 v3.3 已存在嘅 ass-colon-escape macOS tmpdir test）。

### v3.3 — MP4 Advanced Render Options (Bitrate Mode + Pixel Format + H.264 Profile/Level)
- **MP4 card** 內加深 controls，同 MXF 卡嘅 depth-of-control 對齊。新增 5 個 `render_options` 欄位：`bitrate_mode` (crf/cbr/2pass)、`video_bitrate_mbps`、`pixel_format` (yuv420p/422p/444p)、`profile` (baseline/main/high/high422/high444)、`level` (3.1…5.2/auto)。
- **CRF mode** — 維持現有 behaviour，加入 `-pix_fmt`、`-profile:v`、`-level:v` flags（`level="auto"` 時不 emit flag，由 libx264 自動揀）。
- **CBR mode** — `-b:v = -minrate = -maxrate = <Mbps>M`、`-bufsize = 2× bitrate`（libx264 嚴 CBR 標準 headroom）。
- **2-pass mode** — renderer 內部 split 做兩次 `subprocess.run`：pass 1 `-pass 1 -an -f null <NUL|/dev/null>`、pass 2 `-pass 2 ... <real output>`。**每次 render 用 unique `-passlogfile` prefix**（format `x264_2pass_{pid}_{urandom(4).hex()}`）避免 concurrent 2-pass 渲染撞 stats file。`<prefix>.log` + `.log.mbtree` 喺 finally block 清理，同 `.ass` temp-file cleanup 對稱。
- **Cross-field validation（bidirectional）**：`yuv422p` 必須 pair `high422`、`yuv444p` 必須 pair `high444`（forward direction），同時 `high422` 必須 pair `yuv422p`、`high444` 必須 pair `yuv444p`（reverse direction，避免 `yuv420p + high422` 等語義矛盾組合）。Error message 同時列出 pixel format + profile + 要求值，用戶睇 toast 即知點 fix。
- **Frontend render modal**：`#rmSectionMp4` 加 3-tab bitrate mode row + 獨立 pane × 3；CBR / 2-pass pane 有 preset pills（串流 15M / 廣播 master 40M / 近無損 80M）+ slider 2–100 Mbps step 1；section 尾加 pixel_format / profile / level 三個 dropdown。`currentMp4BitrateMode` state + `selectMp4BitrateMode()` + `bindSliderLabel()` + `setMp4Bitrate*()` helper 全新。
- **Defaults 保持 backward-compatible**：`bitrate_mode="crf"`, `crf=18`, `preset="medium"`, `pixel_format="yuv420p"`, `profile="high"`, `level="auto"`, `audio_bitrate="192k"` — 唔傳 `render_options` 或只傳部分欄位嘅舊 client 行為完全不變。
- **Tests**：21 new（8 renderer cmd-shape + 2pass passlogfile collision guard；10 API validation 包括 cross-field bidirectional；Playwright smoke 涵蓋 CRF/CBR/2pass 三 mode + default modal-open payload + 2pass 冇 leak CBR slider value）— 410 automated tests（+21 since v3.2 baseline 389）

### v3.2 — MXF XDCAM HD 422 Output + Unified Render Modal + Save As Picker
- **新 output format `mxf_xdcam_hd422`**: MPEG-2 4:2:2 long-GOP 喺 MXF 容器，用戶可調 CBR bitrate 10–100 Mbps（預設 50 Mbps，Sony XDCAM HD 422 廣播標準）。FFmpeg 命令：`-c:v mpeg2video -pix_fmt yuv422p -b:v/minrate/maxrate/bufsize -g 15 -bf 2 -f mxf`，`bufsize` 自動 = 72% bitrate。Note：FFmpeg 8.0.1 嘅 `-intra_vlc 1` / `-non_linear_quant 1` 會觸發 encoder-open failure (`Not yet implemented in FFmpeg, patches welcome`)，所以 intentionally 冇加 — 輸出仍屬標準合規 MPEG-2 422 long-GOP MXF，廣播互通可用。
- **`_FORMAT_TO_EXTENSION` map**: MXF variants (xdcam 等) 全部輸出 `.mxf` 檔名而唔係 `foo.mxf_xdcam_hd422`
- **統一 render options modal（[index.html](frontend/index.html)）**: Dashboard 嘅 MP4 / MXF ProRes / XDCAM / ⚙ 按鈕全部打開同一個 modal。3 個 format cards 可切換；MP4 有 CRF slider + preset + audio bitrate；MXF ProRes 有 profile 0–5 + PCM bit depth；**XDCAM 有 bitrate slider 10–100 Mbps step 5**；共用 resolution dropdown（keep original / 720p–4K）。原本舊 proofread.old.html 嘅 render modal 無喺新 UI 出現，依家 dashboard 直接補返。
- **File System Access API 下載**: 新 `downloadWithPicker(renderId, suggestedName)` helper — Chrome/Edge desktop 會彈 native Save As dialog 畀用戶揀 folder + filename，用 `pipeTo(writable)` 直接 stream response body 去 file handle，避免 multi-GB MXF 全部 load 入 memory。Safari / Firefox 自動 fallback 去 `<a download>` + 預設 downloads folder + informational toast 提示。
- **Backend validation**: `_validate_render_options` 新 branch — `video_bitrate_mbps` 驗證 int 10–100 Mbps（拒絕 bool 避免 True/False 當 1/0），`audio_format` 跟 ProRes 共享 16/24/32-bit PCM 選項。
- **Tests**: 14 new — 6 renderer command shape (`mpeg2video` + yuv422p、CBR bitrate flags、long-GOP、audio/resolution plumbing、bufsize scaling)、8 API validation (format acceptance、default bitrate、10/75/100 pass、5/150/non-int reject、audio format、output filename `.mxf`)。Playwright smoke test 驗證 modal 開關 / format 切換 / slider live label / confirmRender 嘅 POST payload shape / showSaveFilePicker availability。
- **389 automated tests**（+14 new since v3.1 baseline 375）

### v3.1 — Translation Quality + OpenRouter Engine
- **OpenRouter 翻譯引擎**: 新增 `OpenRouterTranslationEngine` ([backend/translation/openrouter_engine.py](backend/translation/openrouter_engine.py))，繼承 `OllamaTranslationEngine`，只 override HTTP call 打去 OpenRouter 嘅 OpenAI-compatible `/chat/completions`。Bearer auth，自動重試 429/502/503/504，支援 attribution headers (`HTTP-Referer`、`X-Title`)。Profile config 新欄位：`openrouter_model`（free-form，唔係 enum）、`api_key`、可選 `openrouter_url`。Factory `create_translation_engine({"engine": "openrouter", ...})` 自動路由。
- **9 個 curated OpenRouter models + 自訂模型**: Claude Opus 4.5 / Sonnet 4.5 / Haiku 4.5、GPT-4o / 4o-mini、Gemini 2.5 Pro、DeepSeek V3、Qwen 2.5 72B、Llama 3.3 70B。Schema 用 `suggestions` 而非 `enum`，用戶可自行輸入任何 OpenRouter 支援嘅 model id。
- **OpenRouter settings modal UI**: 前端點擊 MT step gear icon（⚙）或揀 openrouter 引擎時彈 modal。包含：password-masked API key 輸入（show/hide 切換）、model id free-form 輸入、curated suggestions clickable list、localStorage history（`motitle.openrouter.models`，3 個/域，可個別刪除）、取消/儲存按鈕。PATCH profile 後即時 Socket.IO 通知 active profile 更新。
- **Phase 1 — 放寬字幕字數上限 + per-batch glossary filter**: `MAX_SUBTITLE_CHARS` 由 16 → 28 字（貼近 Netflix TC 單行規範），`[LONG]` 警告閾值 16→28、hallucination 閾值 32→40。新增 `_filter_glossary_for_batch()`：只將當前 batch EN 文本出現過嘅 glossary term 注入 prompt，避免每 batch 塞完整 glossary 造成 prompt bloat。
- **Phase 2 — Sentence pipeline 時間閘門**: 新增 `MAX_MERGE_GAP_SEC = 1.5`，`_split_by_time_gaps()` 避免將相隔太遠嘅 ASR segment 合併（原本冇呢個 guard 會令 merge 出現時間錯亂）。`translate_with_sentences` 新增 `progress_callback` + `parallel_batches` 參數。
- **Phase 3 — In-prompt sentence scope**: `_detect_sentence_scopes()` 喺 prompt 入面向 LLM 交代邊幾個 segment 屬於同一句（e.g. `[S1: 1-3]`），鼓勵 LLM 翻譯時保持句意連貫但各 segment 仍輸出獨立中文句，唔再 redistribute。
- **Phase 4+5 — 廣播風格 few-shot prompt + opt-in Pass 2 enrichment**: System prompt 全部改寫成繁體中文，加入 4 個 EN→TC 廣播新聞例子（體育、政治、科技、娛樂）。新增 `ENRICH_SYSTEM_PROMPT` + `_enrich_pass` / `_enrich_batch` / `_parse_enriched_response`，用 `translation_passes: 2` 開啟：第一 pass 輸出字面翻譯、第二 pass 加描述性修飾詞（Reference Netflix TC 字幕風格）。
- **Phase 6 Step 1 — ASR word-level timestamps**: 新增 `Word` TypedDict (`{word, start, end, probability}`)；`whisper_engine.py` / `mlx_whisper_engine.py` 加入 `word_timestamps: bool`（default `false`），true 時 DTW align 每個字；`segment_utils.split_segments()` 正確 partition words to split segments（字數唔 match 時安全 fallback）；`app.py` segment dict 傳 `words` 陣列去前端（原本硬編碼 `[]`）。
- **Phase 6 Step 2 — LLM-anchored alignment**: 新增 `backend/translation/alignment_pipeline.py`。`translate_with_alignment()`：將連續 ASR segments 合併做句、向 LLM 發 prompt 要求喺翻譯中注入 `[N]` 位置 marker，然後用 `parse_markers()` 切返個 output 去原本嘅 segment 數量。Fallback：`time_proportion_fallback()` 用 word-level timestamps 按時間比例切 + `_snap_to_punctuation()` 就近中文標點對齊。Profile 透過 `alignment_mode: "llm-markers"` 開啟。
- **翻譯按鈕 UI 修正**: 前端 file header actions 原本漏咗手動觸發翻譯嘅 button（`reTranslateFile()` 函數已存在但冇 UI 入口）。加入三態按鈕：`▶ 翻譯`（未翻譯 + ASR done）/ `⏳ 翻譯中…`（disabled）/ `🔄 重新翻譯`（已完成，覆蓋舊 output）。
- **Profile translation block 新欄位匯總**:
  - `alignment_mode`: `"llm-markers" | "sentence" | ""`（預設空 = 傳統 batch translate）
  - `translation_passes`: `1 | 2`（2 = 開啟 Pass 2 enrichment）
  - `use_sentence_pipeline`: bool
  - `openrouter_model`, `openrouter_url`, `api_key`（OpenRouter 專用）
- **Profile ASR block 新欄位**: `word_timestamps: bool`（配合 alignment pipeline 用）
- **`VALID_TRANSLATION_ENGINES`**: 新增 `"openrouter"`
- **375 automated tests**（+71 new since v3.0 baseline 304：15 alignment_pipeline、16 openrouter_engine、5 sentence_pipeline time-gap、5 ASR word_timestamps、4 segment_utils word partitioning、其他）

### v2.1 — Language Config, Frontend UI, Bug Fixes
- **Language config system**: Per-language ASR params (max_words_per_segment, max_segment_duration) and translation params (batch_size, temperature) with validation
- **Segment post-processing**: `split_segments()` splits oversized ASR output at sentence boundaries
- **Frontend Language Config panel**: Collapsible panel in dashboard sidebar to view/edit per-language ASR and translation parameters
- **Frontend Glossary panel**: Collapsible panel to manage glossary entries (add/delete/CSV import) directly from dashboard
- **Translation status badges**: File cards show 待翻譯/翻譯中.../翻譯完成 status with manual translate button
- **Re-translate button**: Manually trigger translation for any file (待翻譯 shows "▶ 翻譯", 翻譯完成 shows "🔄 重新翻譯")
- **Bug fixes**: Glossary entries display (API format mismatch), drag-drop upload, validation error toast, CSV import count, translation_status lifecycle
- **Sentence-aware pipeline (experimental, not active)**: merge_to_sentences → translate → redistribute_to_segments with pySBD. Kept in codebase for future iteration.
- **157 automated tests** (+36 new: language config, segment utils, sentence pipeline)

### v2.0 — Broadcast Subtitle Pipeline
- **Complete pipeline rewrite**: English video → ASR → Translation → Proof-reading → Burnt-in subtitle output
- **Profile system**: Configurable ASR + Translation engine combinations with environment-aware defaults
- **Multi-engine ASR**: Unified interface supporting Whisper (full), Qwen3-ASR (stub), FLG-ASR (stub)
- **Translation pipeline**: Ollama + Qwen2.5 for local EN→ZH translation, Mock engine for dev
- **Glossary manager**: EN→ZH term mappings with CRUD, CSV import/export, auto-injection into translation prompts
- **Proof-reading editor**: Standalone page with side-by-side video + segment table, inline editing, per-segment and bulk approval, keyboard shortcuts
- **Subtitle renderer**: ASS generation with configurable font, FFmpeg burn-in, MP4 (H.264) and MXF (ProRes 422 HQ) output
- **Auto-translate**: Transcription completion automatically triggers translation
- **Removed live recording mode**: Camera/screen capture, VAD, chunk transcription, streaming mode all removed — project refocused on file-based broadcast pipeline
- **109 automated tests** across profiles, ASR, translation, glossary, proofreading, and rendering

### v1.0–v1.5 — Original Whisper Subtitle App
- File upload with drag-and-drop, persistent file management
- Whisper ASR with faster-whisper support (4–8× faster)
- Transcription progress bar with ETA
- Inline transcript editing
- SRT/VTT/TXT export
- Subtitle delay, duration, and font size controls
