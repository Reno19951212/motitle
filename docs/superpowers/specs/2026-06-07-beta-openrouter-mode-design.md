# Admin Beta 測試模式（OpenRouter 雲端模型）— Design

- **Date**: 2026-06-07
- **Branch**: `feat/admin-beta-openrouter-models`
- **Status**: Approved (design) — pending Validation-First Phase 0 before ASR code lands
- **Owner**: Reno

---

## 1. 目標 / 動機

喺 Admin User 區加一個**全局單一開關**嘅「Beta 測試模式」。開啟之後，後台現時用緊嘅兩個生產模型會由本地切換去 OpenRouter 雲端，做質素 / 速度 / 成本對比測試：

| 模型 | 本地（現狀） | Beta 模式（OpenRouter） |
|---|---|---|
| ASR（語音轉文字） | mlx-whisper `large-v3`（`_output_lang_asr_override`） | `openai/whisper-large-v3`（`/api/v1/audio/transcriptions`，$0.0015/分鐘） |
| LLM（MT + refiner） | Ollama `qwen3.5:35b-a3b-mlx-bf16` @ temp 0.3 | `qwen/qwen3.5-35b-a3b`（`/chat/completions`，$0.14/1M in、$1.00/1M out） |

兩個 OpenRouter model id 揀**真正 parity**（同一個 large-v3 / 同一個 Qwen3.5-35B-A3B MoE），所以對比結果反映嘅係「雲 vs 本地同一模型」嘅差異，唔係換模型嘅差異。

### 非目標（YAGNI）
- 唔做 per-user beta 旗標（全局單一開關）。
- 唔做可編輯 model id（硬編碼 parity，要試別個雲端模型再改 code）。
- 唔做自動 fallback 返本地（測試模式要暴露雲端真實效果）。
- 唔改 Profile-mode 翻譯路由（呢個 feature 只針對 output_lang 主流程 + 共用 `llm_call` 注入點）。

---

## 2. 關鍵技術事實（已查證）

- OpenRouter **有** `openai/whisper-large-v3`，係正式 STT 模型，endpoint `POST /api/v1/audio/transcriptions`，**base64 JSON body**（非 multipart）：
  ```json
  { "model": "openai/whisper-large-v3",
    "input_audio": { "data": "<base64>", "format": "wav" },
    "language": "en" }
  ```
  Model 頁聲稱支援 word / segment timestamp granularity，但**官方 API 文檔冇寫點攞**，example response 淨係 `{text, usage}`。→ 列為 Phase 0 必驗風險。
- OpenRouter **有** `qwen/qwen3.5-35b-a3b`，即本地 `qwen3.5:35b-a3b-mlx-bf16` 嘅雲端對應。
- 現有 `backend/translation/openrouter_engine.py` 嘅 `OpenRouterTranslationEngine._call_ollama(system, user, temperature) -> str` 簽名**完全符合** output_lang flow 注入嘅 `llm_call` callable，可直接複用。
- 現有設定機制：`settings.json` root-level dict，`ProfileManager._read_settings()` / `_write_settings()`（atomic temp + `os.replace`）；`get_global_font()` / `set_global_font()` 係可跟嘅 flag pattern。
- output_lang ASR 由 `app.py _output_lang_asr_override()`（→ `platform_backend.resolve_asr_override`）+ `whisper_direct_params(output_lang)` 決定；ASR engine 經 `create_asr_engine(asr_cfg)` factory 建立。
- output_lang LLM 由 `app.py _make_ollama_llm_call()` 製造，注入 `crosslang_mt.translate_segments`（MT）同 `output_lang_postprocess.formal_refine`（refiner）。

---

## 3. 架構（方案 A：Flag-gated 注入）

只喺**現有兩個 override 接縫**檢查全局 flag，最小改動、完全跟現有 ABC + Factory + 注入 pattern。

```
settings.json: { "beta_openrouter": true|false }
        │
        ├── _output_lang_asr_override()  ──flag on──▶  {asr:{engine:"openrouter-whisper", model:"openai/whisper-large-v3"}}
        │                                  flag off──▶  現有 platform override (mlx-whisper large-v3)
        │
        └── _make_ollama_llm_call()       ──flag on──▶  OpenRouterTranslationEngine(qwen/qwen3.5-35b-a3b)._call_ollama
                                            flag off──▶  現有 Ollama llm_call
```

`crosslang_mt` / `formal_refine` / output_lang dispatch 全部**零改動** —— 佢哋只係收到一個唔同嘅 `llm_call` / engine config。

### 被否決方案
- **方案 B（Profile-based）**：起個「OpenRouter Beta」Profile activate。否決 —— output_lang 主流程 bypass Profile 嘅 ASR/translation 路由，Profile 覆蓋唔到主流程。
- **方案 C（純 env var 無 UI）**：否決 —— 需求明確要 Admin User 區有 toggle。

---

## 4. 元件

### 4.1 `backend/beta_mode.py`（新，小檔）
集中常數 + API key 管理，避免散落：
- `BETA_ASR_MODEL = "openai/whisper-large-v3"`
- `BETA_LLM_MODEL = "qwen/qwen3.5-35b-a3b"`
- `is_enabled() -> bool` — 經 `ProfileManager.get_beta_mode()` 讀 flag
- `key_status() -> bool` — `bool(os.environ.get("OPENROUTER_API_KEY"))`，**只回 configured/not，唔回顯 key**
- `set_key(key: str) -> None` — 寫入 / 更新 `backend/.env` 嘅 `OPENROUTER_API_KEY`（保留其他行，immutable 改寫），並 `os.environ["OPENROUTER_API_KEY"] = key` 即時生效

### 4.2 `ProfileManager`（`backend/profiles.py`）
- `get_beta_mode() -> bool` — `_read_settings().get("beta_openrouter", False)`
- `set_beta_mode(enabled: bool) -> None` — 讀 → copy + set → `_write_settings`（immutable update）

### 4.3 `backend/asr/openrouter_whisper_engine.py`（新）
`OpenRouterWhisperEngine(ASREngine)`：
- `__init__(config)` — 讀 `OPENROUTER_API_KEY`（缺 → `RuntimeError` 清晰訊息）、base URL、`BETA_ASR_MODEL`
- `transcribe(audio_path, language) -> List[segment]`：
  1. 讀 wav → base64
  2. POST `{base}/api/v1/audio/transcriptions`，body 帶 timestamp 請求參數（Phase 0 實測確定欄位名，例如 `response_format` / `timestamp_granularities`）
  3. 回應 map 返 `[{start, end, text, words:[Word]}]`（精確 mapping 由 Phase 0 回應 shape 落實）
  4. 任何 HTTP / 解析錯誤 → `raise RuntimeError("OpenRouter 轉錄失敗：<原因>")`
- `get_info()` / `get_params_schema()`
- **依賴 Phase 0 結論**：若無 segment timestamp，呢個 engine 唔起（見 §7 gate）

### 4.4 `backend/asr/__init__.py`
- `create_asr_engine` factory 加 `"openrouter-whisper" -> OpenRouterWhisperEngine` mapping

### 4.5 `app.py` 注入點（各加一個 flag 分支）
- `_output_lang_asr_override()`：`beta_mode.is_enabled()` → return `{"asr": {"engine": "openrouter-whisper", "model": BETA_ASR_MODEL, "condition_on_previous_text": False}}`；否則現有 platform override。`whisper_direct_params(output_lang)` 嘅 lang/task 照舊透傳。
- `_make_ollama_llm_call()`：`beta_mode.is_enabled()` → 用 `OpenRouterTranslationEngine({"model": BETA_LLM_MODEL, "api_key": os.environ["OPENROUTER_API_KEY"]})`，return `lambda system, user: eng._call_ollama(system, user, 0.3)`；否則現有 Ollama。

### 4.6 Admin API（`backend/auth/admin.py`，`@admin_required`）
- `GET /api/admin/beta-mode` → `{enabled, key_configured, asr_model: BETA_ASR_MODEL, llm_model: BETA_LLM_MODEL}`
- `PUT /api/admin/beta-mode`，body `{enabled?: bool, api_key?: str}`：
  - 有 `api_key` → `beta_mode.set_key(...)`（空字串 → 400）
  - `enabled=true` 但設定後仍無 key → **400**「請先設定 OpenRouter API key」
  - 成功 → `set_beta_mode(enabled)`，audit `beta.toggle`，return 最新狀態

### 4.7 前端（`frontend/user.html`，admin-only）
- 新 nav `#navBeta`（同 `#navUsers` / `#navAudit` 一樣，`is_admin` 先顯示）+ pane `#pane-beta`：
  - Toggle 開關（綁 `enabled`）
  - API key 輸入（`type=password`、write-only、placeholder 顯示 configured/not、唔回顯舊值）
  - 兩個固定 model id 唯讀顯示（`asr_model` / `llm_model`）
  - 成本提示 + 狀態 + 「儲存」按鈕
  - JS：載入時 GET，儲存時 PUT，錯誤顯示 `{error}`

---

## 5. 失敗行為

全部**硬失敗、唔自動 fallback**：
- OpenRouter ASR / LLM runtime 失敗 → engine `raise RuntimeError` → 傳到 `JobQueue` → job `status='failed'`，`error_msg` 帶原因；前端顯示「OpenRouter 轉錄/翻譯失敗：<原因>」。
- 開 toggle 但 `backend/.env` 無 `OPENROUTER_API_KEY` → `PUT` 即場 **400**，唔准開。

理由：測試模式要讓使用者**睇到雲端真實效果**（含失敗），唔應靜默遮蓋。

---

## 6. 安全

- API key 只寫入 `backend/.env`（已 gitignore），**永不** commit、永不回顯前端。
- `key_status()` 只回 boolean。
- Admin endpoint 全部 `@admin_required`（非 admin → 403）。
- 沿用現有 `_write_settings` atomic 寫法；`.env` 改寫保留其他行。

---

## 7. ⚠️ Validation-First Phase 0（CLAUDE.md 強制 — ASR/MT 改動）

**落 §4.3 ASR engine 同 §4.5 LLM 分支代碼之前**，必須先實測並記錄結果，confirm 之後先進入 plan + 落代碼。

`backend/scripts/validate_openrouter_whisper.py`：
1. 用一段已知測試 clip（同 production stack 對齊），call OpenRouter `openai/whisper-large-v3`，確定：
   - **(必驗)** 回應有冇 **segment-level `{start, end}`** timestamp？用咩請求參數攞到？
   - word-level timestamp 有冇？
   - 回應 JSON 實際 shape（落實 §4.3 mapping）。
2. 轉錄質素 + latency 對比本地 mlx-whisper `large-v3`。
3. （LLM 側）`qwen/qwen3.5-35b-a3b` 經 OpenRouter 做 MT / refine 嘅輸出抽樣 vs 本地 Ollama，confirm register / byte-preservation 一致。
4. 結果寫入 `docs/superpowers/specs/2026-06-07-beta-openrouter-validation-tracker.md`，逐項標 ✅ Validated / ❌ Rejected / ⚠️ Partial。

**Gate**：
- 若 OpenRouter whisper **冇 segment timestamp** → ASR-on-OpenRouter 路徑**唔可行**（output_lang 一定要 per-segment `{start,end}` 砌 cue）。暫停、回 brainstorming 重新決定（例如 Beta 只切 LLM、ASR 留本地）。
- LLM 側（§4.5 後半、§4.6、§4.7、flag 機制）**不受此 gate 阻擋**，可獨立推進。

---

## 8. 測試

**Unit**
- `beta_mode.is_enabled()` / `ProfileManager.get/set_beta_mode` flag round-trip（temp settings.json）
- `beta_mode.set_key` 寫入 / 更新 `.env` 保留其他行（temp file）
- `OpenRouterWhisperEngine` 回應 → segment mapping（mock HTTP，含 timestamp shape）
- factory `create_asr_engine("openrouter-whisper")` 建出 engine
- Admin endpoint：非 admin → 403；開 toggle 無 key → 400；正常 round-trip

**Integration**
- flag 開 → `_make_ollama_llm_call()` return 嘅 callable 行 OpenRouter 路徑（mock）
- flag 開 → `_output_lang_asr_override()` return openrouter-whisper engine config
- flag 關 → 兩者退回現有本地路徑（regression）

> 注意 test-suite isolation：驗 regression 要**單獨跑改到嘅 test file**（full-suite 有已知 order-dependent 失敗）。

---

## 9. 影響檔案清單

| 類別 | 檔案 | 改動 |
|---|---|---|
| 新 | `backend/beta_mode.py` | 常數 + flag + key 管理 |
| 新 | `backend/asr/openrouter_whisper_engine.py` | OpenRouter STT engine |
| 新 | `backend/scripts/validate_openrouter_whisper.py` | Phase 0 驗證 |
| 新 | `docs/superpowers/specs/2026-06-07-beta-openrouter-validation-tracker.md` | 驗證結果 |
| 改 | `backend/profiles.py` | `get/set_beta_mode` |
| 改 | `backend/asr/__init__.py` | factory mapping |
| 改 | `backend/app.py` | 2 個注入點 flag 分支 |
| 改 | `backend/auth/admin.py` | beta-mode GET/PUT |
| 改 | `frontend/user.html` | Beta nav + pane + JS |
| 改 | `backend/config/settings.json` | `beta_openrouter` 預設 false |
| 改 | `CLAUDE.md` / `README.md` / `docs/PRD.md` | 文檔 |
