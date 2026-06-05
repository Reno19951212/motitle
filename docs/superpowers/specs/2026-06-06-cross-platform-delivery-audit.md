# 跨平台交付就緒審查 + 交付計劃（macOS / Windows-CUDA / NVIDIA GB10）

> **日期**：2026-06-06
> **分支 / Worktree**：`worktree-delivery-audit-3platform`（對齊 `feat/glossary-v2` @ `d505b2e`）
> **範圍**：審查 + 交付計劃。**本文件唔包含任何 code 改動。**
> **交付形態**：伺服器式安裝 —— 每個平台裝成一部 server，客戶用瀏覽器經 `http://<server-ip>:<port>` 連入用返現有 Motitle 功能。
> **質量目標**：離開 Mac（Windows / GB10 用 CUDA 模型）後達到**等價質量**（faster-whisper CUDA + Ollama GGUF，經 Validation-First 驗證）。
> **方法**：9 個 parallel 子代理（5 個 read-only 代碼審查 + 4 個上網研究）+ 主代理親自核實關鍵事實。

---

## 0. 執行摘要（Executive Summary）

| 平台 | 整體可行性 | 最大風險 | 一句結論 |
|---|---|---|---|
| **macOS (Apple Silicon)** | 🟢 GREEN | bf16 35B 模型體積/記憶體 | 現狀基本可交付；保留 MLX stack（Metal 最佳質量），缺嘅係 launchd 常駐 + 打包 |
| **Windows x86_64 + NVIDIA** | 🟢/🟡 GREEN-ish | 模型路徑硬編碼未做平台分支；缺 start 腳本/服務化 | 技術路徑成熟（faster-whisper CUDA + Ollama GGUF）；要落 MLX→CUDA 條件分支 + 服務化 |
| **NVIDIA GB10 (DGX Spark, ARM64 + Blackwell)** | 🟡 YELLOW（含 1 個 🔴） | **CTranslate2 唔支援 CUDA 13 / 冇 aarch64 CUDA wheel** | 可行但唔可以照搬；ASR 要換引擎（whisper.cpp / WhisperX），LLM/ffmpeg 綠燈 |

**三個必須拍板嘅核心結論：**

1. **核心關口 = 模型平台耦合，唔係打包。** Primary `output_lang` pipeline 硬編碼咗 Apple-only 嘅 MLX 模型（`app.py:340-344` mlx-whisper、`app.py:347-352`/`3057-3065` Ollama `qwen3.5:35b-a3b-mlx-bf16`），**完全冇平台條件分支**。呢個係令 Windows / GB10 行唔到 primary flow 嘅唯一根本原因。好消息：底層抽象（`ASREngine` ABC + factory、`OllamaTranslationEngine`、注入式 `llm_call`）已經支援多後端，所以**條件化改動面細**（核心只係 2 個函數 + 1 個 model_map）。

2. **GB10 嘅 ASR 係唯一 🔴 紅燈。** `faster-whisper` 依賴 `CTranslate2`，而 CTranslate2 **至今唔支援 CUDA 13**（GB10 Blackwell sm_121 強制要 CUDA 13），亦**冇 aarch64 CUDA wheel**（pip 會靜靜裝 CPU-only build）。LLM（Ollama/llama.cpp）、ffmpeg、PyTorch（經 `cu130` index）喺 GB10 都係綠/黃燈。**解法**：喺現有 `ASREngine` ABC 後面加一個 whisper.cpp-CUDA 或 WhisperX(Blackwell-patched) 引擎，唔好喺 GB10 用 faster-whisper+CUDA。

3. **所有模型改動受 Validation-First Mode 約束。** 換 ASR/LLM 後端 = ASR/MT 改動，按 CLAUDE.md 必須**先做實證驗證**先可以 ship。本計劃內附一份等價質量驗證矩陣（§6），喺寫 production code 之前要先跑。

> **重要更正**：研究子代理對 `qwen3.5:35b-a3b` 嘅模型身份描述前後不一（有一個 pass 自認 hallucinate 成 397B 旗艦）。**對交付計劃而言唯一可靠且可行嘅事實係**：Mac 用嘅係 `-mlx-bf16` (Apple MLX) build；去 CUDA 只需要除咗 `-mlx-bf16` 後綴、改用同一 checkpoint 嘅 GGUF/CUDA quant tag，先驗 Q4_K_M、有 register/詞彙退步先升 Q8_0。確切模型體積 / VRAM 數字屬於「要喺真機量度」嘅 unknown，唔可以照抄研究數字落 production。

---

## 1. 現狀（已經有嘅嘢 — 唔係由零開始）

審查發現呢個 project **已經有部分 cross-platform 底子**，所以呢次係「驗證 + 補洞」而非從頭做起：

**已存在、而且做得啱：**
- `app.py:29-43` — Windows CUDA DLL 註冊（`os.add_dll_directory()` + `PATH` prepend），`sys.platform == "win32"` 正確 gate，並有註解解釋點解兩者都要。**經上網研究確認呢個 pattern 同 2025-2026 upstream 一致（CUDA 12 / cuDNN 9，唔好用 winget CUDA v13）。**
- 四個 setup 腳本齊：`setup.sh`（generic）、`setup-mac.sh`（arm64 + mlx-whisper）、`setup-win.ps1`（CUDA wheels）、`setup-linux-gb10.sh`（aarch64 CUDA wheels）。
- `start.sh`（Unix）+ HTTPS 自簽證書生成 + admin bootstrap + `FLASK_SECRET_KEY` 強制檢查。
- LAN 部署底層 OK：Flask bind `0.0.0.0`（`BIND_HOST` 可覆寫）、CORS/SocketIO 限制 LAN origin（`_LAN_ORIGIN_REGEX`）、前端 API base 用 `''`（相對 URL）、Socket.IO 用 `location.origin` fallback。
- ASR/Translation 引擎抽象（ABC + Factory）已經支援多後端 —— 換後端唔使大改架構。
- registry 原子寫入（tmp + `os.replace()`，跨平台安全）、SQLite WAL mode。

**已存在但有洞 / 未驗證：**
- 模型選型硬編碼 MLX（見 §3，核心問題）。
- `setup-win.ps1` 會喺 `whisper-streaming`（→ `pyalsaaudio` + `opus-fast-mosestokenizer`）build 失敗（ALSA 係 Linux-only / 要 C++ toolchain）—— 已喺 `app.py` import guard，但 setup 腳本未排除。
- **冇 Windows start 腳本**（`setup-win.ps1` 只 provision venv，操作員要手動 activate + `python app.py`）。
- `start.sh` 喺 Windows：browser 唔會自動開（`open`/`xdg-open` 唔存在）、`curl` health check 可能失敗。

**完全冇（交付缺口）：**
- ❌ 冇 Docker / docker-compose（GB10 NVIDIA 官方 container-first，呢個係重大缺口）。
- ❌ 冇 CI/CD（無 `.github/workflows`）。
- ❌ 冇 process supervision：systemd unit（Linux）/ launchd plist（mac）/ Windows service（NSSM）—— server crash 後唔會自動重啟。
- ❌ 冇 pinned requirements（`requirements-freeze.txt`），跨平台重現性差。
- ❌ 冇離線模型分發機制（mlx-whisper / faster-whisper / Ollama 全部首次執行先由網絡下載；air-gapped server 開唔到機）。
- ❌ `~/.cache/whisper` 路徑 Windows 唔啱（Windows 預設冇 `~/.cache`）。

---

## 2. 平台耦合盤點（Top Blockers，含 file:line）

> 完整逐項清單見 §附錄 A。以下係**會阻止交付**嘅項目。

### 🔴 BLOCKER 級

| # | 位置 | 問題 | 影響平台 |
|---|---|---|---|
| B1 | `app.py:340-344` `_output_lang_asr_override()` | 硬編碼 `engine: "mlx-whisper"`，primary flow **所有** ASR 都行呢條，無平台分支 | Windows, GB10 |
| B2 | `app.py:351` + `app.py:3057-3065` model_map | Ollama 模型硬編碼 `qwen3.5:35b-a3b-mlx-bf16`（MLX quant，Apple-only），MT + refiner 共用 | Windows, GB10 |
| B3 | `asr/mlx_whisper_engine.py` | MLX 引擎本身 Apple-only；`mlx-whisper` 喺 Windows/Linux 裝唔到（pip 直接報 no matching platform） | Windows, GB10 |
| B4 | `engines/transcribe/qwen3_vad_engine.py:35` + `app.py:1135` | 第二 venv 的 Python 路徑硬編碼 POSIX `…/venv_qwen/bin/python`（Windows 係 `\Scripts\python.exe`） | Windows |
| B5 | **GB10 ASR runtime** | `CTranslate2` 唔支援 CUDA 13、冇 aarch64 CUDA wheel → faster-whisper+CUDA 喺 GB10 行唔到 | GB10 |

### 🟠 HIGH 級

| # | 位置 | 問題 |
|---|---|---|
| H1 | `asr_profiles.py:22`, `profiles.py:35` | `VALID_ENGINES` 容許 mlx-whisper 喺所有平台選，validation 唔係 platform-aware → 用戶可揀到一個行唔到嘅引擎 |
| H2 | `setup_v6.sh` | 第二 venv 裝 `mlx_qwen3_asr`（Apple-only），喺 Windows/Linux 必然 fail；無 `uname` guard |
| H3 | 依賴 `eventlet` / `gevent` / `silero-vad` / `torch`/`torchaudio` | ARM64-Linux + Blackwell wheel 可用性未驗證；GB10 `torch` 要用 `--index-url .../cu130`（非預設 PyPI） |
| H4 | `requirements.txt` `whisper-streaming` | Windows build fail；setup-win.ps1 未排除 |
| H5 | 缺 Windows start 腳本 + 三平台缺 process supervision | server 唔能可靠常駐 / 開機自啟 / crash 重啟 |
| H6 | `app.py:2122`（`~/.cache/whisper`） | Windows 路徑唔啱，模型 cache 去錯位 |

### 🟡 MEDIUM（前端 / 部署衛生）

- 前端 `proofread.old.html:1006` 硬編碼 `http://localhost:5001`（封存頁，遠端 client 會 fail）→ 交付時刪除或修正。
- `index.html` / `proofread.html` 從 CDN 載 `cdn.socket.io` + Google Fonts → **air-gapped LAN 會靜默失敗**；要本地化 socket.io.min.js + 字型 fallback。
- `font-preview.js:33` 有 `http://localhost:5001` fallback（API_BASE 未定義時遠端 client 字型 fail）。
- `_LAN_ORIGIN_REGEX` 要覆蓋實際部署網段（10.x / 192.168.x / 172.16-31.x）—— 部署前核對。
- Ollama URL 硬編碼 `localhost:11434`（`ollama_engine.py:251` / `app.py:1115`）—— 應改為可由 env（`OLLAMA_HOST`）覆寫，方便將來 Ollama 分離部署。
- 無 HTTPS = 非 secure context：遠端 client 嘅 mic / clipboard / service-worker 等 API 會被瀏覽器封（現有「上載檔案→轉錄」流程唔受影響；如將來加瀏覽器收音先要 TLS）。

---

## 3. 核心架構問題：MLX 耦合 + 最小條件化改動面

Primary `output_lang` pipeline 只用「兩個模型」，全部硬編碼喺 `app.py`：

```
ASR  : _output_lang_asr_override()  → {engine: "mlx-whisper", model_size: "large-v3", cond=False}   (app.py:340-344)
LLM  : _make_ollama_llm_call()      → OllamaTranslationEngine({engine: "qwen3.5-35b-a3b"})           (app.py:347-352)
       model_map: "qwen3.5-35b-a3b" → "qwen3.5:35b-a3b-mlx-bf16"                                      (app.py:3057-3065)
```

**令成條 pipeline 喺 CUDA 行返嘅最小改動面（審查確認，唔使大改架構）：**

1. `_output_lang_asr_override()` 改成平台條件 / env 驅動：
   - Mac → `{engine: "mlx-whisper", model_size: "large-v3", cond=False}`（不變）
   - Windows → `{engine: "whisper", device: "cuda", model_size: "large-v3", compute_type: "float16", cond=False}`
   - GB10 → `{engine: "<whisper.cpp / whisperx 新引擎>", …}`（因為 CTranslate2 紅燈，見 §5）
2. `_make_ollama_llm_call()` / model_map 改成平台條件：
   - Mac → `qwen3.5:35b-a3b-mlx-bf16`（不變）
   - Windows / GB10 → 除 `-mlx-bf16` 後綴、用 GGUF/CUDA quant tag（先 Q4_K_M，必要時 Q8_0）
3. `asr_profiles.py` / `profiles.py` 的引擎 validation 改 platform-aware（runtime filter 唔可用嘅引擎）。
4. 第二 venv Python 路徑（`qwen3_vad_engine.py:35`、`app.py:1135`）改用 `sysconfig` / OS-aware 構造 + env 覆寫。

**建議實作方式：env-driven + 平台自動偵測**（最靈活、最易驗證、唔會喺 Mac 改變現有行為）：
```
R5_ASR_BACKEND   = auto | mlx | cuda | cpu        # 預設 auto：darwin→mlx，else→cuda(有GPU)/cpu
R5_OLLAMA_MODEL  = <覆寫 Ollama tag>              # 預設按平台選 mlx-bf16 / gguf
R5_OLLAMA_URL    = http://localhost:11434         # 已部分支援，統一成 env
```
> ⚠️ 第 1、2、3 點全部落入 **Validation-First 範圍**（改 ASR/MT 後端）。必須先跑 §6 驗證矩陣、過 user review，先可以寫 production code。

---

## 4. 逐平台交付方案（研究結論 + 引用）

### 4.1 macOS（Apple Silicon）🟢

- **打包**：原生 venv + launchd（**唔好用 Docker** — Apple Silicon 嘅 Metal GPU 唔會 pass 入 container，MLX/Ollama 會跌返 CPU，對 large-v3 + 35B 不可用）。可用 Homebrew bootstrap `python@3.11` / `ffmpeg` / `ollama`，再喺固定 prefix 起 venv。
- **Ollama**：`brew install ollama` 或官方 app；要 headless 開機自啟用 **LaunchDaemon**（`/Library/LaunchDaemons`, `RunAtLoad=true`, `OLLAMA_HOST=0.0.0.0:11434`）。參考 `anurmatov/mac-studio-server`。
- **ffmpeg**：evermeet **只出 Intel**，要用 arm64 source（martin-riedl.de / ssut / OSXExperts）；codesign + notarize；`--enable-gpl` build 係 GPLv2+，redistribute 要附 source/notice（或改 LGPL build）。
- **Flask-SocketIO**：用 **gevent**（eventlet 已 maintenance-only）；`gunicorn -k gevent -w 1 --bind 0.0.0.0:5001`；wrap 入 LaunchDaemon。
- **服務常駐**：Mac 唔可以瞓（`caffeinate` / 防睡眠）；首次監聽會彈 firewall prompt（codesign launcher 可免）。
- **模型**：mlx-whisper 由 HF 下載 cache 去 `~/.cache/huggingface/hub`；air-gapped 要預載 cache + `HF_HUB_OFFLINE=1`。**bf16 35B tag 體積大、要大 unified memory** —— 確切數字屬要量度嘅 unknown；記憶體緊就改 quantized tag。

### 4.2 Windows（x86_64 + NVIDIA CUDA）🟢/🟡

- **打包**：venv + **NSSM**（host Python 成 Windows service，`sc.exe` 唔夠）+ **Inno Setup** installer。**唔好 PyInstaller**（torch/CUDA 凍結成 multi-GB、GPU 偵測常 fail）；Docker+WSL2 GPU 可行但對單機 server 過重。
- **faster-whisper / CTranslate2**：`ctranslate2 4.x` 要 **CUDA 12 + cuDNN 9**（DLL `cublas64_12.dll` / `cudnn64_9.dll`）。pip recipe：`faster-whisper` + `nvidia-cublas-cu12==12.4.5.8 nvidia-cudnn-cu12`（cuDNN 9.x）+ `torch --index-url .../cu124`。**唔好裝 winget `Nvidia.CUDA`（v13，DLL 改名 `cublas64_13`，唔滿足 ct2）。** app.py:29-43 已正確處理 DLL 註冊。
- **Ollama**：官方 `OllamaSetup.exe`（背景服務）；driver ≥ 452.39（建議裝最新 Studio/Game Ready）；`ollama pull` 一個 GGUF tag（除 `-mlx-bf16`）。
- **Flask-SocketIO**：用 **`async_mode="threading"` + `simple-websocket`**（Windows 上 eventlet/gevent wheel 最脆弱；`gunicorn` Windows 唔支援，要用 waitress/threading）。
- **Firewall**：`New-NetFirewallRule … -LocalPort 5001 -Action Allow -Profile Private`（installer 自動加）。
- **ffmpeg**：bundle Gyan.dev static build（GPLv3，附 notice）。

### 4.3 NVIDIA GB10 / DGX Spark（ARM64 Linux + Blackwell）🟡（含 🔴 ASR）

- **平台事實**：aarch64 Grace CPU + Blackwell GPU（**sm_121**，與 sm_120 binary-compatible）、128GB 統一記憶體、**DGX OS 7（Ubuntu 24.04 aarch64）**、**預設 CUDA 13**、driver R580。NVIDIA **container-first**。
- **唯一根本制約**：平台係 **CUDA 13 + sm_121**，主流 pip wheel 多數 target CUDA 12.x，喺呢部機 `libcudart.so.12` load fail。
- **逐組件風險**：

| 組件 | 風險 | 結論 |
|---|---|---|
| OS / CUDA 13 / aarch64 base | 🟢 | 出廠即備 |
| ffmpeg | 🟢 | `apt install ffmpeg`（CPU encoder x264/ProRes 不受影響） |
| Ollama + qwen3.5:35b-a3b (GGUF) | 🟢 | 官方 aarch64 binary，GPU 行；要除 MLX tag；建議 `--no-mmap` + q8_0 KV cache |
| PyTorch CUDA | 🟡 | 要用 `--index-url https://download.pytorch.org/whl/cu130` 或 NGC container（非預設 PyPI） |
| **faster-whisper / CTranslate2 CUDA** | 🔴 | **冇 aarch64 CUDA wheel + 唔支援 CUDA 13** → 必須換 ASR 引擎 |
| vLLM（NVFP4） | 🔴 | qwen3.5 NVFP4 喺 GB10 crash（illegal-instruction）→ 避免，用 Ollama/llama.cpp GGUF |

- **建議交付**：**Docker + NVIDIA Container Toolkit**，single image `FROM` NGC aarch64 PyTorch base（CUDA 13 / Blackwell-built）+ in-container Ollama（aarch64 binary, GGUF tag）+ **新 ASR 引擎（whisper.cpp-CUDA 或 WhisperX Blackwell-patched，build for sm_121）** + `apt ffmpeg` + Flask app。`--gpus all` 跑、publish LAN port。
- **必須喺真機驗證嘅 unknown**：見 §8。

---

## 5. ASR 引擎策略（跨平台統一抽象）

| 平台 | 建議 ASR 後端 | 狀態 |
|---|---|---|
| macOS | `mlx-whisper large-v3`（Metal） | 現狀，保留 |
| Windows | `faster-whisper large-v3` `compute_type=float16`（CUDA） | 成熟，同 OpenAI 原 weights，等價 |
| GB10 | **`whisper.cpp`-CUDA(sm_121) 或 WhisperX(Blackwell-patched)**，行喺 `ASREngine` ABC 後 | 要新引擎 + 真機驗證 |

**重點**：三者**底層都係 OpenAI Whisper large-v3 weights**，純粹 runtime 唔同（MLX/Metal vs CTranslate2/CUDA vs whisper.cpp/ggml）。文字輸出近乎一致；唯一要驗證嘅係 **DTW word-timestamp 邊界可能有 <100ms drift**（app 用 word_timestamps）。GB10 加新引擎本身就係 ASR 改動 → 受 Validation-First 約束。

---

## 6. 模型等價質量驗證矩陣（Validation-First，落 code 前必跑）

固定輸入：每個 source family（`yue`/`cmn`/`en`/`ja`）一條 clip、同一 glossary、`mt_style` 跑 `racing` + `generic`、同一 `script`。**只變平台**。

| Arm | ASR | LLM |
|---|---|---|
| A（Mac 基準） | mlx-whisper large-v3 | qwen3.5:35b-a3b-mlx-bf16 |
| B（CUDA 預設） | faster-whisper large-v3 fp16 | qwen3.5:35b-a3b **Q4_K_M** |
| C（CUDA 高保真，B 退步先跑） | faster-whisper large-v3 fp16 | qwen3.5:35b-a3b **Q8_0** |
| D（GB10 ASR） | whisper.cpp/WhisperX sm_121 | （同 B/C） |

**量度指標（沿用現有 tracker 欄位 + 2 個獨立 judge model + live 3-flow 整合）：**

| 指標 | 量度方法 | 等價門檻 |
|---|---|---|
| ASR 文字 CER | B/C vs A（Mac 為 reference），逐 source lang | CER ≤ 1% delta |
| Word-timestamp drift | B vs A 邊界 |Δ| | mean < 50ms, max < 150ms |
| Char distribution | 逐 cue 字數直方圖（現有 line-wrap metric） | KS-test n.s.；無新增 `[LONG]`(>28字/行) |
| Meaning-error rate | 2 judge model 逐 cue 評（沿用 2026-06-04 yue-base 77%→33% rubric） | major-error 與 Mac 差 ±5pp 內 |
| Register 正確度 | judge 評 書面語/口語 register | ≥ Mac pass rate；`generic` 無 racing-register 滲漏 |
| Glossary follow rate | 現有 `glossary-scan` string match | delta ≤ 2pp |
| Hallucination rate | 現有 heuristic(>40字) + judge | 不增 |
| 專名 byte 保留 | 名/地/英文/數字 vs source | 保留數一致 |

**程序**：A+B 同 4 clip 跑 live `output_lang` → judge 盲評 B-vs-A → 任何指標超門檻先跑 C 重評 → 結果寫入 `docs/superpowers/specs/2026-06-XX-cross-platform-equivalence-validation-tracker.md`（✅/⚠️/❌）。GB10 用真機跑 Arm D。

---

## 7. 分階段交付計劃

> 每階段結尾過 CLAUDE.md 4 個 Verification Gate；模型相關階段先過 §6 驗證。

**Phase 0 — 驗證 + 設計鎖定（先唔落 production code）**
- 跑 §6 驗證矩陣（Windows arm B/C；如有 GB10 真機跑 arm D）。
- 確認 GGUF tag + compute_type，記入 validation tracker。
- 產出 design.md + plan.md pair（CLAUDE.md 慣例）。
- **Gate**：user review 通過。

**Phase 1 — 平台抽象層（落 code 起點）**
- `_output_lang_asr_override()` / `_make_ollama_llm_call()` / model_map 改 env-driven + 平台偵測（§3）。
- 引擎 validation 改 platform-aware（H1）。
- 第二 venv Python 路徑 OS-aware（B4/H2）。
- ffmpeg / `~/.cache` 路徑跨平台 fallback（H6）。
- Ollama URL env 化。
- **Gate**：Mac 行為 byte-identical（regression 驗證）；pytest 全綠。

**Phase 2 — GB10 ASR 引擎**
- 喺 `ASREngine` ABC 後加 whisper.cpp-CUDA / WhisperX 引擎；GB10 真機驗 §6 arm D。
- **Gate**：GB10 端到端轉錄質量 + GPU 利用率達標。

**Phase 3 — 打包 + 服務化（逐平台）**
- mac：launchd LaunchDaemon（app + Ollama）、ffmpeg 簽名 notarize、`.pkg`/簽名腳本。
- win：`start-win.ps1` + NSSM service + Inno Setup installer + firewall rule；setup 排除 `whisper-streaming`。
- GB10：Dockerfile（NGC aarch64 base）+ NVIDIA Container Toolkit + compose；或 bare-metal + systemd unit。
- pinned `requirements-*.txt`（逐平台）。
- **Gate**：三平台乾淨機 install→開機自啟→LAN client 連入成功。

**Phase 4 — 離線 / air-gapped + 衛生**
- 模型預載工具（HF cache + `ollama pull` 預打包）+ offline flags。
- 本地化 socket.io.min.js + 字型；刪 `proofread.old.html`。
- `_LAN_ORIGIN_REGEX` 覆蓋實際網段；`.env.example` + 文檔。
- **Gate**：air-gapped LAN 全功能通過。

**Phase 5 — CI + 文檔**
- GitHub Actions：pytest（多平台 matrix，pure-unit 至少）+ Playwright headless。
- 更新 CLAUDE.md / README.md（繁體）/ PRD.md + design/plan/validation tracker。
- **Gate**：CI 綠；4 個 Verification Gate 全過。

---

## 8. 必須喺真機驗證嘅 Unknowns（GB10 為主）

1. **GB10 ASR on Blackwell（#1 unknown）**：whisper.cpp-CUDA 同 WhisperX「Blackwell bridge」都係 community/early-adopter，未有官方穩定方案。WhisperX 內部仍用 CTranslate2，要確認 Hopper-spoof 喺轉錄（唔淨止 diarization）path 成立。
2. **CTranslate2-from-source on CUDA 13/sm_121**：所有已知 recipe pin CUDA 12.6，是否能 build/run 喺 CUDA 13 + R580 未驗證 → 唔好假設可行。
3. **確切 qwen3.5 GGUF quant + throughput**：要量度你嘅 refiner+MT workload（長 context、q8_0 KV），唔好照抄 benchmark 數。
4. **torchaudio CUDA on Blackwell**：若選用嘅 ASR path 拉 torchaudio CUDA kernel，sm_121 Jiterator bug 可能中招。
5. **Ollama GPU 確認**：DGX 有 cosmetic「no GPU detected」preflight 訊息 → 要 `ollama ps` 實證 GPU offload。
6. **統一記憶體 contention**：Whisper + 35B + ffmpeg 共用 128GB 無離散 VRAM 邊界，要量峰值。
7. **模型確切體積 / VRAM**（全平台）：研究數字前後不一，全部要真機量度先入 production 文檔。
8. **eventlet/gevent/silero-vad/torch ARM64 wheel**：GB10 上逐個確認（傾向 NGC container 解決）。

---

## 9. 需要你拍板嘅決策

1. **GB10 交付路線**：Docker(NGC) container（建議，NVIDIA 官方方向、隔離 CUDA 13 風險）vs bare-metal + systemd？
2. **GB10 ASR 引擎**：whisper.cpp-CUDA vs WhisperX(Blackwell-patched)？（兩者都要真機驗，建議 whisper.cpp，同 LLM 共用 toolchain、風險較低）
3. **有冇 GB10 真機可以做 Phase 0/2 驗證**？冇嘅話，GB10 要標為「pending hardware validation」，先交付 Mac + Windows。
4. **離線 / air-gapped 要求**：客戶 server 係咪要無網絡運行？（影響模型預載 + CDN 本地化工作量）
5. **質量 quant 起步**：Q4_K_M 起（省 VRAM）定直接 Q8_0（更貼 bf16，要更多 VRAM）？
6. **本次到此為止（審查+計劃）**：確認後我先出 design.md + plan.md pair，等你 review 先入 Phase 1 code。

---

## 附錄 A — 完整平台耦合清單（節錄；逐項 file:line 已記於子代理報告）

**Apple/MLX 耦合**：`asr/mlx_whisper_engine.py`（整個引擎）、`app.py:340-344`（asr override）、`app.py:351`+`3057-3065`（ollama model）、`asr_profiles.py:22` / `profiles.py:35`（VALID_ENGINES）、`setup-mac.sh:23`、`setup_v6.sh:37-40`（mlx_qwen3_asr）。

**OS-specific / 路徑**：`qwen3_vad_engine.py:35` + `app.py:1135`（venv `/bin/python`）、`renderer.py:238-246`（Windows ffmpeg fallback，mac/Linux 無 fallback）、`renderer.py:306`（`NUL`/`/dev/null`）、`app.py:2122`（`~/.cache/whisper`）。

**依賴可移植性**：`whisper-streaming`（Windows build fail）、`eventlet`/`gevent`/`gevent-websocket`（ARM64 wheel 未驗）、`torch`/`torchaudio`（GB10 要 cu130 index/NGC）、`silero-vad`（ARM64 未驗）、`soundfile`（libsndfile 系統庫）、`mlx-whisper`/`mlx_qwen3_asr`（Apple-only）。

**網絡 / 前端**：`proofread.old.html:1006`（localhost 硬編碼）、`font-preview.js:33`（localhost fallback）、`cdn.socket.io` + Google Fonts CDN（air-gapped fail）、`ollama_engine.py:251`/`app.py:1115`（Ollama localhost 硬編碼）、`_LAN_ORIGIN_REGEX` 要核網段。

**打包 / 運維缺口**：無 Docker、無 CI、無 systemd/launchd/NSSM、無 Windows start 腳本、無 pinned requirements、無離線模型分發、registry.json 無 file-lock（單進程假設）。

---

*本文件由 9 個 parallel 子代理（5 代碼審查 + 4 上網研究，含完整 URL 引用）綜合 + 主代理親自核實關鍵 file:line 而成。所有上網研究嘅 URL 引用保存喺各子代理原始報告。本文件唔包含任何 code 改動。*
