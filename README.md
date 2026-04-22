# 🎙 MoTitle — 廣播字幕製作系統

基於 [OpenAI Whisper](https://github.com/openai/whisper) 及本地 AI 翻譯模型嘅專業字幕製作工具。將英文影片自動轉錄、翻譯為**繁體中文（粵語/書面語）**字幕，經人工校對後燒入影片輸出。

---

## 功能特點

| 功能 | 說明 |
|------|------|
| 📁 **文件上傳與管理** | 拖放或選擇影片/音頻，支援 MP4、MOV、AVI、MKV、WebM、MXF 等格式 |
| 🤖 **英文語音轉錄** | Whisper ASR 自動將英文語音轉為英文文字（支援 faster-whisper 加速，以及 Apple Silicon 嘅 MLX-Whisper） |
| 🌐 **中文翻譯** | 三種選擇：本地 Ollama + Qwen2.5/3.5、Ollama Cloud、或 **OpenRouter**（Claude / GPT-4o / Gemini / DeepSeek 等 9 款 frontier models，用戶可自訂任何 OpenRouter model id） |
| 🎯 **翻譯質素調校** | 四種模式：傳統 batch → sentence pipeline → LLM-anchored alignment → 兩次 pass enrichment。詳見「翻譯質素調校」章節 |
| 📖 **術語表管理** | 自訂英中術語對照表，確保專業名詞翻譯一致（支援 CSV 匯入/匯出、一鍵 LLM 智能替換） |
| ⚙️ **Profile 配置** | 可切換不同 ASR + 翻譯引擎組合，適應開發/生產環境 |
| 🌐 **語言參數配置** | 每種語言獨立設定 ASR 分段參數（每句最大字數/時長）及翻譯參數（batch size/temperature） |
| ✏️ **字幕校對編輯器** | 獨立校對頁面，左右並排影片與字幕表格，逐句審核、編輯、批核 |
| 🎬 **燒入字幕輸出** | 將已批核字幕燒入影片，可調整編碼參數後輸出：**MP4** (H.264，支援 CRF / CBR / 2-pass 三種 bitrate mode、yuv420p/422p/444p、H.264 Profile & Level)、MXF (ProRes)、或 MXF · **XDCAM HD 422**（MPEG-2 4:2:2，碼率 10–100 Mbps 自由調校）。渲染完成後可經系統級「另存為」對話框揀下載位置。 |
| 📊 **轉錄進度條** | 轉錄時顯示進度百分比、已處理/總時長、預計剩餘時間 |
| ⚡ **雙引擎支援** | 自動選用 faster-whisper（快 4–8 倍）或 openai-whisper |
| 💾 **字幕導出** | 每個文件獨立提供 SRT、VTT、TXT 下載 |

---

## 系統需求

- **Python** 3.8 或以上（推薦 3.11）
- **FFmpeg**（用於從影片提取音頻及燒入字幕）
- **Ollama**（本地 LLM 翻譯引擎）— [下載](https://ollama.com/download)
- **pip**（Python 套件管理工具）
- 現代瀏覽器（Chrome / Firefox / Safari / Edge）

### Windows 安裝 Python + FFmpeg

Windows 預設**冇**安裝 Python（PATH 入面嘅 `python` 只係 Microsoft Store 嘅 stub），亦冇 FFmpeg。建議透過 `winget` 一次過安裝：

```powershell
winget install --id Python.Python.3.11 -e --source winget
winget install --id Gyan.FFmpeg -e --source winget
```

安裝後請重啟 shell（或登出再登入）令 PATH 生效，再執行 `python --version` 同 `ffmpeg -version` 確認。

#### Windows 常見問題

**1. `pip install -r requirements.txt` build 失敗（`pyalsaaudio` / `opus-fast-mosestokenizer`）**

`whisper-streaming` 依賴 `pyalsaaudio`（Linux-only ALSA）及 `opus-fast-mosestokenizer`（需 C++ 編譯環境），兩者喺 Windows 會 build 失敗。由於 v2.0 已移除串流模式（`app.py` 嘅 import 有 `try/except` 保護），可以**跳過**此依賴，改為直接安裝其餘套件：

```bash
source backend/venv/Scripts/activate
pip install openai-whisper faster-whisper flask flask-cors flask-socketio \
  werkzeug eventlet numpy torch torchaudio ffmpeg-python python-socketio \
  gevent gevent-websocket pysbd opencc-python-reimplemented librosa soundfile
```

**2. 轉錄失敗：`Library cublas64_12.dll is not found or cannot be loaded`**

當系統有 NVIDIA 顯示驅動但**未裝 CUDA runtime libraries**，`faster-whisper`（靠 `ctranslate2`）嘅 `device: "auto"` 會偵測到 GPU 並嘗試載入 CUDA 12 libs（`cublas64_12.dll` / `cudnn64_9.dll`），但搵唔到就報呢個錯。三條解法揀一：

- **🚀 路線 A（推薦 GPU）—— 用 pip 裝 CUDA runtime**：唔需要成個 CUDA Toolkit（3GB+），只需要兩個 pip package（約 1GB），裝完 backend 會自動於啟動時 register DLL path。
  ```bash
  source backend/venv/Scripts/activate     # Windows Git Bash
  pip install nvidia-cublas-cu12==12.4.5.8 nvidia-cudnn-cu12
  ```
  Profile 嘅 `device` 保持 `auto` 即可，重啟 `python backend/app.py` 後 log 應該 print `[cuda-dll] registered 2 NVIDIA DLL path(s) for GPU acceleration`。如果冇呢行 log 或見到 `[cuda-dll] skipped DLL path registration: ...`，代表兩個 pip package 冇裝或 venv 唔啱，重覆 pip install 指令。

- **💻 路線 B（純 CPU，最穩陣）—— 強制 Profile device=cpu**：
  ```bash
  curl -X PATCH http://127.0.0.1:5001/api/profiles/<profile_id> \
    -H "Content-Type: application/json" \
    -d '{"asr":{"engine":"whisper","model_size":"small","language":"en","device":"cpu","condition_on_previous_text":true,"vad_filter":true,"language_config_id":"en"}}'
  ```
  或者前端 Profile 編輯表單將「Device」由 `auto` 改 `cpu`，再重啟 backend。

- **🛠 路線 C（完整系統級 CUDA Toolkit）**：去 [NVIDIA 下載頁](https://developer.nvidia.com/cuda-12-4-0-download-archive) 下載 CUDA Toolkit 12.4（**唔好用 winget 嘅 v13**，DLL 文件名唔匹配），加埋 cuDNN 9.x。安裝後 `cublas64_12.dll` 會喺 `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin`，已經喺系統 PATH。

> **診斷 tips**：backend 啟動時 print `faster-whisper available — will use for live transcription` 之後，如果見到 `[cuda-dll] skipped DLL path registration` 就代表走咗 fallback；如果冇呢行錯誤，但仍然 crash，多數係版本夾唔 match（ctranslate2 4.7 對應 CUDA 12 + cuDNN 9；CUDA 13 會唔 work）。

### macOS / Linux

- macOS：`brew install python@3.11 ffmpeg`
- Ubuntu/Debian：`sudo apt-get install python3 python3-venv ffmpeg`

---

## 快速開始

### 第一步：安裝

```bash
./setup.sh
```

安裝腳本會自動：
- 檢查 Python 3 及 FFmpeg 是否已安裝（**請先完成「系統需求」章節嘅安裝步驟**）
- 建立 Python 虛擬環境（`backend/venv/`）
- 安裝所有 Python 依賴套件

> **Windows 提示**：`whisper-streaming` 依賴 `pyalsaaudio`（Linux-only）及 `opus-fast-mosestokenizer`（需要 C++ 編譯環境），兩者喺 Windows 會 build 失敗。由於 v2.0 已移除串流模式，此依賴屬**選用**，可直接 `pip install -r requirements.txt` 失敗之後手動安裝其餘套件（或使用 `requirements.txt` 不含 `whisper-streaming` 嘅版本）。

### 第二步：安裝 Ollama 及翻譯模型

```bash
# 安裝 Ollama（macOS）
# 從 https://ollama.com/download 下載安裝

# 下載翻譯模型
ollama pull qwen2.5:3b
```

### 第三步：啟動

```bash
./start.sh
```

啟動腳本會：
1. 啟動後端服務器（`http://localhost:5001`）
2. 預加載 Whisper small 模型
3. 自動在瀏覽器打開前端頁面

按 `Ctrl+C` 停止服務器。

---

## 使用流程

### 1. 選擇 Profile

在右側「設置」面板嘅「Pipeline Profile」下拉選單中選擇配置：
- **Development** — Whisper tiny + Mock 翻譯（開發測試用）
- **Broadcast Production** — Whisper + Qwen2.5 翻譯（正式使用）

可直接喺側邊欄 Profile 管理介面**建立、編輯、刪除** Profile，或按下「＋ New Profile」按鈕建立新配置。點擊任何 Profile 列表行可立即激活該 Profile（綠點指示）。

- **引擎選擇**：編輯 Profile 時，ASR 和翻譯引擎選單會從後端動態載入，顯示每個引擎的可用狀態（綠點 = 可用、灰點 = 不可用）。切換引擎後，對應的參數欄位會自動更新。

### 2. 上傳英文影片

- 拖放影片至上傳區域，或點擊選擇文件
- 支援格式：MP4、MOV、AVI、MKV、WebM、MXF、MP3、WAV 等
- 點擊「🚀 上傳並轉錄」

### 3. 自動轉錄 + 翻譯

- 系統自動進行英文語音轉錄
- 轉錄完成後自動觸發中文翻譯
- 右側轉錄面板會顯示翻譯後嘅中文字幕
- 播放影片時字幕會同步顯示

### 4. 校對字幕

- 文件卡片上會出現紫色「**校對**」按鈕
- 點擊進入校對編輯器（`proofread.html`）
- 左邊播放影片，右邊逐句審核翻譯
- 可直接編輯中文翻譯，按 Enter 儲存並批核
- 「批核所有未改動」可一次批核所有未修改嘅句子

**鍵盤快捷鍵：**
| 按鍵 | 功能 |
|------|------|
| ↑↓ | 切換段落 |
| Enter | 批核當前段落 |
| E | 編輯翻譯 |
| Esc | 取消編輯 |
| Space | 播放/暫停影片 |

### 5. 燒入字幕輸出

- 所有段落批核完成後，「匯出燒入字幕」按鈕啟用
- 點擊按鈕後，會開啟**渲染設定 Modal**，可在此選擇格式及調整編碼參數：

**MP4 (H.264) 選項：**
| 參數 | 說明 | 預設值 |
|------|------|--------|
| 畫質 (CRF) | 0–51，數值越低畫質越高 | 18 |
| 編碼速度 | ultrafast → veryslow，越慢壓縮率越高 | medium |
| 音頻碼率 | 64k / 96k / 128k / 192k / 256k / 320k | 192k |
| 輸出解像度 | 720p / 1080p / 1440p / 4K（空白保留原始） | 原始 |

**MXF (ProRes) 選項：**
| 參數 | 說明 | 預設值 |
|------|------|--------|
| ProRes 規格 | Proxy (~45 Mbps) / LT (~102 Mbps) / Standard (~147 Mbps) / **HQ (~220 Mbps)** / 4444 / 4444 XQ | HQ |
| 音頻位深 | 16-bit PCM / **24-bit PCM（廣播標準）** / 32-bit PCM | 16-bit PCM |
| 輸出解像度 | 720p / 1080p / 1440p / 4K（空白保留原始） | 原始 |

- 確認設定後開始渲染，渲染期間顯示進度，完成後自動下載

---

## 系統架構

### 整體 Pipeline 流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (Frontend)                           │
│                                                                  │
│  index.html                              proofread.html          │
│  ┌──────────────────────┐                ┌────────────────────┐  │
│  │ 📁 上傳影片           │                │ ✏️ 校對編輯器       │  │
│  │ ⚙️ Profile / 語言配置 │                │ 📹 影片 + 字幕表格  │  │
│  │ 📖 術語表管理         │                │ ✅ 逐句批核         │  │
│  │ 📄 轉錄 + 翻譯預覽   │──── 校對 ────▶│ 🎬 燒入字幕輸出     │  │
│  └──────────┬───────────┘                └─────────┬──────────┘  │
│             │ REST API + WebSocket                  │ REST API    │
└─────────────┼───────────────────────────────────────┼────────────┘
              │                                       │
              ▼                                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                     後端 (Flask + SocketIO)                       │
│                                                                  │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌───────────┐  │
│  │ Profile  │    │ Glossary │    │ Language  │    │   File    │  │
│  │ Manager  │    │ Manager  │    │  Config   │    │ Registry  │  │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘    └─────┬─────┘  │
│       │               │               │                │         │
│       ▼               ▼               ▼                ▼         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    轉錄 + 翻譯 Pipeline                    │   │
│  │                                                           │   │
│  │  1. FFmpeg 音頻提取 (MP4/MXF → 16kHz WAV)                │   │
│  │              │                                            │   │
│  │              ▼                                            │   │
│  │  2. ASR 引擎 (英文語音 → 英文文字段落)                     │   │
│  │     ┌─────────────┬──────────────┬──────────────┐        │   │
│  │     │ Whisper     │ Qwen3-ASR   │ FLG-ASR      │        │   │
│  │     │ (完整實現)   │ (stub)      │ (stub)       │        │   │
│  │     │ tiny/base/  │ 生產環境     │ 生產環境      │        │   │
│  │     │ small/medium│ 大型模型     │ 快速引擎      │        │   │
│  │     │ /large/turbo│              │              │        │   │
│  │     └─────────────┴──────────────┴──────────────┘        │   │
│  │              │                                            │   │
│  │              ▼                                            │   │
│  │  3. 段落後處理 (split_segments)                            │   │
│  │     按 max_words / max_duration 分割過長段落               │   │
│  │              │                                            │   │
│  │              ▼                                            │   │
│  │  4. 翻譯引擎 (英文文字 → 繁體中文)                         │   │
│  │     ┌──────────────────────┬──────────────┐              │   │
│  │     │ Ollama + Qwen2.5    │ Mock Engine   │              │   │
│  │     │ (本地 LLM 翻譯)      │ (開發測試)    │              │   │
│  │     │ 3B / 7B / 72B       │ [EN→ZH] 格式  │              │   │
│  │     │ 書面語 / 粵語口語    │              │              │   │
│  │     │ + 術語表注入         │              │              │   │
│  │     └──────────────────────┴──────────────┘              │   │
│  │              │                                            │   │
│  │              ▼                                            │   │
│  │  5. 翻譯結果儲存 → WebSocket 通知前端                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    字幕渲染 Pipeline                        │   │
│  │                                                           │   │
│  │  已批核翻譯 → ASS 字幕生成 → FFmpeg 燒入                  │   │
│  │  MP4：CRF / preset / 音頻碼率 / 解像度 可調              │   │
│  │  MXF：ProRes profile / 音頻位深 / 解像度 可調             │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### AI 模型配置

系統透過 **Profile** 統一管理 AI 模型組合。每個 Profile 指定 ASR 引擎 + 翻譯引擎 + 字體配置：

| Profile | ASR 引擎 | 翻譯引擎 | 用途 |
|---------|----------|----------|------|
| **Development** | Whisper tiny | Mock | 開發測試，無需 GPU |
| **Broadcast Production** | Whisper / Qwen3-ASR | Ollama Qwen2.5 | 正式製作 |

#### ASR 引擎

| 引擎 | 狀態 | 模型 | 說明 |
|------|------|------|------|
| **Whisper** | ✅ 完整實現 | tiny / base / small / medium / large / turbo | OpenAI 開源語音辨識，支援 faster-whisper 加速 |
| **Qwen3-ASR** | 🔧 Stub | — | 生產環境大型模型（待實現） |
| **FLG-ASR** | 🔧 Stub | — | 生產環境快速引擎（待實現） |

#### 翻譯引擎

| 引擎 | 狀態 | 模型 | 說明 |
|------|------|------|------|
| **Ollama** | ✅ 完整實現 | qwen2.5:3b / 7b / 72b | 本地 LLM，支援書面語及粵語風格 |
| **Ollama Cloud** | ✅ 完整實現 | glm-4.6 / qwen3.5-397b / gpt-oss-120b | 雲端 MoE，需 `ollama signin` |
| **OpenRouter** | ✅ 完整實現 | Claude / GPT-4o / Gemini / DeepSeek 等 | OpenAI-compatible proxy，自備 API key |
| **Mock** | ✅ 測試用 | — | 返回 `[EN→ZH]` 格式，用於開發測試 |

### Ollama Cloud 模型（選用）

系統支援三個 Ollama Cloud 雲端模型，提供更高質素嘅翻譯結果：

| 模型 | 用途 |
|---|---|
| `glm-4.6-cloud` | 通用中英翻譯，198K context，響應快 |
| `qwen3.5-397b-cloud` | Qwen 最大 MoE（397B），256K context，粵語翻譯質素最高 |
| `gpt-oss-120b-cloud` | OpenAI 開源 MoE 120B，128K context |

使用前需要先登入 Ollama Cloud（付費服務）：

```bash
ollama signin
```

登入之後，雲端模型會自動出現喺 Profile 翻譯引擎選單嘅「雲端模型」組別，唔需要 `ollama pull`。如果未 signin，選項會顯示 `⚠` 加 tooltip 提示。

### OpenRouter 模型（選用）

如果想用 Claude / GPT / Gemini 等 frontier models 做翻譯，可以用 OpenRouter — 一個統一 API gateway，唔使分別註冊每間 provider。

**第一步：攞 API key**
1. 去 [openrouter.ai](https://openrouter.ai) 註冊帳號
2. 入 [Keys](https://openrouter.ai/keys) 頁建立新 key（格式 `sk-or-v1-...`）
3. 充值（OpenRouter 按 token 計錢，各 model 價錢唔同，可以喺 [Models](https://openrouter.ai/models) 查）

**第二步：喺 MoTitle 填入**
1. 喺 dashboard 頭頂 pipeline 條嘅 **MT** step 揀 **OpenRouter**
2. 彈出 settings modal：貼 API key + 揀 model
3. Curated models（按英中翻譯質素排列）：

| Model ID | 說明 |
|---|---|
| `anthropic/claude-opus-4.5` | Claude Opus 4.5（最高質素，最貴） |
| `anthropic/claude-sonnet-4.5` | **推薦** — 質素接近 Opus，成本 1/5 |
| `anthropic/claude-haiku-4.5` | 快速、低延遲，批次便宜 |
| `openai/gpt-4o` | OpenAI 旗艦，中文流暢 |
| `openai/gpt-4o-mini` | 成本低，準度中上 |
| `google/gemini-2.5-pro` | Google 旗艦，長 context |
| `deepseek/deepseek-chat` | **極便宜**，中文理解佳 |
| `qwen/qwen-2.5-72b-instruct` | 阿里巴巴，中文強項 |
| `meta-llama/llama-3.3-70b-instruct` | Meta 開源旗艦 |

4. 亦可自行輸入任何 OpenRouter 支援嘅 model id（唔限 curated list）。輸過嘅 model 會記入 localStorage 做 suggestion。
5. 儲存後會即時套用到 active Profile。

**注意**
- API key 儲存喺 active profile 嘅 JSON（例如 `backend/config/profiles/dev-default.json`）。`dev-default.json` 同 `*.local.json` 已加入 `.gitignore`，**唔會**推上 git。模板範本喺 `backend/config/profiles.example/dev-default.json`（唔含 key）。新 clone 嘅工作流程：
  ```bash
  cp backend/config/profiles.example/dev-default.json backend/config/profiles/dev-default.json
  # 然後喺前端 MT step 彈出嘅 OpenRouter modal 填入你自己嘅 api_key
  ```
- 避開 reasoning models（如 `qwen/qwen3.5-122b-a10b`）除非你要深度推理 — 呢啲 model 每 call 有長長嘅 `reasoning` field，延遲可達 30–60 秒

#### 語言參數

每種語言可獨立設定：

| 參數 | 說明 | 預設值 (EN) |
|------|------|------------|
| `max_words_per_segment` | ASR 每段最大字數 | 40 |
| `max_segment_duration` | ASR 每段最大時長（秒） | 10.0 |
| `batch_size` | 翻譯批次大小 | 10 |
| `temperature` | 翻譯隨機度 | 0.1 |

### 前端頁面

| 頁面 | 功能 | 與後端通訊 |
|------|------|-----------|
| **index.html** | 主控台 — 上傳、轉錄、翻譯、設定 | REST API + WebSocket（即時進度） |
| **proofread.html** | 校對編輯器 — 審核、編輯、批核、渲染 | REST API（輪詢渲染狀態） |

**index.html 右側面板：**
- ⚙️ Profile 選擇器
- 📦 模型預加載
- 🎬 字幕延遲 / 大小控制
- 🌐 語言配置（可展開收合）
- 📖 術語表管理（可展開收合）

### 資料流（完整流程）

```
1. 用戶上傳影片 (index.html)
   │
   ├─ POST /api/transcribe → 上傳文件 + 開始轉錄
   │
2. 後端處理
   │
   ├─ FFmpeg 提取音頻 (16kHz WAV)
   ├─ ASR 引擎轉錄 (WebSocket 逐段推送進度)
   ├─ split_segments 後處理（按語言參數分割過長段落）
   ├─ 自動觸發翻譯 (Ollama Qwen2.5 + 術語表)
   └─ WebSocket 通知前端「翻譯完成」
   │
3. 前端預覽
   │
   ├─ 轉錄面板顯示中文字幕
   ├─ 播放影片時字幕同步顯示
   └─ 可點擊「🔄 重新翻譯」重做
   │
4. 校對 (proofread.html)
   │
   ├─ 左：影片播放 / 右：英中對照表格
   ├─ 逐句編輯中文翻譯 (Enter 儲存 + 自動批核)
   └─ 「批核所有未改動」一鍵完成
   │
5. 燒入字幕輸出
   │
   ├─ 點擊「匯出燒入字幕」→ 開啟渲染設定 Modal
   ├─ MP4：調整 CRF / 編碼速度 / 音頻碼率 / 解像度
   ├─ MXF：選擇 ProRes 規格 / 音頻位深 / 解像度
   ├─ 確認後後端生成 ASS 字幕 → FFmpeg 燒入
   └─ 完成後自動下載
```

---

## 項目結構

```
motitle/
├── backend/
│   ├── app.py              # Flask 後端服務器（REST API + WebSocket）
│   ├── profiles.py         # Profile 管理模組（ASR + 翻譯 + 字體配置）
│   ├── glossary.py         # 術語表管理模組（CRUD + CSV 匯入/匯出）
│   ├── language_config.py  # 語言參數配置模組（ASR + 翻譯參數）
│   ├── renderer.py         # 字幕渲染模組（ASS 生成 + FFmpeg 燒入）
│   ├── asr/                # ASR 引擎抽象層
│   │   ├── __init__.py     #   ASREngine ABC + 工廠函數
│   │   ├── whisper_engine.py #   Whisper 實現（faster-whisper / openai-whisper）
│   │   ├── segment_utils.py  #   段落後處理（分割過長段落）
│   │   ├── qwen3_engine.py #   Qwen3-ASR stub
│   │   └── flg_engine.py   #   FLG-ASR stub
│   ├── translation/        # 翻譯引擎抽象層
│   │   ├── __init__.py     #   TranslationEngine ABC + 工廠函數
│   │   ├── ollama_engine.py #   Ollama/Qwen 翻譯（本地 LLM）
│   │   └── mock_engine.py  #   Mock 翻譯（開發測試）
│   ├── config/             # 配置文件
│   │   ├── settings.json   #   當前 Profile 指標
│   │   ├── profiles/       #   Profile JSON 文件
│   │   ├── glossaries/     #   術語表 JSON 文件
│   │   └── languages/      #   語言參數 JSON 文件 (en.json, zh.json)
│   ├── tests/              # 測試套件（271 個測試）
│   └── data/               # 上傳文件及渲染輸出（自動生成，gitignore）
├── frontend/
│   ├── index.html          # 主控台 — 上傳、轉錄、翻譯、設定
│   └── proofread.html      # 校對編輯器 — 審核、編輯、批核、渲染
├── docs/superpowers/       # 設計文檔及實作計劃
├── setup.sh                # 一鍵安裝腳本
├── start.sh                # 一鍵啟動腳本
└── README.md               # 本文件
```

---

## 術語表管理

系統內建「Broadcast News」術語表，包含常用香港廣播新聞術語：

| 英文 | 中文 |
|------|------|
| Legislative Council | 立法會 |
| Chief Executive | 行政長官 |
| Hong Kong | 香港 |
| government | 政府 |
| police | 警方 |
| ... | ... |

可通過 API 新增、編輯、匯入 CSV 術語表。術語會自動注入翻譯 prompt，確保專業名詞翻譯一致。

---

## Whisper 模型對照表

| 模型 | 參數量 | 速度 | 精準度 | 建議用途 |
|------|--------|------|--------|---------|
| tiny | 39M | 最快 | 基礎 | 開發測試 |
| base | 74M | 快 | 良好 | 快速轉錄 |
| small | 244M | 中等 | 優良 | 一般使用（推薦） |
| medium | 769M | 慢 | 出色 | 高精準度需求 |
| large | 1550M | 最慢 | 最佳 | 最高精準度 |
| turbo | 809M | 快 | 優良 | 速度與精準度平衡 |

> **提示**：安裝 `faster-whisper` 後，所有模型速度可提升 4–8 倍。

---

## 效能調校

### 並發批次翻譯（parallel_batches）

Profile 的翻譯設定支援 `parallel_batches`（預設 1）。設定後，翻譯引擎會同時發送多個 batch 請求，縮短總翻譯時間。

| 使用情境 | 建議值 |
|---------|--------|
| 本地 Ollama（3B/7B 模型） | 1–2 |
| 雲端模型（qwen3.5-397b-cloud 等） | 3–5 |

在 Profile 編輯器的「翻譯設定」區塊設定「並發批次」欄位即可。

> **注意：** 使用本地 Ollama 時，需同時設定 `OLLAMA_NUM_PARALLEL` 環境變量，數值須 ≥ `parallel_batches`：
>
> ```bash
> OLLAMA_NUM_PARALLEL=2 ollama serve
> ```
>
> 16 GB RAM 的 Apple Silicon Mac 跑 7B 模型時，建議不超過 2，以免記憶體不足。  
> 雲端模型（`ollama signin` 後使用）無此限制，可設至 3–5。

### 處理時間顯示

每次翻譯完成後，介面會顯示各階段耗時：

```
ASR: 8s ｜ 翻譯: 34s ｜ 總計: 42s
```

翻譯進行中也會即時顯示已用時間，方便確認處理速度是否符合預期。

---

## 翻譯質素調校

MoTitle 提供四種翻譯模式，由簡單到進階可按需要逐級切換。全部喺 Profile 嘅 `translation` block 配置。

### 模式 1 — 傳統 batch translate（預設）
最快，模型逐批譯獨立 ASR segments。適合短片、日常字幕。
```json
"translation": {
  "alignment_mode": "",
  "translation_passes": 1
}
```

### 模式 2 — Sentence pipeline
用 pySBD 先合併連續 ASR segments 做完整句子翻譯，再按時間比例切返去原本 segments。適合 ASR 切得太散嘅情況（每段 1-2 個字）。
```json
"translation": {
  "alignment_mode": "sentence",
  "use_sentence_pipeline": true
}
```
加入 `MAX_MERGE_GAP_SEC = 1.5` 時間閘門，相隔超過 1.5 秒嘅 segments 唔會強行合併。

### 模式 3 — LLM-anchored alignment（`llm-markers`）
Sentence pipeline 嘅進階版：合併成句後，prompt LLM 喺中文輸出中 **注入 `[N]` 位置 marker**，然後按 marker 位置切返去原本 segments — 比純時間比例準確。Marker 解析失敗時 fallback 去 word-level timestamps + 中文標點對齊。
```json
"asr": {
  "word_timestamps": true          // 需要 DTW word-level 對齊
},
"translation": {
  "alignment_mode": "llm-markers"
}
```
**適用**：長句被 ASR 切成 3+ segments、需要精確時間邊界嘅廣播字幕。

### 模式 4 — Two-pass enrichment（最慢，最貼 reference 人譯）
基於以上任一模式，再跑第二 pass 加描述性修飾詞（形容詞/副詞），令輸出接近 Netflix TC 人譯風格。
```json
"translation": {
  "alignment_mode": "llm-markers",  // 或其他
  "translation_passes": 2
}
```
時間成本：約 ×2（因為每 batch 要多一次 LLM call）。建議配合強 model（Claude Sonnet、Qwen3.5-397b）。

### 其他相關參數

| Profile 欄位 | 說明 |
|---|---|
| `asr.word_timestamps` | 啟用 DTW word-level timestamp（`alignment_mode: "llm-markers"` 嘅 fallback 會用到） |
| `translation.parallel_batches` | 並發 batch 數（見上面效能調校） |
| `translation.context_window` | 傳給 LLM 嘅前後 segment context（parallel 模式下自動 disable） |

---

## API 參考

後端提供以下 REST 端點（基礎 URL：`http://localhost:5001`）：

### 文件管理
| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/transcribe` | 上傳並轉錄（自動觸發翻譯） |
| GET | `/api/files` | 列出所有文件 |
| GET | `/api/files/<id>/media` | 取得媒體文件 |
| GET | `/api/files/<id>/subtitle.<fmt>` | 下載字幕（srt/vtt/txt） |
| DELETE | `/api/files/<id>` | 刪除文件 |

### Profile 管理
| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/profiles` | 列出所有 Profile |
| POST | `/api/profiles` | 建立 Profile |
| GET | `/api/profiles/active` | 取得當前 Profile |
| POST | `/api/profiles/<id>/activate` | 切換 Profile |

### 翻譯與校對
| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/translate` | 翻譯文件字幕 |
| GET | `/api/files/<id>/translations` | 取得翻譯結果 |
| PATCH | `/api/files/<id>/translations/<idx>` | 修改翻譯（自動批核） |
| POST | `/api/files/<id>/translations/approve-all` | 批量批核 |

### 術語表
| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/glossaries` | 列出術語表 |
| POST | `/api/glossaries/<id>/entries` | 新增術語 |
| DELETE | `/api/glossaries/<id>/entries/<eid>` | 刪除術語 |
| POST | `/api/glossaries/<id>/import` | 匯入 CSV |
| GET | `/api/glossaries/<id>/export` | 匯出 CSV |

### 語言配置
| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/languages` | 列出所有語言配置 |
| GET | `/api/languages/<id>` | 取得語言配置 |
| PATCH | `/api/languages/<id>` | 更新語言參數 |

### 渲染
| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/render` | 開始燒入字幕渲染 |
| GET | `/api/renders/<id>` | 查詢渲染狀態 |
| GET | `/api/renders/<id>/download` | 下載渲染結果 |

---

## 更新記錄

### v3.3 — MP4 進階輸出參數（Bitrate Mode + Pixel Format + H.264 Profile / Level）

- **Bitrate 控制模式**：MP4 卡片加入 3 個 tab 切換 — CRF（質素目標，default）/ CBR（固定碼率）/ 2-pass（兩次編碼達至更佳 bitrate 利用，慢 ~2×）。
- **CBR 與 2-pass 模式** 有 slider 2–100 Mbps（step 1，default 20 Mbps）+ 三個 preset 按鈕：**串流 15M** / **廣播 master 40M** / **近無損 80M**。
- **Pixel format**：新增 `yuv420p`（預設，兼容最廣）/ `yuv422p`（廣播 master）/ `yuv444p`（色彩精準）。
- **H.264 Profile**：`baseline` / `main` / `high`（預設）/ `high422` / `high444`。
- **H.264 Level**：`3.1` / `4.0` / `4.1` / `4.2` / `5.0` / `5.1` / `5.2` / `auto`（預設，由 libx264 自動揀）。
- **嚴格配對（雙向驗證）**：`yuv422p` 必須配 `high422` profile；`yuv444p` 必須配 `high444`。後端 submit 時驗證；錯配會返 400 + 明確 fix 提示。
- **2-pass 並發安全**：每次 render 用獨一 passlogfile prefix，兩個並發 2-pass render 唔會撞 stats file。
- **向下相容**：舊 client 冇傳 render_options 或只傳部分欄位，輸出同之前完全一樣（CRF 18 / medium preset / yuv420p / high profile / level auto / AAC 192k）。
- **Tests**：21 new；總共 410 個自動化測試（+21 since v3.2）。

### v3.2 — MXF XDCAM HD 422 輸出 + 統一渲染 Modal + Save As 選擇位置

- **新輸出格式 MXF · XDCAM HD 422**：Sony 廣播標準，MPEG-2 4:2:2 long-GOP，CBR bitrate 可自由調校 **10–100 Mbps**（預設 50 Mbps，業界標準）。48kHz PCM 音軌，output `.mxf` 檔。
- **統一渲染 Modal**：Dashboard 撳任何輸出格式（MP4 / MXF ProRes / XDCAM / ⚙）都會彈同一個設定視窗；原本嘅直接下載改為先揀參數先渲染。3 張格式卡片可切換：
  - **MP4**：CRF slider（0–51）、9 級編碼速度、音頻碼率 64k–320k
  - **MXF ProRes**：6 種規格卡（Proxy/LT/Standard/HQ/4444/4444XQ）、PCM 16/24/32-bit
  - **MXF · XDCAM HD 422**：視頻碼率 slider（10–100 Mbps 步進 5）、PCM 16/24/32-bit
  - 共用：輸出解像度（保持原始 / 720p / 1080p / 1440p / 4K）
- **Save As 下載**：渲染完成後彈 **系統級「另存為」對話框**（Chrome / Edge desktop 原生支援，經 File System Access API），可自訂下載 folder + 檔名，並以 `pipeTo(writable)` 直接串流大 MXF 檔，唔會佔 browser memory。Safari / Firefox 自動回退去瀏覽器預設下載資料夾 + 提示 toast。
- **Tests**：14 個新測試，涵蓋 XDCAM encoder 參數、bitrate 驗證邊界（10/75/100 pass、5/150/non-int reject）、檔名 `.mxf` 正確、modal 三態切換 + slider live label + POST payload shape。
- **389 個自動化測試**（+14 new since v3.1）

### v3.1 — 翻譯質素提升 + OpenRouter 引擎

- **OpenRouter 翻譯引擎**：新增對 Claude / GPT-4o / Gemini / DeepSeek 等 frontier models 嘅支援，透過 OpenRouter 統一 API。9 款 curated models + 可自訂任何 model id，localStorage 記錄歷史。
- **OpenRouter settings modal**：專用 modal 輸入 API key（password-masked，可切顯示）、揀 model（suggestions + 歷史），儲存後即時套用到 active Profile。
- **Phase 1 — 字幕字數上限放寬**：`MAX_SUBTITLE_CHARS` 16 → 28（貼近 Netflix TC 規範），減少 `[LONG]` false positive；`_filter_glossary_for_batch()` 按 batch 內容過濾 glossary，避免 prompt bloat。
- **Phase 2 — Sentence pipeline 時間閘門**：`MAX_MERGE_GAP_SEC = 1.5`，避免相隔太遠嘅 segments 合併造成時間錯亂。
- **Phase 3 — Sentence scope context**：prompt 向 LLM 標示邊幾個 segments 屬同一句，改善跨 segment 翻譯連貫性。
- **Phase 4+5 — 廣播 few-shot + Pass 2 enrichment**：繁中 system prompt + 4 個廣播新聞例子；opt-in `translation_passes: 2` 加描述性修飾詞。
- **Phase 6 Step 1 — ASR word-level timestamps**：`word_timestamps: true` 啟用 DTW 對齊，每個字嘅時間、字符機率都會儲起。
- **Phase 6 Step 2 — LLM-anchored alignment**：`alignment_mode: "llm-markers"` 用 `[N]` 位置 marker 將長句翻譯精準切返去原本 ASR segments；marker 解析失敗時 fallback word-level timestamps + 中文標點對齊。
- **翻譯按鈕 UI 修正**：dashboard file header 加返 `▶ 翻譯` / `⏳ 翻譯中…` / `🔄 重新翻譯` 三態按鈕（原本函數存在但冇 UI 入口）。
- **375 個自動化測試**（+71 new：alignment pipeline 15、OpenRouter engine 16、sentence time-gap 5、ASR word timestamps 5、segment utils word partitioning 4，其他）

### v3.0 — 模組化引擎選擇 + 渲染匯出參數

- **引擎模組化**：ASR 同翻譯引擎可獨立選擇、獨立配置，不再綁定 Profile
- **引擎參數 API**：每個引擎提供 param schema + 可用模型列表，前端動態渲染參數欄位
- **Profile CRUD UI**：側邊欄 Profile 管理介面 — 建立、編輯、刪除，active Profile 刪除保護
- **Ollama Cloud 模型支援**：glm-4.6-cloud、qwen3.5-397b-cloud、gpt-oss-120b-cloud（需 `ollama signin`）
- **渲染 Bug 修正**：修正 6 個渲染相關 bug，包括 `fileId` scope ReferenceError、FFmpeg stderr 傳遞、`output_filename` 欄位等
- **渲染匯出參數面板**：
  - 點擊「匯出燒入字幕」開啟渲染設定 Modal
  - MP4：CRF slider (0–51)、編碼速度（9 級）、音頻碼率（6 選項）、輸出解像度
  - MXF：ProRes 規格卡片格（Proxy / LT / Standard / HQ / 4444 / 4444 XQ + 碼率說明）、音頻位深（16/24/32-bit PCM）、輸出解像度
  - 後端完整驗證所有參數，返回 400 + 明確錯誤訊息
- **271 個自動化測試**（+126 個新增）

### v2.1 — 語言配置、前端 UI 整合、Bug 修復
- 語言參數配置：每種語言獨立設定 ASR 分段參數及翻譯參數
- ASR 後處理：自動分割過長段落（按句子邊界）
- 前端語言配置面板：可展開收合，直接編輯語言參數
- 前端術語表面板：可展開收合，新增/刪除術語、CSV 匯入
- 翻譯狀態徽章：待翻譯/翻譯中/翻譯完成，支援手動觸發翻譯
- 多項 Bug 修復：術語表顯示、拖放上傳、驗證錯誤提示等
- 145 個自動化測試（+36 個新測試）

### v2.0 — 廣播字幕製作系統
- 全新 pipeline：英文影片 → ASR 轉錄 → 中文翻譯 → 校對 → 燒入字幕輸出
- Profile 系統：可切換 ASR + 翻譯引擎組合
- 多引擎 ASR：統一介面支援 Whisper、Qwen3-ASR（stub）、FLG-ASR（stub）
- 翻譯 pipeline：本地 Ollama + Qwen2.5，支援粵語及書面語風格
- 術語表管理：英中對照，CSV 匯入/匯出
- 校對編輯器：獨立頁面，左右並排，逐句審核
- 字幕渲染：ASS 字幕 + FFmpeg 燒入，支援 MP4 及 MXF (ProRes) 輸出
- 自動翻譯：轉錄完成自動觸發翻譯
- 移除實時錄製模式：專注文件式廣播字幕製作流程
- 109 個自動化測試

### v1.0–v1.5 — 原始版本
- 文件上傳轉錄，支援多種格式
- Whisper ASR + faster-whisper 加速
- 轉錄進度條及預計剩餘時間
- 字幕內容編輯
- SRT/VTT/TXT 導出
