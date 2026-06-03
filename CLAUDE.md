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
├── frontend/
│   ├── index.html              # Main dashboard — upload, transcribe, translate
│   ├── proofread.html          # Proof-reading editor — review, edit, approve, render
│   └── js/
│       └── font-preview.js      # Shared module: syncs subtitle overlay with active Profile font config
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

### Style-picker Phase 2 — 翻譯風格選擇器（馬會賽馬 / 體育新聞 / 通用）（2026-06-03）
- **問題**：Phase 1 嘅 en→zh MT prompt 係單一通用版,但賽馬片想主動補賽馬詞、非賽馬片唔想被注入賽馬詞（驗證見 FIFA 足球被 racing-framed prompt 注「the boys→騎師」）。
- **方案**：upload pop-up 加「翻譯風格」dropdown（3 style → MT prompt template）。`mt_style ∈ {racing 馬會賽馬, sportsnews 體育新聞, generic 通用}`,**default generic**。3 個 prompt 全部 production qwen3.5 實證（[drift-fix tracker](docs/superpowers/specs/2026-06-02-drift-fix-validation-tracker.md)）。
- **套用範圍**：style template 係 **en→繁中書面語**,只對 **`source=en` 且 `output∈{zh,cmn}`（英文/英→中文書面語 MT）**生效；其餘 pair（ja→zh、yue→en…）+ 非 MT 路徑（refine/passthrough）行 Phase 1 既有 prompt,**不受 style 影響**。
- **架構（純 wiring,prompt 已驗證）**：`config/mt_style_prompts/{racing,sportsnews,generic}.txt`；`crosslang_mt.build_mt_system_prompt(source,out,style)` en→zh/cmn 回 style template、否則 Phase 1；`translate_segments` + `derive_aligned_output` 加 `style`（向後兼容 default generic = Phase 1）。`mt_style` 由 upload form → `_register_file` 存 entry → `_run_output_lang_cross` + `_run_output_lang_second_cross` 讀傳落 derive（boundary always-coerce 無效→generic + read-site `entry.get or generic` + `_load_style_prompt` coerce = triple safety）。
- **前端**：`index.html` upload pop-up `#mtStyle` dropdown（3 option,default 通用）+ confirm 送 `mt_style`。
- **整合驗證 ✅（真 qwen3.5,live :5001）**：FIFA 足球片 `mt_style=generic` → **racing_terms=0**（`the boys→這些男孩`）;`mt_style=racing` → racing_terms=4（`the boys→各位騎師`,style 容許）;兩者 0 漏粵語。Playwright dropdown 3 option + default generic PASS。Backend regression 13 檔 144 pass,Phase 1 + V6/Profile 零 regression。執行：Subagent-Driven（Sonnet T1/T2/T4 + Opus T3/全 review,每 task two-stage review + fix loop）。
- **新**：`crosslang_mt.{STYLE_LABELS,DEFAULT_STYLE,_load_style_prompt}`;`mt_style` form/entry field。spec/plan：[design](docs/superpowers/specs/2026-06-03-style-picker-phase2-design.md) / [plan](docs/superpowers/plans/2026-06-03-style-picker-phase2-plan.md)。
- **範圍外（v2）**：glossary 專名注入;日文/中文內容 style-aware prompt;style 影響 refine 路徑;en→cmn 真普通話詞彙區分（現用 en→繁中 template + OpenCC glyph）。

### Cross-language drift-fix Phase 1 — 單 pass 綁 base 1:1 衍生 + MT register（2026-06-03）
- **問題**：跨語言 output_lang 雙語**顯示**（校對頁/主頁）系統性 drift —— `_run_output_lang_second` `segs2[i]→live[i]` 純 index-merge，第二語言由**獨立轉錄**硬塞入第一語言 grid（兩條分句唔同 → 錯位）；加 `粵→zh` whisper-direct 開頭幻覺「字幕由 Amara.org」；MT prompt 用粵語寫 prime qwen3.5 漏粵語（我係/喺）。O1 嘅 `aligned_bilingual` 雖 1:1 但只用於 export，顯示仍讀 drifted by_lang。
- **修復（單一真源）**：跨語言（family rule，`_is_cross_language`：zh={yue,cmn,zh}/en/ja，任一輸出家族 ≠ 內容 → 跨）改**單 pass 綁 base** —— 內容 ASR **轉一次**做共享 base（中文家族先 `clause_split`），每輸出 `derive_aligned_output` **1:1 衍生**（passthrough/MT/refine，`derive_mode` 已驗證 en/ja→zh raw MT、yue/cmn→zh refine），喺**同一 grid** 砌 `translations`(by_lang) + `aligned_bilingual` + `segments` + `content_asr_segments`。**刪走 index-merge + 第二 job**（`_run_output_lang_cross`）；on-demand 加語言由 cached base 1:1 衍生 append（`_run_output_lang_second_cross`，gate 於 base 存在且 grid 長度相符,否則 fall legacy）。**同家族單語言中文行返舊路 byte-不變;V6/Profile 完全唔郁。**
- **MT register**：`crosslang_mt._MT_SYS` **由粵語寫改書面語寫**（根治洩漏）+ target-conditional blocklist（zh/cmn 套粵語禁字表、yue 保留粵語、en/ja 書面）+ prompt-leak/empty guard（病態輸出 fallback 落 source）。
- **Validation-First（全程）**：drift 根因 + B 架構 + MT 方法 + winner prompt + de-raced 通用 prompt + style-picker 全部 production-model 實證。Tracker：[docs/superpowers/specs/2026-06-02-drift-fix-validation-tracker.md](docs/superpowers/specs/2026-06-02-drift-fix-validation-tracker.md)。spec/plan：[design](docs/superpowers/specs/2026-06-03-crosslang-drift-fix-phase1-design.md) / [plan](docs/superpowers/plans/2026-06-03-crosslang-drift-fix-phase1-plan.md)。
- **整合驗證 ✅（真片,live :5001）**：賽後(yue→[zh,en]) 362 cues、WF(en→[en,zh]) 282 cues —— 兩條 **display by_lang grid == bilingual export aligned grid（零 drift）、paired=True、cantonese_leak=0、amara 幻覺=0**;賽後 #0「今日第五場…」(無 Amara)、WF「我**是**艾倫·艾特肯」(書面語,非 我係)。Backend regression 14 檔隔離 140 pass + V6/Profile/progress 49 pass，零新增。執行：Subagent-Driven（Sonnet T1/T2 + Opus T3/T4/全 review,每 task two-stage review + fix loop）。
- **新函數**：`app.py::_is_cross_language` / `_run_output_lang_cross` / `_run_output_lang_second_cross`;`crosslang_mt` 書面語 prompt。
- **範圍外（Phase 2）**：style-picker UI（馬會賽馬 / 通用,default 通用,對應 MT prompt template,通用 prompt 已驗 `docs/superpowers/specs/2026-06-02-mt-prompt-generic-sportsnews.txt`）。**（v2）**：glossary 專名注入（馬名/騎師名一致）、en/ja 內容單語言 export clause-split（render line-wrap 已遮）。

### Cross-language 輸出路由 — Whisper 直出 + ASR+MT 混合 + 普通話/簡體（2026-06-02）
- **目標**：output_lang 之前全部 Whisper force-language 直出，輸出語言 ≠ 內容語言時崩壞（死 loop、幻覺、中日混合、碎段爆炸、誤譯）。改成按「內容語言 vs 輸出語言」**自動路由**：同方言 Whisper 直出（質量/分句最佳），跨語言/跨方言用「內容 ASR + MT→輸出」。新增 source 粵/普 拆分、output 普通話、繁/簡 toggle。
- **Validation-First（全程）**：全 matrix（3 內容 × 4-6 輸出）+ 普通話 v2 再驗證，量化證據敲定路由表。Whisper-direct cross-language 一致崩壞；ASR+MT（naive 1:1）一致勝出。**關鍵不對稱**：`粵→中文書面語` Whisper-direct(`zh`) 得（5/4/5），但 `普通話→口語廣東話` Whisper force-`yue` 唔轉粵語（仍出普通話）→ 必須 ASR(zh)+MT(zh→yue)。Tracker：[docs/superpowers/specs/2026-06-02-crosslang-routing-validation-tracker.md](docs/superpowers/specs/2026-06-02-crosslang-routing-validation-tracker.md)；spec/plan：[design](docs/superpowers/specs/2026-06-02-crosslang-routing-design.md) / [plan](docs/superpowers/plans/2026-06-02-crosslang-routing-plan.md)。
- **路由規則**：`route_output(source_language, output_lang)` → `whisper` iff 該輸出方言嘅 Whisper 轉錄喺該內容音上得到目標：`yue` 限粵語內容；`zh`/`cmn` 收粵+普；`en`/`ja` 限同語言內容；其餘 → `asr_mt`。Whisper 直出**唔再用 translate task**（時好時壞、爆 loop）—— `→英文` 跨語言一律 ASR+MT。
- **語言模型**：來源 `source_language`（**權威**）∈ {yue 粵語, cmn 普通話, en 英文, ja 日文}；輸出 dropdown {yue 口語廣東話, zh 中文書面語, cmn 普通話, en 英文, ja 日文} + **繁/簡 `script`** toggle（中文輸出，OpenCC s2hk/t2s，**永遠明確** —— Whisper 'zh' native script 不穩定）。3 個正交維度：方言（Whisper lang）× 語體（中文書面語=加 V6 formal refiner、普通話=raw）× 字體（OpenCC）。
- **中文輸出可組合 pipeline**：`base（Whisper 直出 或 ASR+MT）→ [clause_split 若 asr_mt] → [V6 formal refiner 若 zh] → OpenCC 繁/簡`。
- **新模組（純函數 + 注入式）**：`backend/output_lang_router.py`（route_output / whisper_direct_params / content_asr_lang）；`backend/translation/crosslang_mt.py`（generic 參數化 cross-lang MT，per-segment 1:1，注入 llm_call）；`backend/output_lang_postprocess.py`（apply_script / clause_split_all / formal_refine，重用 cn_convert + v6 clause_split + V6 refiner prompt）。
- **Dispatch（架構 A，app.py）**：`_make_ollama_llm_call()`（綁 Ollama qwen3.5:35b）+ `_produce_output_lang(audio, source_language, output_lang, script, cancel_event, content_asr_cache)`（路由 + 內容 ASR 整片只跑一次跨輸出共享 + 後處理鏈）。`_run_output_lang` / `_run_output_lang_second` 改用之，per-output 獨立路由（一條片可 first=Whisper、second=ASR+MT）。`by_lang` + `{lang}_text` mirror data model **不變** → descriptor/資訊 tab/proofread/export/render/overlay 零改 shape。
- **REST**：`POST /api/transcribe` 加 form field `source_language`（∈{yue,cmn,en,ja}，output_lang mode 必）+ `script`（trad/simp，default trad）；驗證失敗 400。file entry 新增 `source_language` / `script` / `content_asr_segments`（cross 共享 cache）。`subtitle_text.OUTPUT_LANG_LABELS` 加 `cmn`=普通話。
- **前端**：上傳 popup 來源 dropdown 改 粵語/普通話/英文/日文（權威）；輸出 dropdown 加普通話；新增中文字體 繁/簡 toggle（`#olScript`）；confirm 送 `source_language`+`script`。
- **整合驗證 ✅**：真片逐路由格端到端（`integ_crosslang.py`）—— 粵→粵(direct)+英(asr_mt)、**普→粵(asr_mt，真粵語「係/嘅」)**+普(direct)、英→中(asr_mt+refiner)簡體（任务/晋级）。全 status=done。Backend regression 16 檔隔離 172 pass、frontend output_lang Playwright 20 pass、零 regression（profile/V6/B1/B2/現有 output_lang 不變）。執行：Subagent-Driven（Sonnet 機械 + Opus judgment/review，每 task two-stage review）。
- **範圍外（v2）**：glossary 專名注入（cross-lang MT 見專名誤譯）、MT sentence-pipeline 上文、中文書面語 ASR(yue)+refiner vs Whisper-zh+refiner fidelity 取捨。

### O1 配對雙語對齊 — shared-base + 1:1 衍生（store-both）（2026-06-02）
- **問題**：並排雙語（一 cue = 上下兩行）之前用 **index-merge**（第二語言按 index 硬塞入第一語言 row，唔睇時間）。第一語言（Whisper 原生分句）同第二語言（MT 後 clause-split）段數唔同 → 錯位 + 截斷。
- **核心原理（已 Validation-First 驗證）**：**內容語言 base ASR 跑一次** → 每個輸出語言 = base 嘅 **1:1 變換**（輸出==內容→passthrough、跨語言→`crosslang_mt`、書面語→`formal_refine`）+ OpenCC，**唔 clause-split**。全部由同一 base 1:1 衍生 → 所有輸出段數 == base、cue i 各語言共用 base[i] 嘅 start/end → 配對**構造上完美對齊、零 drift**。Prototype 證據：WF 全條 134==134、警察 46==46、阿土 114==114，首尾皆對齊（去到 9.5min 最尾兩 cue 仍逐句對應）。Tracker：[docs/superpowers/specs/2026-06-02-bilingual-shared-base-validation-tracker.md](docs/superpowers/specs/2026-06-02-bilingual-shared-base-validation-tracker.md)。
- **決定：Bilingual-only + store-both**：**單語言輸出 `by_lang` 完全不變**（沿用 cross-lang per-output routing + clause-split，所見即所得、零 regression）；**處理時額外產生一個 1:1「對齊版」** 存入新 file-entry field `aligned_bilingual`，雙語匯出/燒入時用（唔使匯出時 re-derive）。
- **資料模型**：新 file-entry field `aligned_bilingual = [{start, end, by_lang:{<lang>:<1:1 text>}}]`（base grid，每 cue 含全部輸出語言 1:1 文字，長度 == base 段數）。`by_lang` / `{lang}_text` mirror / `translations`（單語言 clause-split grid）**不變**。兩結構獨立：單語言讀 `by_lang`、雙語讀 `aligned_bilingual`。
- **新模組（純函數，注入 llm_call）`backend/output_lang_aligned.py`**：`derive_mode(content_lang, output_lang)`→ 'pass'|'mt'|'refine'（family map yue/zh/cmn→zh, en, ja；cross-family→mt、same-family non-Chinese→pass、粵 base→{yue:pass, zh/cmn:refine}、普/zh base→{cmn:pass, yue:mt, 其餘:refine}）；`derive_aligned_output`（1:1，無 clause-split，中文輸出 apply_script）；`build_aligned_bilingual`（砌 base-grid 結構）；`aligned_rows_for_export`（轉 row-like dicts 畀現有 export/render resolver）。重用 `crosslang_mt.translate_segments` + `output_lang_postprocess.{formal_refine,apply_script}`。
- **Dispatch（app.py）**：`_run_output_lang_second` 尾**追加** best-effort build（`try/except` 包，single-language 已 persist 先，永不阻斷 job）—— 有 ≥2 輸出語言時，reuse `content_asr_segments`（無則 transcribe content base）→ `build_aligned_bilingual(...)` → 存 `_file_registry[file_id]["aligned_bilingual"]`。鎖外做慢 ASR/LLM、鎖內讀寫（plain Lock，無 re-entrancy）。
- **匯出/燒入讀 aligned**：`download_subtitle` + `api_render` 嘅 **bilingual mode**（`subtitle_source=bilingual`）—— 若 `aligned_bilingual` 存在且 descriptor ≥2 lang → 由 `aligned_rows_for_export` 砌 row（配對完美）；否則 fallback 現有 `by_lang`/`translations` build（向後兼容、單語言/舊檔不變）。render + export 用同一 `resolve_language_descriptor` + `_role_fields_for` → 燒入同匯出揀同一 first/second 語言。
- **已知特性（v1 接受）**：(1) 雙語 zh 文字可能同單語言 zh 稍異（同家族格雙語用 refiner(yue base)、單語言用 whisper-zh 直出，兩者都驗證過好）；(2) 雙語 cue = base 分句（較粗，靠現有 line-wrap，但配對永遠正確）；(3) 個別 1:1 段帶 fragment-MT 痕跡（無上文，v2 加 neighbour context）。
- **測試**：`test_output_lang_aligned`(6) + `test_aligned_bilingual_build`(1) + `test_bilingual_export_aligned`(1) + `test_bilingual_render_aligned`(1)；regression `test_bilingual_api`(29) + `test_output_lang_api`(22) + `test_subtitle_text`(38) + `test_produce_output_lang`(6) + dispatch 全綠（單語言 by_lang/匯出零 regression）。整合 harness：`backend/scripts/crosslang_prototype/integ_bilingual_aligned.py`（live :5002 雙語 SRT 配對驗證）。
- **spec/plan**：[design](docs/superpowers/specs/2026-06-02-o1-bilingual-alignment-design.md) / [plan](docs/superpowers/plans/2026-06-02-o1-bilingual-alignment-plan.md)。執行：Subagent-Driven（T1 Sonnet 純函數 + T2-T4 Opus app.py 整合 + 每 task two-stage Opus review）。
- **範圍外（v2）**：neighbour-context MT 提質、雙語 cue 專用 line-wrap UI、O4 獨立圖層 render、單語言↔雙語 zh 文字統一。

### 輸出語言 Pipeline — 純 Whisper 雙語輸出（取代 MT，封存 V6）（2026-06-01）
- **目標**：將「原文 / 譯文（MT 翻譯）」概念換成 **「輸出第一語言 / 輸出第二語言」**，純由 **OpenAI Whisper Large v3（mlx-whisper）多 pass** 驅動，**撤除 MT 翻譯 + DUAL ASR v6**（封存不刪）。User 揀片後彈 popup 選輸出語言；主頁實時 + Proofread 全部改用 first/second 輸出語言。
- **新 `active_kind="output_lang"`**：`_asr_handler` 分流，唔行 `_run_v6` DAG、唔 enqueue MT translate job。每個選定輸出語言**各跑一次** `transcribe_with_segments`（第一語言一次、第二語言 enqueue 多一個 `asr_output` job），各自帶 language/task/s2hk override，行**現有 Profile ASR 路徑（mlx-whisper large-v3）**。復用 B1/B2 `by_lang` + first/second role 資料模型 → descriptor/export/render/overlay 下游零改 shape。
- **輸出→Whisper mapping（由輸出語言決定設定）**：`yue`→`language=yue, task=transcribe, s2hk=True`（口語廣東話）；`zh`→`language=zh, task=transcribe, s2hk=True`（中文書面語）；`ja`→`language=ja, task=transcribe`（日文 marginal）；`en`→`task=translate`（Whisper translate 永遠→英文）。`condition_on_previous_text=False` 修 hallucination loop。源語言 dropdown 純 metadata。
- **Backend（T1-T7）**：`transcribe_with_segments` 加 `lang_override`/`task_override`/`s2hk_override`/`asr_profile_override`（default None → profile-mode 逐 byte 不變；3 個 `task='transcribe'` site 收窄至 2 個 in-function + 第 3 個係 dead streaming code 不動）；mlx engine 由 config 讀 `task`（`asr/mlx_whisper_engine.py`）。新 `backend/output_lang_persist.py::build_output_translations`（純函數，by_lang + authoritative `{lang}_text` mirror，防 B2 `9e3ef67` shadow bug）。`_whisper_params_for_lang` + `_run_output_lang` + `_run_output_lang_second` + `_asr_handler`（`asr_output` job → 第二 pass；`output_lang` kind → 第一 pass）+ `_mt_handler` output_lang short-circuit（`app.py`）。jobqueue 新 `asr_output` job type + nullable `output_language` column（idempotent ALTER + **drop stale `type` CHECK 嘅 table-rebuild migration** —— live `data/app.db` 舊 CHECK 唔含 asr_output，SQLite 改唔到 CHECK，所以 PRAGMA-rebuild 保留全部 column/row 重建，retry 兩路 inherit output_language）。`resolve_language_descriptor` + `_role_fields_for` output_lang 分支（label map yue=口語廣東話/zh=中文書面語/en=英文/ja=日文）。`/api/transcribe` 收 `output_languages` form（JSON，∈{yue,zh,en,ja}，1-2 個）；`/api/files/<id>/translate-second` output_lang → enqueue `asr_output`（非 MT）；approve/unapprove output_lang mirror status 落**全部** by_lang key；PATCH role=first→outs[0]_text、role=second→outs[1]_text。`SUPPORTED_OUTPUT_LANGS = frozenset(OUTPUT_LANG_LABELS)`。
- **Frontend（T8-T9）**：主頁揀片後彈 **upload popup**（左：影片預示+名+時間+大細；右：影片來源語言 + 目標輸出第一語言（必）+ 目標輸出第二語言（可選含「無」））→ confirm 將 `output_languages` JSON 加落 `/api/transcribe` FormData。`loadFileSegments`/proofread `loadSegments` 加 output_lang 分支（by_lang→first/second via descriptor）。Proofread **兩欄皆可編輯**（enInput=第一語言→PATCH role=first；zhInput=第二語言→role=second；單語言隱藏第二欄），label 由 descriptor（`${label} · LANG`），per-lang CPS。Cmd+Enter 喺 popup 開時路由去 confirm（唔會 bypass 落 legacy upload）；glossary「套用」喺 output_lang 隱藏。
- **MT/V6 封存（T10）**：代碼**全部保留不刪**，functional bypass 喺 dispatch（T5/T7/T8）。完整封存清單 + re-enable 指引：[docs/superpowers/archived/ARCHIVE_MT_V6_DESIGN.md](docs/superpowers/archived/ARCHIVE_MT_V6_DESIGN.md)（5 節：disabled paths / archived code（44 路徑核實存在）/ old→new mapping / 原 MT 假設 / glossary↔MT + re-enable）。`reTranslateFile` output_lang guard。Pipeline strip 由全域 `activeKind` 驅動（非 per-file），保守保留並文檔化為「remaining UI to retire」。
- **Validation-First + 整合驗證（T0+T11）**：T0 prototype（`diag_whisper_output_langs.py` + `diag_whisper_full_quality.py`）實證 4 語言能力。**T11 real dual-Whisper-pass 整合 PASS**（`scripts/integ_output_lang.py`，真檔 2.4min 粵語）：第一 pass yue+s2hk「今晚我好高興同埋好榮幸」(口語+繁體)、第二 pass en translate 乾淨英文、by_lang+mirror+descriptor(2 lang)+export(first/second) 全正確。Tracker：[docs/superpowers/specs/2026-06-01-whisper-output-langs-validation-tracker.md](docs/superpowers/specs/2026-06-01-whisper-output-langs-validation-tracker.md)。Backend regression：output_lang+shared 子系統 135 pass / 0 fail；render/v6/queue isolation 全綠（唯一 fail = v3.3 已知 macOS tmpdir colon-escape baseline）；零新增 regression。
- **執行方式**：Subagent-Driven Development，Sonnet 4.6（機械 task）+ Opus 4.8（高判斷 task T2/T5/T8 + 全部 spec/quality review）混合分配，每 task two-stage review（spec-compliance → code-quality）。
- **進度 kind 修復（`90b6e2d`）**：`transcribe_with_segments` 加 `progress_kind`/`progress_stage_index`（default profile/0 → byte-identical），`_run_output_lang`/`_run_output_lang_second` 傳 `("output_lang",0/1)`，`report_from_subtitle_segment` 加同名 param → 轉錄期間 step-diagram 正確顯示 output_lang 2-step（之前 hardcode profile → 暫顯 profile 3-step）。
- **已知 minor（非 blocker）**：`/api/files` row 未 echo raw `output_languages`（descriptor `languages` 已有 → frontend 無影響）；雙語並排只係近似 cross-language 對齊（兩個獨立 Whisper pass 各自分句，按 index merge）—— 單語言輸出時間軸完美，並排雙語逐句唔保證對應；find/replace radio label「搜 EN/ZH」未泛化（搜尋功能正常）。
- **REST**：`POST /api/transcribe` 加 `output_languages` form field（JSON array 1-2 個 ∈ {yue,zh,en,ja}；存在 → 強制 active_kind=output_lang）；`POST /api/files/<id>/translate-second` output_lang mode → enqueue `asr_output`（on-demand 加第二語言）。新 job type `asr_output`（ASR 隊列，per-pass Whisper）。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-06-01-output-language-pipeline-design.md) / [plan](docs/superpowers/plans/2026-06-01-output-language-pipeline-plan.md)。Branch `feat/output-language-pipeline`。Commits：`712f1a2`(T1)→`e47b69e`+`4b911e1`(T2)→`be25201`+`06ddeed`+`18454c8`(T3)→`a1eecd4`(T4)→`2a09c8e`+`310f8f2`(T5)→`842c424`(T6)→`6efe7a4`+`4e8a531`(T7)→`e8798bc`+`b0309de`(T8)→`0099b3f`+`aa49146`(T9)→`6b5c357`(T10)。

### 序列 file card 實時化 — live 階段名+% + 字幕串流（2026-06-01）
- **目標**：工作隊列 panel 有實時進度，序列 file card 唔夠實時。User 要 card 顯示 (1) live 階段名+%（似 queue panel），(2) 字幕文字即時流出 —— **V6 主力**改 backend 邊跑邊 emit。
- **Backend（telemetry/emit only，唔改 refiner/ASR/MT 輸出 → 唔涉 Validation-First）**：`LLMRefiner.refine` 本身已 per-segment 回呼 refined text，但 `RefinerStage` 之前掉咗。修：`StageContext` 加 `segment_callback`；`RefinerStage.transform` forward 每段 text；`pipeline_runner._make_segment_callback` emit 新 additive event **`pipeline_segment`** `{file_id, idx, total, text, lang}`；`_run_stage_v5` 加 `segment_emit`；`_run_v6` **只為最後一個 refiner** 開（書面語 chain 串 pass-2 書面語）。現有 `pipeline_progress`/`pipeline_stage_*` contract 不變。
- **根因發現（forensic）**：實地觀察揭示 **`pipeline_progress` socket event 根本到唔到 dashboard**（`file_updated`/`transcription_complete`/`pipeline_segment` 全部到，唯獨 adapter 經 boot-captured `socketio.emit` 發嘅 `pipeline_progress` 唔到）。工作隊列 panel「實時」其實係靠佢自己每 3s poll `/api/queue`（讀 adapter cache）；file card 之前**淨係靠** socket event → 連 Subsystem A 嘅 card diagram 都從來冇真正 live 過（=user 投訴根源）。
- **Frontend（`index.html`）**：card 加 `.card-stage-label` + `.card-live-caption`（只喺 `status==='transcribing' || translation_status==='translating'` 顯示）。**`_applyCardProgress(fid, snap)`** 共用 helper（cache + patch diagram + stage-label，create-if-missing）；由 (a) `pipeline_progress` listener 同 (b) **新 `_pollCardProgress` 每 3s fetch `/api/queue`**（權威 adapter cache）兩條路 call —— poll 係主力（socket 唔可靠），令 card diagram + 階段名+% 真正 live。字幕串流：`pipeline_segment` socket（**到得**）→ `cardSubtitle` + `_updateCardCaption`；Profile ASR 經 `subtitle_segment`（無 file_id → active 檔）。完成（`transcription_complete`/`pipeline_timing`）清 caption。
- **時序 nuance**：文字喺**最後 refiner stage** 先串（VAD→Qwen3→mlx→合併之後）；串流係 refiner 逐段（clause_split 前）—— live preview 用。`subtitle_segment` 無 file_id → Profile 串流只歸 active 檔。
- **已知遺留**：`pipeline_progress` socket 不達 client 係更深層 latent bug（全靠各處 /api/queue poll 遮住），未根治 —— 留待單獨查 adapter boot-captured emit_fn / socketio threading-mode emit。
- **測試**：backend `test_pipeline_segment_emit.py` 5（LLMRefiner 傳 text / StageContext field / RefinerStage forward / _run_stage_v5 segment_emit 開關）+ Playwright `test_card_realtime.spec.js` 6（stage-label render / caption render / `_updateCardStageLabel` 同 `_updateCardCaption` 同 `_applyCardProgress` live 更新 / done 唔顯示）。`test_v6_runner` fake 簽名 +`**kwargs`。零新 regression。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-06-01-sequence-card-realtime-design.md) / [plan](docs/superpowers/plans/2026-06-01-sequence-card-realtime-plan.md)。
- **新 WebSocket event**：`pipeline_segment`（server→client，V6 最後 refiner 逐段 emit refined 文字 → card live caption）。
- **範圍外**：早串 Qwen3 原始 region 文字、clause_split 後精準 cue 串流、多用戶 subtitle_segment file_id、inspector status-card 統一。

### 完成檔 re-run 用當前揀緊嘅 pipeline + 執行掣可按（2026-05-31）
- **問題**：完成咗嘅片想換另一條 pipeline 再跑 —— 頂部 strip「執行」掣（`#runBtn`）灰咗㩒唔到；而且 re-run（`POST /api/files/<id>/transcribe`）用返**上傳時 snapshot 嘅舊 pipeline**，唔跟 strip 新揀嘅。
- **修復（dispatch/UX，唔涉 ASR/MT engine → 唔涉 Validation-First）**：
  - **Backend** `app.py` 新 helper `_resnapshot_active_for_rerun(file_id)` —— re-transcribe enqueue 前，將 file 嘅 `active_kind`/`active_id`/`active_pipeline_snapshot` **重新 snapshot 成當前 global active**（`_current_active_snapshot` + V6 行 `_snapshot_pipeline_at_upload`）。`re_transcribe_file` 喺 reset 前 call 佢。咁 re-run（頂部執行掣 **同** file card「🔄 重新執行」都行同一 route）即用新揀嘅 pipeline。
  - **Frontend** `index.html`：`updateRunButton()` 對 `status==='done'`/`'error'` 嘅選中檔 enable `#runBtn`（tooltip「用當前 Pipeline 重新執行…」）；`startTranscription()` 對完成檔分流去 `rerunPipeline(activeFileId)`（待上傳新檔路徑不變）。
- **驗證**：backend `test_rerun_resnapshot.py` 2（V6→V6 re-snapshot + snapshot 重填、V6→profile clear snapshot）；Playwright `test_rerun_selected_pipeline.spec.js` 3（完成檔 enable / processing 中 disable / 完成檔㩒執行打 re-transcribe）。Live：完成檔 active_id `1443afcb(書面語)`→ 揀 `4696bbaa(口語)` re-run → active_id + on-disk snapshot 即 flip 做口語。零新 regression。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-31-rerun-with-selected-pipeline-design.md) / [plan](docs/superpowers/plans/2026-05-31-rerun-with-selected-pipeline-plan.md)。
- **範圍外**：per-file pipeline override（脫離 global active）、mid-process re-run、queue panel 內 re-run 掣。

### V6 粵語書面語 pipeline — two-pass chained refiner（2026-05-31）
- **目標**：新增獨立可揀 V6 pipeline「[v6] 賽馬廣播 (書面語)」輸出**現代正式繁體書面語**，取代口語化粵語輸出；**唔影響**現有口語 pipeline。User 拍板 dial：阿拉伯數字、現代正式書面語（禁過度文言/公文腔、保成語）、接受 clause_split 自動切。
- **架構（config-only，零 Python 改動）**：`pipeline_runner._run_v6` 嘅 `refinements[zh]` loop 已支援鏈式 → 新 pipeline `refinements.zh = [口語 refiner f7f72bd9, 書面語 register refiner 9dbe1aa3]`。Pass 2 收 pass 1 已清理嘅粵語，淨係 flip register。`pipeline_runner.py:588` loop 逐個執行、`_persist_by_lang` 寫 `by_lang[zh]`、clause_split 收尾。
- **新檔**：prompt template `config/prompt_templates_v5/refiner/zh_written_register_v6.json`（嘅→的/係→是/咗→了…、保阿拉伯數字、byte 保專名、禁文言虛詞 惟/縱/乃 + 公文腔、保成語、0.8–1.3× 長度、輸出 `{action:keep,text}`）+ refiner profile `9dbe1aa3`（`user_id:null`，reuse LLM `9402593c` qwen3.5-35b）+ pipeline `1443afcb`（clone 自口語 `4696bbaa`，`user_id:null`）。移植自 feat branch `ac96d75`/`43d614d`/`42bc3d1`（`user_id` 627→null、鬆 test assertion）。
- **Validation-First（全程）**：prototype（120 真實口語段，真 Ollama qwen3.5-35b）殘餘 marker 16.63→0.13/100、專名 100%、no-op 0.8%。**整合 re-run（真片 賽後兩點晚 283MB 端到端、560s、337 段）**：source 口語 13.32 → output 書面語 **0.07 markers/100**、over-cap **1.5%**（低過口語 1.8% baseline）、empty 0、阿拉伯數字保留（`135`→「負重 135 磅」）、`stage_outputs` 6 key 證實雙 refiner 執行；口語 pipeline byte-identical（git collateral + regression test）。Tracker：[docs/superpowers/specs/2026-05-31-v6-written-register-validation-tracker.md](docs/superpowers/specs/2026-05-31-v6-written-register-validation-tracker.md)。
- **測試**：`backend/tests/test_v6_written_register.py` 4（template/refiner/pipeline-chain + 口語 regression guard）。Spec/Plan：[spec](docs/superpowers/specs/2026-05-31-v6-written-register-design.md) / [plan](docs/superpowers/plans/2026-05-31-v6-written-register-plan.md)。
- **範圍外**：單-pass、EN pipeline、>2 refiner、register flag、per-file 口語↔書面語 toggle。

### 工作隊列 panel 顯示修復 — 狀態直行斷字 + 跨 job stale stage（2026-05-31）
- **問題**（Playwright 主頁實地觀察）：右側「工作隊列」panel 只 ~278px 闊，每個 job row 喺單一 flex line 塞 7 欄（#位置 / 類型 / 檔名 / step-diagram / 擁有者 / 狀態 / ×）。空間不足 → **(Bug 1)** 狀態文字「進行中」冇 `white-space:nowrap`/`flex-shrink:0`，被逐隻字壓成直行「進／行／中」，擁有者 `admin_p3` 擠成 `a…`、檔名幾乎睇唔到（任何進行中 job 都中）；**(Bug 2)** re-transcribe 一個之前譯完嘅檔，row 一開頭顯示「轉錄 ✓ 完成 → 翻譯 ● 進行中」（上一個 translate job 嘅殘留 stage），其實 ASR 啱啱開始。
- **Root cause**：
  - Bug 1 — 純 layout，row 欄太多 + 狀態/擁有者 span 缺 nowrap/shrink 控制。
  - Bug 2 — **後端** `progress_adapter`（per `file_id` cache）同**前端** `queue-panel.js::_progressCache`（module-level Map）都**冇喺新 job 開始時失效**。Raw `/api/queue` 證實：新 `type=asr` job t+0 回 `stage_label='翻譯' stage_index=1 pct=100`（上個 job 嘅 terminal snapshot），持續 4+ 秒（成個 audio-extraction 階段）。前端 `renderQueueRows` 仲**優先用 in-memory cache 多過 `/api/queue` 權威值**。屬 display/telemetry（非 ASR/MT engine → 唔涉 Validation-First）。
- **修復**：
  - **後端**（`app.py`）：新 helper `_reset_progress_for_job(file_id, job_id, pipeline_kind, stage_index)` → `get_adapter().clear()` + seed 該 job 第一個 stage（pct=0, active）。喺 `_asr_handler`（stage 0：profile 轉錄 / V6 VAD）、`_mt_handler` profile path（stage 1 翻譯）、`_translate_second_handler`（stage 1）三個 job 入口 call。broad guard，progress 報告永不阻斷 job。
  - **前端**（`queue-panel.js`）：(a) row 改 **2-line layout** —— line 1 身份（位置/類型/檔名/擁有者/×），line 2 step-diagram + `nowrap` 狀態，各有足夠空間（含 V6 5-stage diagram）。(b) seed loop 改 **server-authoritative**：stage / pipeline_kind 變（新 job）即 overwrite stale cache；同 stage 內保留較高 pct（poll 唔會將 live socket 進度拉返轉頭，亦兼容無 socket）。(c) 順手修 legacy（無 step-diagram，如 render job）path 嘅 stage-label 唔再 fallback 去狀態文字（之前 render queued row 出「排隊 … 排隊」重複）。
- **驗證**：Playwright 主頁實地 reproduce（login → enqueue job → 逐秒截 #queuePanel）確認兩 bug；修後 raw `/api/queue` t+0 = `轉錄/stage 0/pct 0`（非 翻譯/100）；matrix 截圖（V6 5-stage + profile + queued render 三 row 疊）全部狀態單行、擁有者完整、diagram 唔 clip、零 console error。Tests：新 `test_queue_panel_display.spec.js` 4（@1512 + @mobile 390 狀態唔 wrap / server stage 蓋 stale cache / 同 stage pct 唔倒退）+ 新 `test_queue_progress_reset.py` 4（helper clear+seed 語意）；regression：既有 queue Playwright 10 + progress backend 17 全 PASS，零新增。
- **範圍**：純 `app.py`（adapter reset 接駁）+ `queue-panel.js`（layout + cache）+ tests；無 API schema / engine / 其他頁改動。

### EN→Cantonese（dev-default）改用 sentence-pipeline + 清 dead openrouter_model（2026-05-31）
- **問題**：`dev-default`（EN→Cantonese 書面語）profile 譯 FIFA 訪談片（file `f422c01566ca`）整體質量好，但好多相鄰句子**意思重複** —— batched translate 將相鄰 EN 碎段一齊餵 LLM，LLM 逐段各自補完整句，相鄰 cue 重複介紹同一資訊（例：兩 cue 都重複「賽事/球員」context）。
- **Root cause**：`dev-default` 用 default batched path（`use_sentence_pipeline=false`、`alignment_mode=""` → `_select_translation_strategy` 回 `"batched"`）。Batched 對英文碎段冇句界限概念 → 每段補成完整句 → 鄰段意思重疊 + padding。另 `openrouter_model:"anthropic/claude-sonnet-4.5"` 係 **dead config**（`create_translation_engine` 睇 `engine` field，`engine="qwen3.5-35b-a3b"` 行 Ollama，呢欄被忽略，仲令 UI 誤示 OpenRouter）。
- **修復（config-only）**：`dev-default.json` translation block set `use_sentence_pipeline: true`（→ `_select_translation_strategy(am="", usp=true, src_en=true)` 回 `"sentence"`：pySBD 併英文碎段成完整句 → 整句譯一次 → 按標點/比例 `redistribute_to_segments` 返各原 ASR 段，**每 cue 收互補切片而非各自補全句**），移除 dead `openrouter_model`。engine/style/batch_size/temperature/parallel_batches/glossary 不變；無代碼邏輯改動。
- **Validation-First（CLAUDE.md mandate 全程遵守）**：[分析報告](docs/superpowers/incidents/2026-05-31-profile-mt-adjacent-repetition-analysis.md)（root cause + 5 ranked options）→ prototype `backend/scripts/diag_sentence_pipeline.py` 用**真 Ollama qwen3.5-35b**（同 production engine）跑同一檔 → [validation tracker PASS](docs/superpowers/specs/2026-05-31-sentence-pipeline-validation-tracker.md)：鄰段重複 8.6%→0%、padding 19.8%→13.2%、over-cap 0.9%→0%、7 個已知重複對全修。User review evidence 後先 spec→實施。
- **Live 整合驗證**（重啟 backend + activate dev-default + `POST /api/translate` re-run f422c01566ca）：106 段持久化輸出 —— 鄰段重複 **1/105 (1.0%)**（唯一一個係 keyword heuristic false-positive：#18→#20 本身係**一句英文跨 3 cue**，「賽事」自然重現兩次，讀落連續無重複，**0 真重複**）、padding **8.5%**、over-cap **0%**、empty 1.9%（邊界 case）、首 20 段 timing **0 anomaly**（`redistribute` 保留原 ASR 段 start/end → 結構上無 off-by-one）。
- **範圍**：只 `dev-default`（現 EN→Cantonese 1 條 + 將來同類）；`prod-default` / `b877d8b5`(zh→zh) / `696ed1a3` 不變。`dev-default.json` 係 **gitignored**（api-key 安全，`.gitignore` L56）→ config flip 只落本機；commit 出 spec + CI-safe regression test（`test_dev_default_sentence_pipeline.py`，本機檔在時 4 pass、fresh checkout skip）。
- **Spec/Plan**：[spec+plan](docs/superpowers/specs/2026-05-31-enable-sentence-pipeline-dev-default.md)。

### User 頁 — 帳戶 + 自助改密碼 + admin 用戶管理 + 審計（Task B）（2026-05-31）
- **目標**：將現有 admin/user 後端（`/api/admin/*` + `/api/me`）做返一個好睇嘅 User 頁（取代 Task A placeholder），加自助改密碼，吸納 admin.html。
- **新 backend endpoint**：`POST /api/me/password`（`auth/routes.py`，login_required + `@limiter.limit("10 per minute")`）—— body `{old_password,new_password}`：`verify_credentials` 驗舊密碼（錯→403 + audit `password_change_failed`）、`validate_password_strength` 驗強度（弱→400）、`update_password` + audit `password_changed`。**唯一新增 endpoint**，其餘全用現有 admin-only endpoints。屬 auth/security（非 ASR/MT → 唔涉 Validation-First）。
- **`frontend/user.html`**：app shell（5-item rail，User active）+ 3 角色分區 —— `#accountSection`（恆顯：username + 角色 badge，由 `/api/me`；改密碼 form）、`#userMgmtSection`（admin only：list/create/delete/reset-pw/toggle-admin，重用 `/api/admin/users`）、`#auditSection`（admin only：`/api/admin/audit`）。`#userMgmtSection`/`#auditSection` 由 `is_admin` gate（非 admin 隱藏且唔 call admin endpoint）。
- **`frontend/js/user.js`**（新）：`loadMe()` boot + 改密碼 submit + 重用（自 admin.js 搬入）嘅 loadUsers/deleteUser/resetPassword/toggleAdmin/loadAudit + create-form。DOM id 同舊 admin 一致（`adminUserList`/`adminAuditList`/`adminUserCreateForm`）。
- **admin.html 吸納**：`backend/app.py::serve_admin_page` 由 serve 改 `redirect("/user.html")`（保留 anonymous→login / 非-admin→403 guard）；刪 `frontend/admin.html` + `frontend/js/admin.js`；`index.html` 嘅 `#adminLink` + `#mobileDrawerAdminLink` href 改 `/user.html`。Profiles/Glossaries 唔搬（有自己頁面）。
- **測試**：`test_change_password.py` 4（成功改+真生效 / 舊錯 403 / 弱 400 / 缺欄 400）；Playwright `test_user_page.spec.js` 3（admin 見 3 區 + 用戶列表 / 改密碼舊錯顯示 error / `/admin.html`→`/user.html` redirect）。整合：4 backend + 10 Playwright（含 unified_sidebar 7，`/admin.html` 經 redirect 落 user.html 照過）全 PASS。
- **範圍外**：email/頭像/其他 user profile 欄位（users 表只 username/is_admin/created_at）；Profiles/Glossaries 管理；語言配置搬入（仍喺 topbar 齒輪）。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-31-user-page-design.md) / [plan](docs/superpowers/plans/2026-05-31-user-page-plan.md)。Commits：`f3c59e3`（T1 endpoint）→ `9c9fa33`（T2 user.html+user.js）→ `7d99bc6`（T3 redirect+移除 admin）。

### 統一左側欄 — 5-item rail（Task A）（2026-05-31）
- **目標**：所有頁最左 rail 統一為剛好 5 個 nav item：**主頁 / 檔案 / 校對 / 術語表 / User**。之前各頁 rail 唔一致（index 仲有 Pipeline + 語言 + 服務狀態齒輪）。
- **移除項去向（功能不失）**：Pipeline → 靠頂部 pipeline strip（已存在）；語言（語言配置）→ rail 移除、trigger 搬去 index topbar 新 `#settingsGearBtn`「⚙ 設定」（onclick `openLangConfigManageModal()`，開語言配置管理 modal）；服務狀態/restart → rail 移除（`restartService()` function 保留）。
- **覆蓋頁**：`index.html`（rail 修剪 + User link + topbar 設定齒輪；主頁/檔案/校對 in-page data-route 不變）、`proofread.html` / `Glossary.html`（rail 換 canonical 5-item cross-page-link，當前頁 active）、`admin.html`（本來無 rail/shell → 加最小 `.admin-shell` flex + `.b-rail`，現有 tabs/panels 原封 wrap 入 `.admin-content`，id/JS 全保留）。新 `frontend/user.html` placeholder（5-item rail，User active；`GET /user.html` login-required 靜態 route，跟 serve_glossary_page pattern）。
- **架構**：vanilla HTML 無 build step → 每頁 inline 同一套 rail markup（canonical SVG/順序/`.tt` label 一致），只差 active class + in-page-route(index) vs cross-page-link(其他頁)。後端只加一條靜態 route，零 API/邏輯改動。`login.html` 無 rail 不變。
- **測試**：`frontend/tests/test_unified_sidebar.spec.js` 7 pass —— 5 頁各斷言 rail 剛好 5 item（主頁/檔案/校對/術語表/User 順序）+ active + 無 Pipeline/語言/服務狀態；`user.html` 200；index topbar 設定齒輪開語言配置。
- **範圍外（Task B）**：User 頁實際內容（admin/user 管理 frontend，後端 `/api/admin/*` + auth 已有）+ 個人設定 + 語言配置正式搬入 User 設定區 + admin.html 吸納入 User 頁。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-31-unified-sidebar-design.md) / [plan](docs/superpowers/plans/2026-05-31-unified-sidebar-plan.md)。Commits：`a93d5ee`（T1 user.html+route+spec）→ `01b5048`（T2 index+gear）→ `f6e71cf`（T3 proofread）→ `f1d0349`（T4 glossary）→ `f834161`（T5 admin）。

### V6 mlx 時間軸幻覺修復 — D3 cond=False + D2 VAD fallback（2026-05-31）
- **問題**：V6 粵語片（reproducer `de603727d3f8`「賽後兩點晚」）頭段字幕嚴重錯位 —— 字幕 #0 顯示 0.0s 但實際語音 7.88s 先講（早 7.88s）。Root cause（由持久化 `stage_outputs` 證實）：mlx-whisper（V6 timing 權威）hallucinate「字幕由 Amara.org 社群提供」+ 每 30s 一格 block；因 `condition_on_previous_text=True`（asr_primary profile 從未收過 v3.8 cascade fix）令幻覺 **cascade** 落頭 150s（5 × 30s 塊）。time-anchored merge 盲信呢啲塊，clause_split 再按字數比例切 → 字幕時間係「30s 塊內比例」嘅假時間。Qwen3 本身有準逐字時間（「今」@7.88s）但被丟棄。Incident: [docs/superpowers/incidents/2026-05-31-v6-cantonese-mlx-timing-misalignment.md](docs/superpowers/incidents/2026-05-31-v6-cantonese-mlx-timing-misalignment.md)。
- **修復（只 V6；Profile/V5 零影響）**：
  - **D3** — `backend/pipeline_runner.py` 新 module-level helper `_v6_timing_profile(profile)` 回傳 `{**profile, "condition_on_previous_text": False}`；`_run_v6` 用佢包 `primary_profile` 先建 `ASRPrimaryStage`。V6 mlx 係純 timing track，carryover 永遠唔需要 → 打斷 caption cascade。
  - **D2** — `backend/stages/v6/time_anchored_merge_stage.py`：`transform` 多讀 `context.pipeline_overrides["__vad_regions"]`；`_time_anchored_merge` 對 coarse mlx 段（dur ≥ `mlx_coarse_fallback_sec`，預設 `_COARSE_SEC_DEFAULT=20.0s`）改行新 `_vad_fallback()` —— 用覆蓋該段嘅 VAD 區間做 slots、Qwen3 字按 timestamp bucket（gap 字歸最近 slot；無 VAD 覆蓋退回 Qwen3 首尾字 span）。健康段（<20s）路徑**逐 byte 不變**。`_run_v6` merge_overrides 加 `__vad_regions`（stage 0 VAD 輸出）+ 傳 `mlx_coarse_fallback_sec`（pipeline JSON 可 override）。
- **Validation-First（全程遵守）**：先 prototype 量化驗證（`backend/scripts/v6_prototype/diag_mlx_timing.py`：cond=True 4 段全 30s 幻覺 → cond=False 40 段 median 2.24s；`diag_mlx_detect_fallback.py`：detector flag 5 塊/150s、healthy 零誤報、Qwen3「今」@7.88s）→ tracker → user confirm → brainstorm → spec → plan → 落代碼。整合 re-run（862s production V6）：**字幕 #0 由 0.0→7.80s、mlx coarse 塊 5→1、median 30s→2.14s、頭段改 VAD-aligned 邊界、detector 零誤報**。Tracker（含整合結果）: [docs/superpowers/specs/2026-05-31-v6-mlx-timing-validation-tracker.md](docs/superpowers/specs/2026-05-31-v6-mlx-timing-validation-tracker.md)。
- **測試**：`test_v6_merge_vad_fallback.py` 5（coarse→VAD 重切、healthy 逐 byte 不變、無 VAD→Qwen3-span、VAD 缺失唔 crash、gap 字歸最近）+ `test_v6_timing_profile.py` 2（cond=False override + 不可變）。整合 re-run PASS。Regression：v6/merge/timing/runner/subtitle/bilingual 288 pass，7 pre-existing（5 v6_second_language full-suite isolation + 2 b7 B1-stale），零新增。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-31-v6-mlx-timing-fix-design.md) / [plan](docs/superpowers/plans/2026-05-31-v6-mlx-timing-fix-plan.md)。Commits：`592e3eb`+`b6bb4cf`（T1 D2 merge）→ `2602ac7`（T2 D3）。

### 全專案 Bug 審計 + 22 個修復（2026-05-31）
- **方法**：multi-agent workflow（8 個唯讀 finder 按子系統 fan-out → dedup → 逐個 candidate 對抗式驗證）。30 個 candidate → **25 confirmed / 5 refuted**。完整報告：[docs/superpowers/audits/2026-05-31-project-bug-audit.md](docs/superpowers/audits/2026-05-31-project-bug-audit.md)。User 確認後修 22 個（skip 3 個：#7 ASR 空段過濾、#6 redistribute off-by-one —— 兩個受 Validation-First 管制留待單獨驗證；#10 bilingual_order 命名語意當 cosmetic）。
- **修復（每個 TDD RED→GREEN，Sonnet 實作 + Opus 逐個覆核 diff）**：
  - **V6 健壯性**（`b51a0bf`）：`llm_refiner.py` 拒絕非字串 JSON `text`（之前 `str()` 化 int/list 變垃圾字幕）；`clause_split.py::split_v6_aligned` fallback timing 用 `0.0`（之前 `None` → 算 duration TypeError）；`clause_split_segment` 短句 `copy.deepcopy`（之前共享 nested `flags`/`words`）。
  - **翻譯**（`d61e66e`）：`_filter_glossary_for_batch` 要求 entry 同時有 `source` + `target`（之前缺 `target` → 下游 KeyError）；`_enrich_pass` + `sentence_pipeline` 改 functional 重建（不可變，輸出不變）。
  - **渲染 / profiles**（`f192a6b`）：`seconds_to_ass_time` 改先算 total centiseconds 令進位正確傳遞（之前 `.995` → cc=100 無效 ASS）；`ProfileManager.delete` 清埋 `active_id`。
  - **jobqueue retry cap**（`5de7a08` → `3651c1d` 修正）：retry 嘅 cap 檢查 + insert 必須喺一個 `BEGIN IMMEDIATE` 交易（之前 read-check-insert 分開 → 並發 retry 繞過 poison-pill cap）。**Opus 覆核捉到 A4 第一版用 `MAX(attempt_count) over (file_id,type)` 係 lifetime cap，會錯誤封鎖 re-transcribe + 整爛 `test_queue_retry`** → 改成讀特定 parent job 嘅 `attempt_count` + 原子 bump（chain-scoped，無跨 chain 累積）。
  - **app.py 並發/registry/crash-guard 一組**（`fec45d0`，9 個 bug）：V6 ASR dispatch `active_id` null → 清楚 RuntimeError（非 KeyError）；`_auto_translate` 嘅 status/error 寫入移入 `_registry_lock`；`warning_missing_zh` 數真正 second-role field（V6 `en_text`）而非硬讀 `zh_text`；`translate-second` endpoint 全部驗證讀取入鎖（TOCTOU）+ 已有 pending 時回 409（per-file 序列化）；`_translate_second_handler` transform 失敗時清 `_pending_second_lang`（避免 re-dispatch loop）+ 不可變重建 translation rows；`_mt_handler` 原子 snapshot 決策欄位再喺鎖外 dispatch。
  - **前端**（`7f8fadd`）：`renderStepDiagram` 加 `stageIndex != null` guard（null 唔再誤判全完成）；`translation_progress` `percent===100` set `translation_status='done'`（之前要 reload 先 done）；find-replace 嘅 approved 狀態取自後端 response（非硬編 `true`）；`unapproveSegment` 改 immutable `segs.map`。
- **驗證**：每個修復喺隔離環境 GREEN；後端完整 suite `1123 passed / 23 failed`（23 個全部 pre-existing：14 已記錄 baseline + 2 B1 stale `b7` + 7 full-suite 共用-db 隔離雜訊，全部單獨跑綠 —— 零新增 regression）；前端 `unified_progress` 6/6。
- **已知遺留（非今次範圍）**：2 個 `test_v3_19 b7_render_source_en_for_zh_v6` 係 B1 改 en-on-zh-V6 guard 之後嘅 stale test（測緊已移除嘅 hard-400 行為），留待單獨更新。

### Subsystem A — 統一進度 step-diagram（Profile + V6，序列 + file card）（2026-05-30）
- **目標**：統一兩個 surface（右側序列 panel row + 左側 dashboard file card）+ 兩個 kind（Profile / V6）嘅進度顯示,用一個 kind-agnostic step-diagram（✓ done / ● active-fill / ○ pending）。順手修 V6 stage label live bug。
- **Canonical 模型**：每 kind 一個有序階段清單。Profile = `轉錄→翻譯→校對`;V6 = `VAD 切段→Qwen3 識別→mlx 對齊→時間合併→Refiner 校對`。每步 state 由 `stage_index`+`stage_state`+`pct` 客戶端 derive。
- **Backend**：`progress_adapter.py` —— `PIPELINE_STAGES` per-kind 清單;`report()` + `pipeline_progress` event + `/api/queue` rows 新增 additive field `stages:[{key,label}]` + `stage_index`（+ `/api/queue` 補 `pipeline_kind`）。**修 V6_STAGE_LABELS bug**：刪舊 dict,新 `_v6_stage_index(stage_type)` 把真 stage_type（`vad`/`qwen3_per_region`/`asr_primary`/`time_anchored_merge`/`refiner:<lang>`）map 去正確 index + label（之前 3/5 顯示「Stage N」+「Qwen3 識別」黐錯 stage）。Profile 校對 step（index 2）由 approve/unapprove/approve-all handler emit（approved/total）。`translation_status` V6 由 'completed' normalize 做 'done'（保留 translation_kind）。
- **Frontend（零 kind branching）**：新共用 `frontend/js/step-diagram.js`（`window.renderStepDiagram(stages, stageIndex, stageState, pct)`）。`queue-panel.js`（右側 row）+ dashboard file card（左側）都用佢 render；file card 加 `pipeline_progress` listener + cold-start 由 file.status/active_kind derive → **V6 card 唔再卡 0%**。**保留 B1 語言 dropdown**（只改 card 進度區）。
- **Invariant**：frontend render backend 畀嘅 `stages`,零 kind 判斷。forward-compat `pipeline_v99` test 通過（unknown kind 照 render）。Native events / `queue_changed` zero-payload 不變,`pipeline_progress` 只加 field。
- **驗證**：progress_adapter + queue_progress_pct 17 pass;Playwright `test_unified_progress.spec.js` 4 pass + `test_queue_progress.spec.js` forward-compat pass;live screenshot 兩 kind × 兩 surface（Profile 3-step / V6 5-step 正確 label、零 console error）。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-unified-progress-stepdiagram-design.md) / [plan](docs/superpowers/plans/2026-05-30-unified-progress-stepdiagram-plan.md)。
- **OPS 提醒**：stale Xcode-framework python 會喺 `pkill -f "python app.py"`（細楷）後殘留 serve :5001 → 用 `pkill -if app.py` 或 kill PID;pytest 跑完會 reset `admin_p3` 密碼 → `update_password('data/app.db','admin_p3','TestPass1!')` 還原（Playwright spec 預設 `PROBE_PASS=TestPass1!`，務必對齊呢個值，否則 fresh-login spec 會 401 失敗）。
- **Bugfix（2026-05-31，`61c6d2a`）**：完成嘅 V6 file card 喺 cold-start（page reload，`cardProgress` 空）時 step-diagram 全部顯示 ○ 未開始。Root cause —— V6 唔 enqueue 獨立 translate job（refiner inline），所以 `translation_status` 完成時係 `null`（by design），但 file-card cold-start derive `_coldStageIndex` 嘅 V6 分支要求 `status==='done' && translation_status==='done'` 至當完成，永遠唔成立 → fall through `{idx:0,'idle'}`。修正：V6 完成只睇 `status==='done'`（refiner 係最後 stage，status done = 成條 pipeline 完）。`test_unified_progress` 原 fixture 用咗唔可能嘅 `translation_status:'done'` 遮蔽咗 bug → 改用真實 `null` + 新 regression（5 步全 done）。順手統一全部 9 個 Playwright spec 嘅 `PROBE_PASS` 預設做 `TestPass1!`（`3c910ad`，之前 AdminPass1!/TestPass1! 兩派 default 令同一 `admin_p3` user 互相 401）。Live 驗證真實片 `b1e0aa39c473`：5/5 step done。

### Subsystem B1 — per-video 雙語(第一/第二語言)統一模型（2026-05-30）
- **目標**：統一 Profile + V6 嘅字幕語言選擇 —— 每條 video 用「第一/第二語言」role-based 模型,取代硬編碼 EN/ZH。Profile:第一=ASR 原文、第二=MT 譯文(已有 data);V6:第一=refiner 結果、第二可選(結構預留,B2 先產生)。
- **Backend**：`subtitle_text.py` —— `resolve_segment_text(... , first_field=, second_field=)` 支援 `first`/`second`/`bilingual` mode(legacy `en→first`/`zh→second` 完全兼容);新 `resolve_language_descriptor(file_entry, active_cfg)` 回傳 `[{role,lang,label}]`。`app.py` —— `GET /api/files` 每 row 加 `languages` descriptor、新 `GET /api/files/<id>/languages`、`POST /api/render` + `GET .../subtitle.<fmt>` 用 `_role_fields_for(entry)` 計 first/second field 傳入 resolver(取代硬 zh_text 讀法 + 硬 en-on-zh-V6 400 guard 改為「first-role 全空」check)、`PATCH .../translations/<idx>` 接 optional `role`。`renderer.generate_ass` 加 first_field/second_field kwarg(default None 向後兼容)。
- **Frontend**：dashboard file-card 語言 dropdown + proofread `#proofreadSourceMode` 由 `file.languages` descriptor 動態 render(顯示實際語言名,V6 單語言時隱藏第二/雙語);`pickSubtitleText` mirror role-based。
- **範圍 / 兼容**：零強制 storage migration(role→field 對映喺 resolver,舊 en/zh 資料照讀);legacy en/zh/auto/bilingual 行為不變(既有 test 全綠)。**B2(V6 真正產生第二語言 = translator stage)deferred**。
- **驗證**：subtitle_text 31 + bilingual_api 24 + render/subtitle regression 180 pass(1 known v3.3 baseline);Playwright `test_bilingual_selector.spec.js` 2 pass(Profile 第一/第二/雙語、V6 單語言);live export smoke(Profile source=first→英文原文 / second→中文譯文)。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-per-video-bilingual-design.md) / [plan](docs/superpowers/plans/2026-05-30-per-video-bilingual-plan.md);[research](docs/superpowers/research/2026-05-30-unified-progress-and-bilingual-research.md)。**Subsystem A(統一進度 step-diagram)next**（user 決定 B 先做完 confirm 再做 A）。

### Subsystem B2 — V6 on-demand 第二語言（translator）（2026-05-30）
- **目標**：B1 已能「顯示/選擇/render」第二 by_lang track，但冇嘢產生佢。B2 補上產生機制 —— 用戶逐條 V6 片 on-demand 加一個第二語言（翻譯 refiner 原文 → target lang），寫入 `by_lang[target]` + `{target}_text` mirror，B1 即自動 surface（descriptor / selector / export / render）。單語言 V6 維持不變（唔強制第二語言）。
- **Backend reuse（零新 MT path）**：新 `POST /api/files/<id>/translate-second {lang}`（`@require_file_owner`）—— 驗證 `active_kind=='pipeline_v6'`、有 first-track `source_lang`、`lang != source`、方向 template `config/prompt_templates_v5/translator/{src}_to_{lang}_default.json` 存在（否則 400「未支援嘅語言方向」），存 `_pending_second_lang` 入 registry 再 enqueue 一個 `translate` job，回 202。`_mt_handler` 喺 V6 short-circuit **之前** check `_pending_second_lang` → 路由去新 `_translate_second_handler`。Handler 讀 refined first-track segments（`by_lang[src].text` / `{src}_text`）→ 砌 in-memory `translator_profile {source_lang, target_lang, llm_profile_id, prompt_template_id}` + qwen3.5 `llm_profile`（`9402593c-…`，同 refiner 同源）→ `TranslatorStage.transform(refined, ctx)`（mirror `_run_v5` 嘅 invoke pattern）→ 逐 row 寫 `by_lang[target].{text,status:pending,flags}` + `{target}_text` mirror，清 `_pending_second_lang`。進度經 A 嘅 `report_from_translation_progress` shim（序列/card step-diagram 顯示「翻譯」0–100%）。**MVP 方向 zh↔en**（有 template），加新 template 即 additive 擴方向。
- **Frontend**：pipeline strip 變 file-context —— 揀中一條片（`activeFileId`）時，strip 喺 preset chip 後加 `renderStripLanguageSelector()`（第一/第二語言 chip + V6 單語言時「+ 加第二語言」按鈕 → target 清單 zh→en / en→zh → `POST /translate-second` → 「翻譯中…」→ 完成後 `/api/files` refresh 自動補第二 chip）。兩個 strip branch（Profile + V6）共用，無選片時 strip 還原 pipeline 顯示。`selectFile→renderAll→renderPipelineStrip` 已自動刷新。
- **整合驗證（真 qwen3.5 smoke）**：對 zh-source V6 片 `2d4a09ac51d9`（210 段粵語 refiner 結果）`POST /translate-second {lang:en}` → ~分鐘完成、210/210 row 有 `by_lang.en` + `en_text` mirror（fluent 英譯，例「You're flipping through your most anticipated weekly game box again.」）、`/languages` 由 1→2 langs、export `source=second`→英文 / `source=first`→refined 粵語 / `bilingual`→雙語。
- **整合期發現 + 修（B1 export 漏洞）**：export row-builder（`download_subtitle`）對 V6 file 將 `en_text` 預填做 raw `source_text`（源語言粵語），而 role-field pass-through 用 `if _fld not in row` skip-if-present guard → B2 真正寫入嘅 `en_text` 被 raw 粵語 shadow，`source=second`/`bilingual` 錯返粵語。修正：兩個 export loop 將指定 first/second role field **authoritative** 由 translation row 取（commit `9e3ef67`）。Render path 唔受影響（直接讀 translation row）。2 個 regression test（`source_text` 故意 distinct 防 leak）。
- **Bilingual order 命名 nuance（已知，非 bug）**：legacy `en_top`/`zh_top` 對映 first/second **role**；V6 role 語言對調（first=源/zh、second=譯/en），所以預設 `en_top` 實際係「源語言喺上、譯文喺下」（正合粵語廣播需求），顯式傳 `zh_top` 先會倒轉。唔擴 resolver signature。
- **Tests**：`test_v6_second_language.py` 5（endpoint 202 / handler 寫 by_lang / same-lang 400 / 無 template 400 / Profile 400）+ `test_bilingual_api.py` 2 export regression + Playwright `test_v6_second_language.spec.js` 4（strip selector / + 加第二語言 menu / Profile 雙 chip 無加鈕 / POST 觸發 spinner）。`pytest test_bilingual_api+subtitle_text+v6_second_language+progress_adapter+render*` = 237 pass / 1 known v3.3 baseline。
- **範圍外**：無 template 方向（zh→ja/ko 等，additive）、pipeline-level auto 第二語言、>2 語言、Profile 加第三語言。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-v6-second-language-design.md) / [plan](docs/superpowers/plans/2026-05-30-v6-second-language-plan.md)。Commits：`58f61ef`（endpoint+job）→ `df772d6`（strip selector）→ `9e3ef67`（export second fix）。
- **新 REST endpoint**：`POST /api/files/<id>/translate-second {lang}` — V6 only，on-demand 加第二語言（202 + job_id + target_lang；非 V6 / 同語言 / 無 template → 400）。

### 主介面 Pipeline Strip 顯示修復 — 步驟 popover（2026-05-30）
- **問題**：MacBook 14"（1512px）topbar pipeline strip 喺 Profile + V6 兩個 mode 嘅 steps 被壓縮重疊成 garble（search+health-cluster+userChip+preset dropdown 食晒 topbar 寬度，strip overflowing，steps flex-shrink 到 ~25px 致文字溢出重疊）。
- **修復**：strip 改為永遠 compact（preset 選擇器 + 「步驟 ▾」toggle）；完整 steps 搬入 `.pipeline-steps-popover`（`width:max-content; overflow:visible`，唔受 topbar grid 限制），撳 toggle 彈出。steps 有自然全寬唔再重疊；popover 內 `.step .v` 解除 100px cap 顯示完整值；每個 step 互動（preset 切換 / V6 qwen3·refiner inline panel / Profile ASR·MT hover 選擇）100% 保留。純前端（`index.html` CSS + `renderPipelineStrip`/`renderPipelineStripV6` + `togglePipelineSteps` + outside-click）。
- **測試**：Playwright `test_pipeline_strip_popover.spec.js` 兩個 mode @1512×982（popover 開合、steps 唔重疊、值完整、撳出面收埋）。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-pipeline-strip-popover-design.md) / [plan](docs/superpowers/plans/2026-05-30-pipeline-strip-popover-plan.md)。

### Pass-2 Enrichment 短 fragment guard（2026-05-30）
- **問題**：`translation_passes: 2` 嘅 Pass-2 enrichment 對短 source fragment 過度膨脹兼虛構（粟米片→「呢款食品係由穀物壓製而成…」7-10×）。
- **Root cause**：`ENRICH_SYSTEM_PROMPT` 有無條件硬規則「短於 18 字嘅輸出需重寫更長」，唔知 source 長度 → minimal utterance 被迫虛構描述。隔離驗證（diag_enrich.py passes=1 vs 2）：短句(≤6字) passes=1 ratio 1.0、passes=2 ratio 6.8×。
- **修復**：`ollama_engine.py::_enrich_pass` 加 source-length guard — 只 enrich `len(source) >= enrich_min_src_chars`（預設 10）嘅 segment，短 source 保留精準 Pass-1 輸出。Config `translation.enrich_min_src_chars`（0 = 還原舊行為全 enrich）。
- **範圍**：只 `_enrich_pass` batching。ENRICH prompt 文字 / Pass-1 / single-segment / 其他 path 唔郁。通用改善（任何語言短 fragment 受惠）。
- **Validation-First**：隔離診斷（diag_enrich.py）定位 Pass-2 為 bloat 源；7 unit test（stub LLM）+ integration 對比驗證短句保 Pass-1、中長句仍 enrich。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-enrich-short-fragment-guard-design.md) / [plan](docs/superpowers/plans/2026-05-30-enrich-short-fragment-guard-plan.md)。

### Profile pipeline same-lingual 對齊修復（2026-05-30）
- **問題**：zh→zh profile（`b877d8b5`，alignment_mode=llm-markers）處理粵語廣播片時字幕系統性 off-by-one（譯文遲 1 段出）。
- **Root cause**：`translate_with_alignment` 內 `merge_to_sentences` 用英文 pySBD + 英文 word boundaries（**英文 source 專用**）；用喺中文 source 上辨認唔到中文句號 → over-merge（驗證：104 段 → 7 句、最大跨 41 段）→ LLM marker alignment 必敗 → time-proportion fallback 致 off-by-one。
- **修復**：新純函數 `_select_translation_strategy(alignment_mode, use_sentence_pipeline, source_is_english)`；`_auto_translate` 改用佢分流。merge-based mode（llm-markers / sentence）只喺英文 source 行；非英文 source 行 `engine.translate(batch_size=1)`（v3.8 single-segment 1:1，每段保 start/end → off-by-one 結構上不可能）。
- **範圍**：只 `backend/app.py` 路徑選擇 + helper + tests。Engine / merge_to_sentences / alignment_pipeline / sentence_pipeline 內部、英文 EN→ZH profile（prod-default / dev-default）、V6 全部唔郁。
- **Validation-First**：非破壞性重現確認 off-by-one；merge guard prototype 量度 over-merge（104→7 句）；單元測試 9（routing）+ 1:1 timing harness 驗證。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-profile-samelingual-alignment-fix-design.md) / [plan](docs/superpowers/plans/2026-05-30-profile-samelingual-alignment-fix-plan.md)。

### V6 字幕分句優化 — 後置標點 clause-split（2026-05-30）
- **問題**：V6 Dual-ASR pipeline 喺連續旁白片（無自然停頓）分句過粗 — 一條 subtitle 跨幾個逗號子句（VTDown 24 段中 13 段含未斷標點、median 28 字、最長 57 字/13 秒）；廣播片（有停頓）靠 VAD/mlx 自然分句 ~99% 好。Root cause：V6 segment 邊界由 mlx-whisper 聲學分段決定，全程無標點分句。
- **修復**：新 module `backend/stages/v6/clause_split.py`（純函數）— 喺 refiner 之後、persist 之前，將超 `char_cap`（預設 24）嘅 refined segment 喺中文標點（。！？，、；：）切原子子句、greedy 填行、proportional timing、min-duration guard（<1.0s 嘅 piece merge 返，避免閃 line）。單一超 cap 無標點子句唔切（避免 jieba-類已 reject 陷阱）。
- **核心約束**：`_persist_by_lang` 用 index 對齊 zip canonical_source（source）+ by_lang（refined）且行 start/end 來自 source，所以 `split_v6_aligned` lockstep 擴展兩條 stream。只郁 V6 單 target_lang path；Profile/merge/refiner/VAD 唔郁。Config：pipeline JSON `clause_split` block（`enabled`/`char_cap`/`min_dur`），缺省 `enabled=true`。
- **Validation-First**：診斷 workflow + P1（標點切句演算法，cap=24 賽馬 churn 1/83）+ P2（re-run Qwen3：時間戳逐字但無標點 → reject「逐字時間對齊」approach B，揀 proportional + guard）。整合 re-run VTDown：24→39 段、over-cap 13→3、median 28→18、無 <1s piece。證據：[validation tracker](docs/superpowers/specs/2026-05-30-v6-segmentation-validation-tracker.md)。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-v6-segmentation-clause-split-design.md) / [plan](docs/superpowers/plans/2026-05-30-v6-segmentation-clause-split-plan.md)。

### Proofread 版面修復 — 移除自訂 Prompt 面板（2026-05-30）
- **問題**：Proofread 影片下方嘅 `.rv-b-vid-panels` 係 2 欄固定高度 grid，但 v3.18 將「自訂 Prompt」(`#promptPanel`) 作為第 3 個 grid child 塞入，產生 implicit 第 2 行，將「詞彙表」+「字幕設定」壓扁到 ~88px（MacBook 14" 1512×982 實測），自訂 Prompt 半欄孤立。
- **修復**：完全移除自訂 Prompt 面板（`frontend/proofread.html` 嘅 #promptPanel HTML + `.rv-b-prompt-*` CSS + 6 個 prompt JS function + 2 變量 + call site，共 296 行刪除）。grid 回復單行 2 欄，兩 panel 各佔全高（220px，字幕設定 6 行完整可見、唔 scroll）。
- **保留**：per-file `prompt_overrides` 資料模型 + `PATCH /api/files/<id>` + `/api/prompt_templates` API 完全不變（只移除 proofread UI 入口）；dashboard `📝 自訂` chip 保留。Backend 零改動。
- **測試**：新增 `frontend/tests/test_proofread_layout.spec.js`（panel 移除 + 兩 panel 尺寸，2 PASS）；刪 `test_prompt_panel.spec.js`；`test_v6_pipeline_strip.spec.js` 移走 2 個 proofread-coupled test（保留 5 個 dashboard-strip test，5 PASS）。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-proofread-panel-layout-fix-design.md) / [plan](docs/superpowers/plans/2026-05-30-proofread-panel-layout-fix-plan.md)。

### v3.21 — Unified Pipeline Progress Contract + Queue Panel Real-time Bar
- **目標**：右側 queue panel 每個 row 根據對應 file 嘅處理階段，顯示接近實時嘅 0–100% 進度條同 stage label。Architecture 必須兼容 (a) 舊有 Profile 模式、(b) V6 Dual-ASR Pipeline、(c) 任何未來新增 pipeline kind — frontend 對 pipeline 內部結構零 awareness。Spec: [docs/superpowers/specs/2026-05-29-queue-progress-prompt.md](docs/superpowers/specs/2026-05-29-queue-progress-prompt.md)。Plan: [docs/superpowers/plans/2026-05-29-queue-progress-plan.md](docs/superpowers/plans/2026-05-29-queue-progress-plan.md)。Architecture doc: [docs/superpowers/architecture/pipeline-progress-contract.md](docs/superpowers/architecture/pipeline-progress-contract.md)。
- **新 backend module**（`backend/progress_adapter.py`）：Adapter pattern — `ProgressSnapshot` dataclass + `ProgressAdapter` class（`threading.RLock` cache + 500ms throttle）+ module-level singleton（`get_adapter()` / `init_adapter(socketio)` / `reset_adapter()`）。兩類 shim helper：Profile shims（`report_from_subtitle_segment` → `"轉錄中"`；`report_from_translation_progress` → `"翻譯中"`）；V6 shim（`report_from_v6_stage` — 5 個內部 stage 映射做單一 0–100%，`V6_STAGE_LABELS` 提供 5 個 `stage_type` → label mapping）。
- **Backend wiring**：(a) `backend/app.py` — `init_adapter(socketio)` 喺 boot 時調用；每個 native `emit("subtitle_segment", ...)` / `emit("translation_progress", ...)` call 之後加對應 shim call。(b) `backend/pipeline_runner.py::_socketio_emit` — V6 native events (`pipeline_stage_start` / `pipeline_stage_progress` / `pipeline_stage_done`) 路由過 `report_from_v6_stage`。
- **`/api/queue` schema 擴充**：每 row 新加 3 個 field：`progress_pct: number | null`、`stage_label: string | null`、`stage_state: 'idle' | 'active' | 'done'`。由 `get_adapter().get_snapshot(file_id)` 提供。無 snapshot 時 defaults：`null / null / 'idle'`。
- **Frontend 改動（最小化）**：`frontend/js/queue-panel.js` 加 `socket.on('pipeline_progress')` listener、`_progressCache: Map<file_id, snapshot>`、render row 加 bar / pct 數字 / spinner UI。`frontend/index.html` 加 `.qp-bar` + `@keyframes qpSpin` CSS。其他 dashboard 邏輯完全唔郁。
- **Tests**：11 pytest（`backend/tests/test_progress_adapter.py`）涵蓋 ProgressSnapshot、adapter throttle、Profile shims、V6 shim + label mapping、singleton lifecycle；3 pytest（`backend/tests/test_queue_progress_pct.py`）涵蓋 `/api/queue` 3 個新 field；5 Playwright（`frontend/tests/test_queue_progress.spec.js`）涵蓋 Profile ASR 0→100%、Profile MT label flip、V6 5-stage monotonic bar、cold-start reload、dummy `pipeline_v99` forward-compat（frontend 零改動）。全部 GREEN。
- **Operator-visible 行為**：Profile 跑 1 條 video — 排隊中 spinner dot → 轉錄中 0–100% bar → 翻譯中 0–100% bar → 完成 100% 然後 row auto-hide。V6 跑 1 條 video — 排隊中 → VAD 切段中 → Qwen3 識別中 → mlx 對齊中 → Merge 中 → Refiner 校對中 → 完成。Page reload 中段：bar 即時顯示非 0（cold-start 由 `/api/queue` 提供 cached pct）。跨 tab 同步：tab A 跑緊 50%，tab B 即時見 50%。
- **Forward-compat invariant**：加 V7 或任何未來 pipeline kind 時，frontend `queue-panel.js` 零修改，只需加 backend shim 或喺 handler 直接 call `get_adapter().report(...)`。呢個 invariant 由 `pipeline_v99` Playwright test 自動驗證。
- **Out of scope**（明確 defer）：左側 file card 嘅 progress bar（右側 queue panel 只）；render job 進度（獨立 polling 已有）；V6 5 個 internal stage 嘅 sub-bar hover tooltip；整體 pipeline 加權 0–100%（per-state 模式已定）；`queue_changed` payload 擴充（永遠保持 zero-payload）。
- **Files touched**：1 個 new backend module（`progress_adapter.py`）、2 個 backend modified（`app.py` ~20 LOC additive shim calls + `init_adapter`；`pipeline_runner.py` `_socketio_emit` ~15 LOC）、1 個 backend modified（`jobqueue/routes.py` 3 new fields on `/api/queue`）、1 個 frontend modified（`queue-panel.js` ~80 LOC）、1 個 frontend modified（`index.html` ~20 LOC CSS）、2 個 new test files（`test_progress_adapter.py` + `test_queue_progress_pct.py`）、1 個 new Playwright spec（`test_queue_progress.spec.js`）。10 commits on finalize-debug branch (226077a → 3bcf782)。

### v3.20 — V6 Qwen3 Subprocess IPC Hardening + Media Preload Fix
- **Background**: 2026-05-29 用戶上傳 34.6 MB 粵語廣播片 (file `183e38257865`, gamehub) 揀 V6 `[v6] 賽馬廣播 (Cantonese)` pipeline，9 分鐘後 registry 仍 `transcribing` / `segments: []` / job DB row `status=running, attempt_count=1, error_msg=NULL`。後端 log 完全冇 V6 stage 級 stdout — pipeline 真實 hang 咗。同時用戶單一 click 觸發 80+ `/api/files/<id>/media` 206 byte-range request，製造「log 好嘈似有 bug」嘅錯覺。Incident report: [docs/superpowers/incidents/2026-05-29-v6-silent-execution-handover.md](docs/superpowers/incidents/2026-05-29-v6-silent-execution-handover.md).
- **Forensic evidence** ([docs/superpowers/validation/2026-05-29-v6-ipc-deadlock-evidence.md](docs/superpowers/validation/2026-05-29-v6-ipc-deadlock-evidence.md))：用 macOS `sample 49396 3` 捕捉到 stuck Qwen3 child (PID 49396, alive 34 min, CPU time 0:36.50, STAT=S, physical footprint 6.4 GB / peak 14.6 GB — 證實 MLX 已 inference 完並部分釋放 scratch buffer)。**100% of 2604 main-thread samples 落喺 `_io_FileIO_write → _Py_write_impl → write (libsystem_kernel)`**，所有 MLX worker thread (`Thread_50416461..66`) idle 喺 `std::condition_variable::wait`。經典 POSIX pipe full-buffer wedge。
- **Root cause**：child (`backend/scripts/v5_prototype/qwen3_vad_subprocess.py:128`) 喺 hot loop 每 region 寫一行 `[region N]` log 到 **stderr**，最後寫一個 big JSON blob 到 **stdout** (line 130)。Parent (`backend/engines/transcribe/qwen3_vad_engine.py:154-165` pre-v3.20) 喺 `while proc.poll() is None: time.sleep(0.5)` loop 入面 **只喺 subprocess exit 之後** 先 drain stdout/stderr (lines 168-169)。macOS pipe buffer 16-64 KB ceiling 撐爆 → child block 喺 kernel `write()` syscall → parent `poll()` 永遠唔見 non-None → 無限等。三個火上加油：(a) 完全冇 `timeout=` kwarg 任何 safety net；(b) parent 冇 SocketIO progress hook，operator 完全冇得睇 progress；(c) child stderr 寫嘅內容係寶貴嘅 per-region completion 訊號，竟然因為 buffer 滿而變死。
- **Fix（Spec §4.1 Option A — concurrent drain via daemon threads）**：抽 `_drain_subprocess(proc, timeout_sec, cancel_event, progress_callback) -> tuple[bytes, bytes]` 做 module-level helper 喺 [backend/engines/transcribe/qwen3_vad_engine.py:46-155](backend/engines/transcribe/qwen3_vad_engine.py)。兩個 daemon thread (`qwen3-stdout-drain` + `qwen3-stderr-drain`) 各自 block 喺 `proc.stdout.read(4096)` / `proc.stderr.read(4096)` 並 buffer 入 bytearray，stderr drain 額外做 `\n`-terminated line split + 經 `progress_callback` 即時 forward。Main thread `while proc.poll() is None:` loop 每 `_CANCEL_POLL_INTERVAL=0.5s` 同時 check 兩件事：(i) `cancel_event.is_set()` → `proc.terminate()` → 3s grace → `proc.kill()` → raise `JobCancelled`；(ii) `time.time() > deadline` → 同樣 shutdown sequence → raise `RuntimeError`。`finally:` block 用 `.join(timeout=5)` 強制 join drain threads，防 fd leak 同 trailing bytes 走失。為咗考慮其他 Option：B (`subprocess.communicate(timeout=)`) 唔能 stream progress；C (`asyncio.subprocess`) 要 rewrite `_run_v6` 做 async 架構大改動；D (child-side stdout JSONL streaming) 仍然要 Option A 做 prerequisite，treat 為 future additive enhancement。
- **新 env var `R5_QWEN3_TIMEOUT_SEC`**：default `900` 秒（15 分鐘，~1.5× healthy 4-6 min broadcast budget）。超時 → terminate → 3s grace → kill → `RuntimeError`「qwen3_vad subprocess exceeded {N}s timeout」。由於 raise `RuntimeError`（唔係 `JobCancelled`），`JobQueue._run_one` 會 mark 個 job `status='failed'` + `error_msg` set，搭配 v3.13 嘅 poison-pill cap (`R5_MAX_JOB_RETRY=3`) 避免 server restart 觸發無限 retry。Operator 想跑 > 15 min 嘅 broadcast 喺 `backend/.env` set 較大值（例如 `R5_QWEN3_TIMEOUT_SEC=1800`）。
- **T7 SocketIO progress hook**：`transcribe_regions(audio_path, vad_regions, cancel_event, progress_callback=None)` 加 optional `progress_callback: Optional[Callable[[str], None]]` kwarg，threaded 入 `_call_subprocess` → `_drain_subprocess`。Stderr drain 每收一條 `\n`-terminated line 就 invoke callback；callback 拋 exception 唔會殺死 drain thread（try/except swallow）。喺 [backend/stages/v6/qwen3_per_region_stage.py:46-69](backend/stages/v6/qwen3_per_region_stage.py) wire 入一個 local closure，透過已有嘅 `pipeline_runner._socketio_emit("pipeline_stage_progress", {...})` payload broadcast — strictly **additive**，唔需要改 `StageContext` schema 或新增 SocketIO event 名。`progress_callback=None` (default) 完全保留 pre-T7 行為（stderr 純 buffer，只喺 failure path 浮出）。
- **Tests (T4)**：4 個新 unit test 跑真正 OS subprocess + prototype children at [backend/scripts/v6_prototype/_children/](backend/scripts/v6_prototype/_children/) — `test_drain_handles_256kb_stderr_flood_without_hang` ([test_qwen3_vad_engine_drain.py](backend/tests/test_qwen3_vad_engine_drain.py))、`test_drain_forwards_stderr_lines_to_progress_callback` (同一文件，T7 bonus coverage)、`test_drain_raises_runtime_error_on_wall_clock_timeout` ([test_qwen3_vad_engine_timeout.py](backend/tests/test_qwen3_vad_engine_timeout.py))、`test_drain_raises_jobcancelled_when_cancel_event_set_mid_flight` ([test_qwen3_vad_engine_cancel.py](backend/tests/test_qwen3_vad_engine_cancel.py))。3 個 required（spec §5 Testing strategy）+ 1 個 bonus 確保 T7 callback contract 唔退化。
- **Tests (T5 regression unblock)**：T7 wire-up 改 `transcribe_regions` signature 加 `progress_callback` kwarg，連帶弄崩 `test_v6_stages.py` 兩個 `assert_called_once_with(...)` (mock 對 positional/kw mismatch 失敗) 同一個 `isinstance(exc, JobCancelled)` (cross-module sys.modules 污染 - JobCancelled 多 import path 後 class identity 唔再 match)。修正方式：mock assertion 改用 `progress_callback=ANY` (`unittest.mock.ANY`)；isinstance 換做 `type(exc).__name__ == "JobCancelled"` name-string compare 避過 sys.modules 污染；cancel wall-budget assertion 由 4s 放鬆到 8s 配合新嘅 join 開銷。**全 suite 結果：971 passed / 15 failed = 同 v3.19 baseline 完全一致（11 Playwright E2E 需 browser、1 macOS tmpdir colon-escape、1 SocketIO CORS、1 queue route、1 雜項），zero new regression**。
- **Media preload separate fix (commit `c2256fc`)**：單一 click 觸發 80+ `/media` 206 byte-range request 嘅錯覺問題，係 Chromium `<video>` element 預設 `preload="auto"` 加上 MP4 moov-atom-at-tail layout，瀏覽器主動掃 file metadata 引發 Range request 風暴。修正兩處：(a) [frontend/index.html:1413](frontend/index.html) `<video id="videoPlayer" preload="metadata">` — 只 fetch 頭幾 KB metadata；(b) [backend/app.py:3544](backend/app.py) `send_file(str(media_path), as_attachment=False, conditional=True)` — Flask/Werkzeug 處理 `If-Range` + 適當 206 response，畀 Chrome stream 而唔係 fall back 去 full GET re-request。完全 backward-compat。
- **Validation gate (CLAUDE.md "Validation-First Mode" 全程遵守)**：(1) 先 live `sample 49396` 拎到 100% write() block 嘅 C-stack empirical evidence；(2) 寫 [backend/scripts/v6_prototype/ipc_drain_prototype.py](backend/scripts/v6_prototype/ipc_drain_prototype.py) 跑 12 個 quantitative cell 嘅 matrix (5 stderr sizes × 2 patterns + 2 slow children = 12 runs) — OLD pattern 喺 16 KB stderr 仍 OK、64 KB 100% hang (rc=-9 SIGKILL after 60s harness timeout)、256 KB / 1024 KB 同樣 hang；NEW pattern 喺 1024 KB stderr 0.5s 內完成、stdout JSON 正確 parse、slow child 5s sleep 0% latency penalty；(3) prototype gate PASSED 之後先入 spec → plan → 真 production code 改動。完整 prototype report: [docs/superpowers/validation/2026-05-29-v6-ipc-fix-prototype-report.md](docs/superpowers/validation/2026-05-29-v6-ipc-fix-prototype-report.md)。
- **T6 Integration verified ✅ (2026-05-29)**: 喺 fix branch 跑 alt-port 5002 instance，3 條 reproducer 全部 PASS — Test 1 原 incident 同源 `gamehub-…赤色沙漠.mp4` Cantonese pipeline **284.5s** (183 segments，refined ZH「又翻到每個禮拜你最期待嘅 game 盒」)；Test 2 `rHQsCK` Cantonese pipeline **83.8s** (24 segments)；Test 3 `Winning Factor` English pipeline **234.9s** (112 segments，EN-target by design 所以 `by_lang.zh` empty)。3 條全部 ≤ 600s spec budget、`error_msg=NULL`、無 orphan subprocess。完整 report: [docs/superpowers/validation/2026-05-29-v6-ipc-fix-report.md](docs/superpowers/validation/2026-05-29-v6-ipc-fix-report.md). Playbook 同設置細節: [docs/superpowers/validation/2026-05-29-v6-ipc-fix-integration-playbook.md](docs/superpowers/validation/2026-05-29-v6-ipc-fix-integration-playbook.md).
- **Files touched**：3 production files modified — `backend/engines/transcribe/qwen3_vad_engine.py` (+185/-31 LOC 大部分係新 `_drain_subprocess` helper 同 docstring)、`backend/stages/v6/qwen3_per_region_stage.py` (+23/-1 LOC progress_callback closure)、`backend/app.py` (+1/-1 LOC `conditional=True`)、`frontend/index.html` (+1/-1 LOC `preload="metadata"`)。3 new test files (~277 LOC 共 4 個新 test case)。2 new prototype children (`_children/flood_child.py` +35 LOC、`_children/slow_child.py` +30 LOC) + 1 new harness (`ipc_drain_prototype.py` +208 LOC) 全部 commit 入 `backend/scripts/v6_prototype/`。5 new doc files (incident + spec + plan + 2 validation reports + integration playbook，~1056 LOC docs total). 1 modified test (`test_v6_stages.py` +8/-0 LOC) 跟 T7 signature 對齊。**`git diff Finalize..HEAD --stat`：17 files changed, 1795 insertions(+), 31 deletions(-)**.
- **Spec / Plan / Validation links**：spec [docs/superpowers/specs/2026-05-29-v6-subprocess-ipc-fix-design.md](docs/superpowers/specs/2026-05-29-v6-subprocess-ipc-fix-design.md)；plan [docs/superpowers/plans/2026-05-29-v6-subprocess-ipc-fix-plan.md](docs/superpowers/plans/2026-05-29-v6-subprocess-ipc-fix-plan.md)；deadlock evidence [docs/superpowers/validation/2026-05-29-v6-ipc-deadlock-evidence.md](docs/superpowers/validation/2026-05-29-v6-ipc-deadlock-evidence.md)；prototype matrix [docs/superpowers/validation/2026-05-29-v6-ipc-fix-prototype-report.md](docs/superpowers/validation/2026-05-29-v6-ipc-fix-prototype-report.md)；integration playbook [docs/superpowers/validation/2026-05-29-v6-ipc-fix-integration-playbook.md](docs/superpowers/validation/2026-05-29-v6-ipc-fix-integration-playbook.md)。
- **Commit SHAs (順序)**：`97d789a` (T1 incident report + validated evidence) → `c2256fc` (T2 media preload + send_file conditional) → `d76d91b` (T2.5 spec + plan + prototype + validation report) → `26e208e` (T3+T4+T7 concurrent drain in `qwen3_vad_engine.py`, 3 unit tests, SocketIO progress hook via `_drain_subprocess` helper) → `ab98718` (T5 test fixes — `assert_called_once_with` → `progress_callback=ANY`; `isinstance(JobCancelled)` → type name compare for module-pollution; cancel wall budget 4s→8s) → `1e5113f` (T6 playbook).

### v3.19 — V6 Dual-ASR Pipeline (VAD + Qwen3-ASR + Refiner) merged from feat/frontend-redesign
- **Background**: feat/frontend-redesign 上嘅 V6 architecture（VAD + dual-ASR + Refiner）operator-validated 過後 graft 入 dev，保留 dev 嘅 vanilla HTML/JS frontend 同所有 v3.17-v3.18 改動。Spec: [docs/superpowers/specs/2026-05-28-v6-dual-asr-merge-design.md](docs/superpowers/specs/2026-05-28-v6-dual-asr-merge-design.md). Plan: [docs/superpowers/plans/2026-05-28-v6-dual-asr-merge-plan.md](docs/superpowers/plans/2026-05-28-v6-dual-asr-merge-plan.md). Source merge commit on feat branch: 95d6f67.
- **架構**: V6 backend 完全活喺新文件夾（`backend/stages/`, `backend/engines/`, `backend/pipelines.py`, `backend/pipeline_runner.py`, `backend/routes/pipelines.py`），dev 既有 `profiles.py` / `transcribe_with_segments` / `_auto_translate` 完全唔郁。`settings.json` 加 `active_kind` + `active_id` 兩個 field（backward-compat 保留 `active_profile` mirror）。File registry 喺 upload 一刻 snapshot `active_kind`/`active_id`，防 race condition（mid-job 切 active 唔影響進行中 job）。
- **5-stage DAG（V6 only）**: Stage 0 Silero VAD → Stage 1A Qwen3-ASR per region + Stage 1B mlx-whisper full audio（純取 timestamps）→ Stage 2 time-anchored merge → Stage 3 LLM refiner（Ollama qwen3.5:35b-a3b-mlx-bf16）→ persist。Qwen3 = content authority；mlx = timing authority；refiner 簡化 prompt（VAD 已 filter 走 silence，唔需要再 detect hallucination）。詳見 [docs/superpowers/specs/2026-05-21-v6-vad-dual-asr-refiner-design.md](docs/superpowers/specs/2026-05-21-v6-vad-dual-asr-refiner-design.md)（feat branch 原 design）。
- **Frontend**: Pipeline strip preset 菜單分 2 section（**舊有 Profile 組合** / **Dual-ASR Pipeline (V6)**）。V6 mode active 時 strip column 由 ASR/MT/術語表 swap 做 VAD/Qwen3 Context/Refiner。Click Qwen3 Context / Refiner column 彈 inline panel 直接 edit pipeline JSON / refiner profile JSON。Proofread page 「自訂 Prompt」面板 mode-aware — V6 file 顯示 `qwen3_context` + `refiner_prompt` 兩個 textarea，Profile file 仍係 v3.18 嘅 4 個 textarea（`alignment_anchor_system` / `single_segment_system` / `pass2_enrich_system` / `pass1_system`）。
- **Backend dispatch**: `_asr_handler` 由 `file.active_kind` 分流 — `pipeline_v6` 入 `PipelineRunner._run_v6`，`profile` 行 `transcribe_with_segments`。`_mt_handler` 對 V6 file short-circuit（Stage 3 refiner 已內含 MT 角色，無需獨立 MT step）。新加 `POST /api/active` 統一 set-active endpoint（接 `kind=profile|pipeline_v6` + `id`），舊 `/api/profiles/<id>/activate` 仍兼容。`/api/me` 新增 `active_kind` + `active_id` + `v6_available` 三個 field。Cancel / retry / crash recovery 全部沿用 R5 Phase 2-5 既有設計。
- **Hardware / env**: `silero-vad>=6.2.1` 入 main venv（已 install）；`mlx_qwen3_asr 0.3.5` 隔離喺 `backend/scripts/v5_prototype/venv_qwen/`（py3.11 subprocess venv）。Main py3.9 backend 用 subprocess JSON stdin/stdout 跟 Qwen3 venv 通訊。[backend/scripts/setup_v6.sh](backend/scripts/setup_v6.sh) idempotent 一鍵起 venv。Boot 時 `V6_AVAILABLE` flag detect — venv 唔存在前端 V6 section 灰咗 + 顯示「⚠ Qwen3 venv 未安裝 — 跑 setup_v6.sh」。
- **Imported V6 pipelines**: 2 個 production-validated pipeline JSON — [`backend/config/pipelines/4696bbaa-...json`](backend/config/pipelines/) (賽馬廣播 Cantonese, qwen3_context 預設「香港賽馬新聞」相關人名) + [`backend/config/pipelines/641a77ec-...json`](backend/config/pipelines/) (Winning Factor EN newscast)。`user_id` 由 feat branch 嘅 627 rewritten 為 `null`（shared）；dev 所有用戶都見到。配套 2 個 refiner profile、4 個 transcribe profile、1 個 LLM profile、3 個 refiner prompt template。
- **`prompt_overrides` 擴展**: v3.18 嘅 whitelist 由 4 keys (`alignment_anchor_system` / `single_segment_system` / `pass2_enrich_system` / `pass1_system`) 擴到 6 keys，加 `qwen3_context` + `refiner_prompt`。Resolver 3-level fallthrough mode-aware — Profile mode 行 `file > active profile > None`，V6 mode 行 `file > active pipeline > None`。
- **Registry migration**: [backend/scripts/migrate_active_kind.py](backend/scripts/migrate_active_kind.py) idempotent — boot 自動 backfill `active_kind="profile"` + `active_id` （prefers `profile_id` field from v3.10，fallback `prod-default`）到舊 file entries。已有 entries 唔郁。
- **Tests**: ~88 個 backend test cases graft 自 feat branch（55 stage + 18 runner + 14 refiner JSON unwrap + 7 pipeline config）+ ~31 個新 dev-side cases（settings migration 6 + validator extension 5 + manager wire-up 8 + register_file snapshot 4 + dispatch 5 + /api/active 5 + migration 4 + V6_AVAILABLE 2，總 39 — 部分數字略有出入但都 green）+ 7 個 Playwright（V6 preset menu + columns + inline panel + Proofread mode-aware；live 5 PASS / 2 SKIP — Proofread 嘅 2 個 SKIP 要 V6 file 入 registry 先 covered）。Full suite final: ~940 PASS / 14 pre-existing fail（11 Playwright E2E、1 macOS tmpdir colon-escape、1 SocketIO CORS、1 queue route — 同 v3.18 baseline 一致）。
- **Inline catches during graft**:
  - Task 1.2: `stages/v5/asr_primary_stage.py` 用 dev 冇嘅 `dedupe_cascade_repeats` + `filter_tail_english_orphan` helper → graft 兩個 helper 入 `asr/segment_utils.py`（commit `8a205ff`）
  - Task 1.4: `routes/pipelines.py` 用 dev 冇嘅 `require_pipeline_owner` decorator + dev 冇嘅 `translator_profiles` / `verifier_profiles` manager → graft 入 `auth/decorators.py` + 2 個 manager module（commit `f605907`）
  - Task 4.1: Playwright run 發現 `set_v4_managers()` setter 喺 graft 入嚟但 app.py boot 冇 call → 加 call wire managers 入 decorator globals（commit `7031ddb`）。冇呢個 fix `PATCH /api/pipelines/<id>` 500「_pipeline_manager not initialised」。
- **Out-of-scope**: V5 dual-ASR + verifier path（`stages/v5/` import 咗但唔 wire entry point）、React frontend（用戶明確保留 vanilla）、per-file VAD threshold override、V6 over OpenRouter（首批 Ollama only）、Stage 1A ∥ 1B parallel execution（sequential 如 feat branch）、v3.18 MT overrides ↔ V6 refiner overrides auto-translation。
- **Files touched (Phase 1+2+3+5)**: ~83 new files + 6 modified（`app.py` ~150 LOC additive、`profiles.py` set_active+get_active rewrite、`auth/decorators.py` +50 LOC、`auth/routes.py` /api/me extension、`translation/prompt_override_validator.py` whitelist、`requirements.txt` silero-vad、`asr/segment_utils.py` +2 helpers、`index.html` ~500 LOC、`proofread.html` ~100 LOC）。28-commit branch ready for merge to main pending Phase 7 operator validation。
- **Operator validation**: 同 feat branch [docs/superpowers/validation/v6-validation.md](docs/superpowers/validation/v6-validation.md) 嘅 metrics 對齊 — 賽馬 4-min Cantonese + Winning Factor 14-min EN newscast。Phase 7 詳細 report 喺 [docs/superpowers/validation/v3.19-v6-merge-report.md](docs/superpowers/validation/v3.19-v6-merge-report.md)（pending — task 7.3）。
- **Frontend audit (Sprint 4 / 2026-05-29)**: Sprint 1 shipped the backend half of Phase A BLOCKER 1 (mirror `by_lang.<lang>.*` to top-level legacy fields; expose `active_kind` on `/api/files`). The frontend half — making `loadSegments()` / `loadFileSegments()` dispatch on `fileInfo.active_kind` — landed under this Sprint 4. Mode-aware single dispatch point per surface; V6 path fetches `/translations` only (legacy `/segments` returns `[]` for V6), maps `source_text → segs[i].en` (Qwen3 raw Cantonese, **read-only** with tooltip + CSS hint), maps `<source_lang>_text → segs[i].zh` (Stage 3 refined, editable). Derives `srcLang` from `t.source_lang || 'zh'` so EN V6 pipelines (Winning Factor) work too. Downstream consumers (subtitle overlay, Find&Replace, approve, render, export) read `segs[]` and continue to work unchanged. 4 new Playwright cases in [frontend/tests/test_v6_frontend_audit.spec.js](frontend/tests/test_v6_frontend_audit.spec.js). Profile mode regression bar: Phase A spec re-runs 24/24. Reproducer: file `d159d9dbd309` (賽馬娛樂新聞) — 83 refined ZH including 「布浩穎同埋見習騎師袁幸堯啊」 now visible in Proofread table + dashboard video overlay. Spec: [docs/superpowers/specs/2026-05-29-v6-frontend-audit-design.md](docs/superpowers/specs/2026-05-29-v6-frontend-audit-design.md). Plan: [docs/superpowers/plans/2026-05-29-v6-frontend-audit-plan.md](docs/superpowers/plans/2026-05-29-v6-frontend-audit-plan.md). Commits: ebd1f0b (proofread loadSegments) + 8cb7844 (EN V6 + error handling fix) + 52c079f (EN read-only) + 77b1016 (ZH edit regression guard) + 19e7f32 (dashboard loadFileSegments).

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
