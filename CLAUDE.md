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

### v3.9 — MT Cascade Drift Fix + ASR Fine-Seg Tuning
- **Background**：v3.8 ship 完 fine_segmentation 後，user 觀察到中文翻譯後半段同英文時間軸唔對稱。診斷發現三層 root cause：(1) `_parse_response` parser bug；(2) production engine `qwen2.5-3b` 太弱、SKIP/ECHO 編號率高；(3) sentence-vs-segment boundary mismatch — LLM 將 batch 視作連續英文按中文句切，唔跟 ASR 時間 cut。
- **Validation**: 5 個 enhancement candidates 全部跑過 cross-fixture A/B（RealMadrid 5min 廣播訪問 + Trump 5min 政治演講）。詳細數據見 [docs/superpowers/specs/2026-05-03-asr-fine-segmentation-validation.md](docs/superpowers/specs/2026-05-03-asr-fine-segmentation-validation.md) v3.9 增量段落。
- **MT parser fix（[backend/translation/ollama_engine.py](backend/translation/ollama_engine.py)）**：`_parse_response` 由 sort + positional remap 改為 dict-by-number slot-fill（`slots[num-1] = text`）。SKIP cascade → 0 drift，ECHO cascade → contained 喺 slot 0，overshoot → silently drop，duplicate → first wins。Drop-in replacement，return shape / `[TRANSLATION MISSING]` sentinel / retry path 100% 不變。新 `ParseDiagnostics` TypedDict + `logger.info` telemetry 喺 abnormal batch 觸發。Mock 1000-trial drift 9.30% → 5.03%（−27%）。
- **ASR pad 200→300ms**：`_vad_segment` 預設值。Cross-fixture sent% 一致 +3.5%（RM +3.48 / Trump +3.66），func% RM −6.43。減少 chunk boundary 子音 clip。
- **Whisper hallucination guards**（[sentence_split.py](backend/asr/sentence_split.py) `_HALLUCINATION_GUARDS`）：每個 mlx call（chunk + fallback path）加 `no_speech_threshold=0.1` / `compression_ratio_threshold=1.4` / `logprob_threshold=-1.0`，per mbotsu/mlx_speech2text reference。防止沉默 chunk 幻覺「Thanks for watching」「Subscribe」呢類誤讀。
- **`safety_max_dur` 9.0→6.0**：`word_gap_split` 預設值。解 mlx-whisper 30s decoder window 內部嘅 long monologue（Trump fixture pre-existing 8.00s 段，VAD 切點層解唔到，因為段係 mlx 一次性 emit 喺正常 ≤25s chunk 內）。Trump max **8.00 → 5.98s**，過 v3.8 acceptance gate（max ≤ 6.0s）。Cost：sent% −7.8（force-split 失去原段尾標點），但 UX 上 2× 3s 段優於 1× 8s 字幕。
- **OpenRouter engine swap（profile-level）**：`prod-default.json` MT engine 由 `qwen2.5-3b`（local Ollama，3B params）切到 OpenRouter `qwen/qwen3.5-35b-a3b`（context 262K，$0.16/M in $1.30/M out）。35B 翻譯流暢、術語精準、SKIP/ECHO 率比 3B 低 1 個 order of magnitude。
- **Sentence pipeline opt-in（profile-level）**：`translation.use_sentence_pipeline: true` 喺 `prod-default.json` 開啟。pySBD 合併 ASR seg 做完整中文句 → translate → char-prop redistribute 返每個 ASR 時間 slot。直接解決 sentence-vs-segment boundary mismatch（v3.1 已實作但預設關，v3.9 default 啟用）。
- **Profile JSON 安全**：`backend/config/profiles/prod-default.json` 加入 `.gitignore`（隔住 OpenRouter `api_key`），`git rm --cached` 由 index 抽走。同 `dev-default.json` + `*.local.json` 一齊處理。Repo 從此唔再 track 任何含 secret 嘅 profile。
- **Rejected enhancements**（empirical evidence）：
  - `vad_min_silence_ms` 500→800：破 max ≤ 6s gate（5.48 → 8.00）
  - mbotsu collect_chunks 全 strip silence：Trump sent% −25.7%（剝走 silence 等於剝走 Whisper 嘅 sentence-end signal）
  - mbotsu hybrid silence-aware split：Trump max no-op（8s 問題喺 mlx decoder 內部，VAD 切點層解唔到）
  - `initial_prompt` cross-chunk continuity：cross-fixture sent% inconsistent（RM +3.58 / Trump −1.28），35B model 已 7/8 named entity 一致，prompt overhead 不抵
- **新 test 數量**：+9（5 parser slot-fill v2 + 4 fine-seg tuning），517 → 520 PASS / 12 pre-existing FAIL
- **Backend total**：509 → **520 PASS** / 12 pre-existing FAIL（532 total）

### v3.8 — ASR Fine Segmentation (Silero VAD chunk-mode + word-gap refine)
- **Background**：mlx-whisper 30s window 結構性限制令 broadcast 訪問風格（run-on 句）經常喺 sentence 中段 emit timestamp（cross-30s-window mid-clause cut）。例如「...what the team really needs is a」+「radical overhaul...」應為一句但被 Whisper 30s window 強行切開。純 mlx-whisper kwargs（length_penalty / beam_size / max_initial_timestamp / hallucination_silence_threshold 等）11-config A/B 證實無法解決。
- **Validation**: 詳見 [docs/superpowers/specs/2026-05-03-asr-fine-segmentation-validation.md](docs/superpowers/specs/2026-05-03-asr-fine-segmentation-validation.md)。跑 11 mlx-whisper kwargs configs + 3-way prototype（faster-whisper+vad / word-gap split / Silero VAD chunk）+ stack tuning。Cross-style 已驗證 Real Madrid sports interview + Trump 政治演講兩個極端 broadcast style。
- **新 module**: [backend/asr/sentence_split.py](backend/asr/sentence_split.py) — Silero VAD pre-segment（threshold 0.5 / min_silence 500ms）→ sub-cap chunks ≤ 25s → mlx-whisper transcribe per chunk（temperature=0.0 + word_timestamps=True + condition_on_previous_text=False）→ word-gap refine（max_dur=4.0s / gap_thresh=0.10s / min_dur=1.5s）。架構性消除 cross-30s-window mid-clause cut。
- **Profile schema**：ASR block 加 10 個 fields（fine_segmentation, temperature, vad_threshold, vad_min_silence_ms, vad_min_speech_ms, vad_speech_pad_ms, vad_chunk_max_s, refine_max_dur, refine_gap_thresh, refine_min_dur）；translation block 加 1 個 field（skip_sentence_merge）。Frontend UI 暴露 fine_segmentation toggle + temperature；其餘 9 fields 只 JSON edit。
- **Validation 結果**（5min Real Madrid，large-v3，post-impl live test）：
  - Baseline: 66 segs, mean 4.44s, max 6.24s, 43/66 (65%) 過 84c, sent_end 19.4%, ❌ #3+#4 mid-clause cut
  - L1 + L3 stack（fine_seg）: 85 segs, mean 3.07s, p95 4.82s, max 5.64s, tiny rate 4.7%, ✅ #3+#4 修復, 100% words populated
- **Engine compat**：Phase 1 只 mlx-whisper；whisper engine（faster-whisper / openai-whisper）已有自己 vad_filter 機制。Profile validation reject `fine_segmentation: true` 配 engine ≠ mlx-whisper。
- **Grandfather 策略**：既有 file 唔重新 transcribe；只新 upload 行新 stack。Registry 加 `transcribed_with_fine_seg` flag 標記。
- **Error handling**：Setup error（silero-vad 缺）= strict raise；runtime fallback（VAD 0 chunks / chunk fail）= permissive + WebSocket `transcription_warning` event。
- **新 dep**: `silero-vad>=6.2.0` (~1.8 MB ONNX，無 PyTorch 需要)
- **新 test 數量**: ~30（17 sentence_split + 3 mlx_engine + 9 profiles + 5 app + 2 live integration）
- **Backend total**: 469 → 509 PASS / 12 pre-existing FAIL (521 total)

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
