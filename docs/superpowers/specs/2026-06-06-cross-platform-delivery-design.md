# 跨平台交付架構設計（macOS / Windows-CUDA / NVIDIA GB10）

> **日期**：2026-06-06
> **配對審查文件**：[2026-06-06-cross-platform-delivery-audit.md](2026-06-06-cross-platform-delivery-audit.md)
> **配對計劃文件**：[../plans/2026-06-06-platform-abstraction-layer.md](../plans/2026-06-06-platform-abstraction-layer.md)
> **首批交付範圍**：macOS + Windows（GB10 出設計，pending 真機驗證）
> **離線假設**：有內網可下載（安裝時下載模型；air-gapped 硬性化降為 optional）

---

## 1. 設計目標

1. 同一份 codebase，喺三個平台裝成 server，瀏覽器經 `IP:Port` 連入用返現有 Motitle 全功能。
2. **Mac 行為 byte-identical 不變**（保留 MLX/Metal，現有最佳質量）。
3. Windows / GB10 用 CUDA 後端達到**等價質量**（經 Validation-First 驗證）。
4. 改動面最小、可逐平台獨立驗證、唔破壞現有抽象。

## 2. 核心設計決策

### D1 — Env-driven + 平台自動偵測嘅後端選型（取代硬編碼）

現狀：`app.py:340-344` / `app.py:347-352` / `app.py:3057-3065` 硬編碼 MLX 模型，無分支。

設計：引入一層**後端解析（backend resolution）**，由環境變數驅動、平台自動偵測做預設。新增三個 env：

| Env | 值 | 預設（auto）| 作用 |
|---|---|---|---|
| `R5_ASR_BACKEND` | `auto`/`mlx`/`cuda`/`cpu` | `darwin`→`mlx`；有 NVIDIA→`cuda`；else→`cpu` | 揀 ASR 引擎 + device |
| `R5_OLLAMA_MODEL` | Ollama tag 字串 | `darwin`→`qwen3.5:35b-a3b-mlx-bf16`；else→`qwen3.5:35b-a3b`(GGUF) | 覆寫 LLM tag |
| `R5_OLLAMA_URL` | URL | `http://localhost:11434` | 統一 Ollama endpoint（取代多處硬編碼） |

**點解 env-driven 而唔係純平台偵測**：(a) 可喺 Mac 上用 `R5_ASR_BACKEND=cuda` 行 CPU/CUDA path 嚟寫測試而唔使真 GPU；(b) operator 可覆寫（例如 Mac 想試 GGUF）；(c) auto 預設保證 Mac 零行為改變。

新增純函數模組 `backend/platform_backend.py`：
```
resolve_asr_override(env, platform) -> dict      # 取代 _output_lang_asr_override 內容
resolve_ollama_model(env, platform) -> str       # 取代 model_map 硬編碼
resolve_ollama_url(env) -> str
detect_platform() -> {"os": "darwin|win32|linux", "has_cuda": bool, "arch": "arm64|x86_64"}
```
`app.py` 嘅 `_output_lang_asr_override()` / `_make_ollama_llm_call()` 改為**呼叫呢個模組**，唔再內嵌常數。純函數 → 完全 unit-testable，唔使模型。

### D2 — ASR 引擎策略（跨平台統一喺 ASREngine ABC 後）

| 平台 | engine config | runtime |
|---|---|---|
| macOS | `{engine: "mlx-whisper", model_size: "large-v3", cond=False}` | MLX/Metal（不變） |
| Windows | `{engine: "whisper", device: "cuda", model_size: "large-v3", compute_type: "float16", cond=False}` | faster-whisper/CTranslate2 + CUDA 12 |
| GB10 | `{engine: "whispercpp", device: "cuda", model_size: "large-v3", ...}` | **新引擎**：whisper.cpp-CUDA(sm_121) |

- Windows path 用**現有** `WhisperEngine`（faster-whisper），零新引擎。
- **GB10 需要新 ASR 引擎**（CTranslate2 唔支援 CUDA 13）→ 喺 `backend/asr/` 加 `whispercpp_engine.py` 實作 `ASREngine` ABC（`transcribe` / `get_info` / `get_params_schema`），factory（`asr/__init__.py`）加 mapping。**呢個係 GB10 phase 嘅工作，pending 真機。**
- 三者底層都係 OpenAI large-v3 weights；唯一要驗證：word-timestamp DTW 邊界 drift（<150ms 門檻，§audit 6）。

### D3 — LLM 後端：除 MLX 後綴 + GGUF tag（同一 checkpoint）

- Mac：`qwen3.5:35b-a3b-mlx-bf16`（不變）。
- Windows/GB10：除 `-mlx-bf16` → GGUF/CUDA tag。**確切 tag + quant 由 Phase 0 驗證鎖定**（先 Q4_K_M、退步升 Q8_0）。
- `OllamaTranslationEngine` 已支援任意 `_model`；只需後端解析層注入正確 tag。注入式 `llm_call` pattern 不變 → MT + refiner 自動跟。

### D4 — 平台感知嘅引擎 validation

`asr_profiles.py:22` / `profiles.py:35` 嘅 `VALID_ENGINES` 改為 runtime filter：唔可用嘅引擎（例如 Windows 上嘅 `mlx-whisper`）唔出現喺可選清單 / validation 直接拒。用 `platform_backend.detect_platform()` + 引擎 `*_AVAILABLE` flag。

### D5 — 跨平台路徑修正

| 項 | 現狀 | 設計 |
|---|---|---|
| 第二 venv Python | `…/venv_qwen/bin/python` 硬編碼 | `sysconfig`/OS-aware 構造 + `V6_QWEN_VENV_PYTHON` env 覆寫 |
| ffmpeg 探測 | Windows 有 fallback，mac/Linux 淨靠 PATH | `shutil.which()` + 各平台標準路徑 fallback（brew/apt/winget） |
| whisper cache | `~/.cache/whisper` | 用 `HF_HOME`/平台 cache dir，Windows 唔用 `~/.cache` |

### D6 — 打包 / 服務化（逐平台，首批 Mac+Win）

| 平台 | 打包 | 服務常駐 | 不可用方案（已研究排除） |
|---|---|---|---|
| macOS | venv + 固定 prefix + vendored ffmpeg(arm64,簽名) | launchd LaunchDaemon（app + Ollama, `RunAtLoad`, `0.0.0.0`） | ❌ Docker（Metal 唔過 container）；❌ PyInstaller(torch 凍結爆) |
| Windows | venv + Inno Setup installer | **NSSM** Windows service + firewall rule | ❌ PyInstaller(CUDA 凍結 fail)；❌ gunicorn(Windows 唔支援，用 threading) |
| GB10 | **Docker（NGC aarch64 base）** + NVIDIA Container Toolkit | container restart policy / systemd | ❌ bare-metal pip(CUDA 12/13 衝突)；❌ vLLM NVFP4(GB10 crash) |

### D7 — Flask-SocketIO async mode（逐平台）

- macOS：`gevent`（eventlet 已 maintenance-only）。
- Windows：`async_mode="threading"` + `simple-websocket`（eventlet/gevent Windows wheel 脆；gunicorn 唔支援）。
- GB10：container 內 gevent 或 threading（真機定）。
- 設計：`async_mode` 由 env（`R5_SOCKETIO_ASYNC`）+ 平台預設選，唔再硬編碼。

## 3. Validation-First 整合

D1/D2/D3/D4 全部係 ASR/MT 後端改動 → **必須先過 §audit 6 驗證矩陣**（Windows arm B/C；GB10 arm D pending 真機），結果入 `2026-06-XX-cross-platform-equivalence-validation-tracker.md`，user review 通過先寫 production cutover。

> **關鍵分界**：建立**抽象層 + 單元測試**（D1/D4/D5 純邏輯，mock-based，Mac 行為不變）唔改變任何模型質量，可即做；但**喺 production 啟用 CUDA path**（即 Windows/GB10 真正跑 CUDA 模型出字幕）屬 Validation-First gate，要 evidence。Plan 將兩者分開。

## 4. 檔案結構（首批：抽象層）

```
backend/
  platform_backend.py          [新] 後端解析純函數 + 平台偵測（D1/D2/D3）
  tests/test_platform_backend.py  [新] 純單元測試（無模型）
  app.py                       [改] _output_lang_asr_override / _make_ollama_llm_call 改呼叫 platform_backend
                                     第二 venv 路徑 / cache 路徑修正（D5）
  asr/__init__.py              [改] platform-aware engine availability（D4）
  asr/whisper_engine.py        [改] device validation 對齊平台（D4）
  asr_profiles.py, profiles.py [改] VALID_ENGINES runtime filter（D4）
  translation/ollama_engine.py [改] Ollama URL 用 resolve_ollama_url（D1）
  renderer.py, waveform.py     [改] ffmpeg 探測加 fallback（D5）
  engines/transcribe/qwen3_vad_engine.py [改] venv Python 路徑 OS-aware（D5）
```

## 5. Roadmap（分階段，gate-driven）

| Phase | 內容 | 依賴 / Gate | 首批? | 獨立 plan? |
|---|---|---|---|---|
| **0 驗證** | 跑等價質量矩陣（Win arm B/C），鎖 GGUF tag | — | ✅ | 本 design §audit6；tracker 文件 |
| **1 抽象層** | D1/D4/D5 + Ollama URL env（純邏輯，可 TDD） | 無硬件 | ✅ | **本配對 plan.md（已詳寫）** |
| **2 Windows 打包** | venv+Inno+NSSM+firewall+threading；排除 whisper-streaming；start-win.ps1 | Phase 0 evidence + Phase 1 | ✅ | 到時出 |
| **3 macOS 打包** | launchd LaunchDaemon + 簽名 ffmpeg + .pkg | Phase 1 | ✅ | 到時出 |
| **4 GB10** | 新 whispercpp 引擎 + Docker(NGC) + arm D 驗證 | **GB10 真機** | ⏸ pending | 真機到先出 |
| **5 CI + 衛生** | GitHub Actions matrix + pinned requirements + CDN 本地化(optional) + 刪 old.html | Phase 1-3 | ✅ | 到時出 |

## 6. 風險登記（撮要，全清單見 audit §8）

- 🔴 GB10 ASR（whisper.cpp/WhisperX 均 community-grade）→ 真機驗證前唔交付。
- 🟡 GGUF quant 質量（Q4_K_M 起，Q8_0 兜底）→ Phase 0 鎖定。
- 🟡 模型確切 VRAM/體積數字 → 真機量度，唔入 production 文檔前唔當數。
- 🟡 ARM64 wheel（eventlet/gevent/torch/silero-vad）→ GB10 phase 用 NGC container 解。
- 🟢 Mac 回歸風險低（auto 預設 = 現狀）。
