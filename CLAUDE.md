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
│   ├── user.html               # Account + admin user management + audit (5-item rail)
│   ├── Glossary.html           # Glossary management page
│   ├── Files.html              # Files library page (login-required)
│   ├── login.html              # Login form
│   └── js/
│       ├── font-preview.js     # Shared module: syncs subtitle overlay with active Profile font config
│       ├── queue-panel.js      # Right-side job queue panel (3s /api/queue poll)
│       ├── step-diagram.js     # Kind-agnostic step-diagram renderer
│       └── files-page.js       # Files.html logic
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
| GET | `/api/settings/font` | Global subtitle-font preset (used by render + live preview when no active profile — V6 / output_lang) |
| PUT | `/api/settings/font` | Update the global font preset (settings.json `font`); emits `profile_updated` |
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

> Admin `POST /api/admin/users` (create) and `POST /api/admin/users/<id>/reset-password` now return **400** (not 500) on a weak/empty password — the ValueError from password-strength validation is mapped to a clean 400. Policy (≥8 chars, not a common password) is shown in `user.html`.

### Frontend

**`index.html`** — Main dashboard. File upload, transcription with progress, auto-translation, profile selector, transcript display (auto-switches to Chinese when translations available), subtitle overlay on video playback.

**`proofread.html`** — Standalone proof-reading editor. Side-by-side layout: video player (left) + segment table (right). Inline editing of Chinese translations, per-segment and bulk approval, keyboard shortcuts, format picker (MP4/MXF), render with progress polling and download.

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
3. **docs/PRD.md** — Update feature status markers (📋 → ✅)
4. **Validation-First tracker** — for any ASR/MT change, a `docs/superpowers/specs/YYYY-MM-DD-...-validation-tracker.md` recording empirical results (✅ Validated / ❌ Rejected / ⚠️ Partial)
5. **Design + plan pair** — a matching `docs/superpowers/specs/...-design.md` and `docs/superpowers/plans/...-plan.md`

---

## Current State & Recent Highlights

Full chronological feature/version history → [docs/history.md](docs/history.md).

This section summarises the CURRENT behaviour a developer needs; older entries live in history.md.

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

### Remaining UI to retire (dead code, no entry point)

- `renderPipelineStrip` / `renderPipelineStripV6` / `renderStripLanguageSelector` / `togglePipelineSteps` (pipeline strip)
- `openLangConfigManageModal` + the language-config modal/step-menu
