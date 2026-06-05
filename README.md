# 🎙 MoTitle — 廣播字幕製作系統

基於 [OpenAI Whisper](https://github.com/openai/whisper) 及本地 AI 翻譯模型嘅專業字幕製作工具。將英文影片自動轉錄、翻譯為**繁體中文（粵語/書面語）**字幕，經人工校對後燒入影片輸出。

---

## 功能特點

| 功能 | 說明 |
|------|------|
| 📁 **文件上傳與管理** | 拖放或選擇影片/音頻，支援 MP4、MOV、AVI、MKV、WebM、MXF 等格式 |
| 🤖 **英文語音轉錄** | Whisper ASR 自動將英文語音轉為英文文字（支援 faster-whisper 加速，以及 Apple Silicon 嘅 MLX-Whisper） |
| 🇭🇰 **粵語/中文語音轉錄** | Whisper ASR 中文模式 + `initial_prompt` 防 head hallucination + OpenCC `s2hk` 自動轉繁體（HK style）。可逐 Profile 設定 `initial_prompt`（例如「香港賽馬新聞」提示主題） |
| 🌐 **中文翻譯** | 三種選擇：本地 Ollama + Qwen2.5/3.5、Ollama Cloud、或 **OpenRouter**（Claude / GPT-4o / Gemini / DeepSeek 等 9 款 frontier models，用戶可自訂任何 OpenRouter model id） |
| 🎯 **翻譯質素調校** | 四種模式：傳統 batch → sentence pipeline → LLM-anchored alignment → 兩次 pass enrichment。詳見「翻譯質素調校」章節 |
| 📖 **術語表管理** | 自訂英中術語對照表，確保專業名詞翻譯一致（支援 CSV 匯入/匯出、一鍵 LLM 智能替換） |
| ⚙️ **Profile 配置** | 可切換不同 ASR + 翻譯引擎組合，適應開發/生產環境 |
| 🌐 **語言參數配置** | 每種語言獨立設定 ASR 分段參數（每句最大字數/時長）及翻譯參數（batch size/temperature） |
| 🗣️ **第一/第二語言字幕** | 每條影片可揀第一或第二語言字幕（或雙語）；Profile 第一=原文、第二=譯文，V6 第一=辨識結果（第二語言可選）。**預設顯示**：有兩種語言 → 雙語、只得一種 → 第一語言，仍可隨時切換（只影響畫面顯示，匯出/燒入可逐檔另設） |
| ✏️ **字幕校對編輯器** | 獨立校對頁面，左右並排影片與字幕表格，逐句審核、編輯、批核。段列表每行顯示 **In + Out 時間**，**撳一下即同步跳轉影片**到該段；底部時間軸（波形）任何視窗闊度/縮放都貼底可見 |
| 🎬 **燒入字幕輸出** | 將已批核字幕燒入影片，可調整編碼參數後輸出：**MP4** (H.264，支援 CRF / CBR / 2-pass 三種 bitrate mode、yuv420p/422p/444p、H.264 Profile & Level)、MXF (ProRes)、或 MXF · **XDCAM HD 422**（MPEG-2 4:2:2，碼率 10–100 Mbps 自由調校）。渲染完成後可經系統級「另存為」對話框揀下載位置。 |
| 📊 **轉錄進度條** | 轉錄時顯示進度百分比、預計剩餘時間（ASR 階段進度為**時間估算** —— mlx-whisper 一次過轉錄、唔 stream，完成時校正至 100%；翻譯等其他階段用後端真實進度） |
| ⚡ **雙引擎支援** | 自動選用 faster-whisper（快 4–8 倍）或 openai-whisper |
| 💾 **字幕導出** | 每個文件獨立提供 SRT、VTT、TXT 下載 |

---

## 多用戶 Server Mode（R5 — Phase 1 → 5 完成）

由 single-user CLI 工具升級成 self-hosted multi-client server，畀 3-5 人小團隊（廣播台同事）喺 LAN 上共用同一部 server。**已通過 Phase 5 安全 + 生產加固，可以喺真實 LAN deploy。**

### 一鍵安裝

**macOS（Apple Silicon）**：
```bash
./setup-mac.sh
source backend/.env && cd backend && source venv/bin/activate && python app.py
```

**Windows + NVIDIA**：
```powershell
.\setup-win.ps1
.\backend\venv\Scripts\Activate.ps1
python backend\app.py
```

**Linux (Ubuntu/Debian, NVIDIA GB10 或任何 CUDA GPU)**：
```bash
./setup-linux-gb10.sh
source backend/.env && cd backend && source venv/bin/activate && python app.py
```

`nvidia-cublas-cu12` + `nvidia-cudnn-cu12` 嘅 aarch64 wheel 已 PyPI 上架，GB10 直接 `pip install` 就得。

三個 script 都會：(1) 建 venv + 裝 ASR/翻譯依賴；(2) 互動 prompt 起 admin 用戶；(3) 生成 `FLASK_SECRET_KEY` 寫入 `backend/.env`（已 gitignore）。

### Server 行為

- Server 預設綁 `0.0.0.0:5001`，**自動啟用 HTTPS**（如 `backend/data/certs/server.{crt,key}` 存在；setup script 預設用 mkcert（fallback 用 openssl）生成）。LAN 內 client 用 `https://<server-ip>:5001/` 存取。`R5_HTTPS=0` 可強制 HTTP；`BIND_HOST=127.0.0.1` 縮返 localhost-only。
- 第一次連入時瀏覽器會警告 "Not Secure" — 用 `mkcert -install` 喺每部 client 機加入信任，或者手動匯入 `server.crt`。
- CORS 自動限制喺 LAN 私有 IP 段（10/8、172.16/12、192.168/16、loopback）— 公網 origin 一律拒絕，唔需要再喺 firewall 額外設防。
- Auth 用 Flask-Login session cookie。所有 `/api/*` endpoint 要登入；`/api/files/<id>/*` 系列要 owner 或 admin 先 access 到。
- Job queue：ASR 1 個並發（GPU bound）、translate/render 3 個並發；server 重啟後自動將 stuck `running` job 標 `failed` 重排。
- 上傳檔案落 `backend/data/users/<uid>/uploads/<file_id>.<ext>`，按 owner 隔離。
- DB 喺 `backend/data/app.db`（SQLite，gitignore）；admin 可以用 `python backend/scripts/migrate_registry_user_id.py` 將 pre-R5 文件回填到 admin 名下。

### Phase 進度（全部完成）

| Phase | 完成內容 |
|---|---|
| **Phase 1** | Auth (Flask-Login + bcrypt) / per-user file isolation / Job queue (1 ASR + 3 MT worker) / LAN-only CORS / setup-mac + setup-win scripts |
| **Phase 2** | ASR + MT 統一 JobQueue (`/api/transcribe` + `/api/translate` 返 202 + job_id) / Linux/GB10 setup script / 自簽 HTTPS auto-enable |
| **Phase 3** | Admin dashboard CRUD (`/admin.html`：用戶 / Profile / Glossary / Audit log 四個 tab) / per-user Profile + Glossary 隔離 (admin 可編所有共享，用戶只見自己 + 共享) / cancel queued + retry failed |
| **Phase 4** | `/api/files` 加 `job_id` 欄 (file-card cancel 按鈕真正生效) / Mobile responsive UI (≤768px hamburger drawer + tabbed proofread；≤1024px tablet) / Cancel running jobs (worker thread `JobCancelled` exception，ASR poll between segments，MT poll between batches) |
| **Phase 5** | **5 個 BLOCKING bug 修正**：login null 崩潰 / SocketIO 缺 auth / SECRET_KEY placeholder / 私人 Profile/Glossary 漏出 / poison-pill 重試無上限。**8 個生產加固**：Whisper cache key 完整 / worker app context / SQLite WAL / SameSite cookie / render endpoint 擁有人 check / cancel_event 入 MT engine / atomic last-admin guard / TOCTOU fix |

**測試覆蓋**：673 個 backend tests pass + 1 個已知 v3.3 baseline (macOS tmpdir colon-escape，與 R5 無關)。Playwright E2E 6/6 GREEN。

### Phase 5 新增環境變數 / 安全行為

- **`FLASK_SECRET_KEY`**：**必須設定**。Server boot 時讀取；如果未設或等於 placeholder `change-me-on-first-deploy` 就 raise `RuntimeError` 拒絕啟動。三個 setup script 自動生成 `secrets.token_hex(32)` 寫入 `backend/.env`。
- **`R5_MAX_JOB_RETRY`**（預設 `3`）：boot recovery 嘅重試次數上限。某個 job `attempt_count >= R5_MAX_JOB_RETRY` 之後 server 重啟唔會再 re-enqueue（避免 misconfigured handler 觸發無限重試）。Operator 要手動透過 `POST /api/queue/<id>/retry` 重試。
- **密碼政策**：建立 / 重設用戶密碼時，密碼必須 **≥ 8 字元且非常見密碼**，否則 API 回 400 並顯示政策提示。
- **Session cookie**：自動加 `SameSite=Lax` + `HttpOnly`；HTTPS 啟用時加 `Secure`。Mitigates cross-origin CSRF。
- **SocketIO auth**：cross-origin 客戶端唔再可以開 socket。CORS 同 Flask 共用 `_LAN_ORIGIN_REGEX`（10/8 + 172.16/12 + 192.168/16 + 127/8 + localhost）。
- **Render endpoint**：`GET /api/renders/<id>` + `download` + `DELETE` 全部 enforce file owner check（admin 可以 access 所有）。
- **Database migrations**：`backend/migrations/2026-05-10-add-jobs-attempt-count.py` — idempotent，可手動跑（`python backend/migrations/2026-05-10-*.py backend/data/app.db`）；亦會喺每次 `init_jobs_table` 自動 backfill。

### Cancel job 行為

- **Queued job**：`DELETE /api/queue/<id>` → 200，DB 即時 cancelled。
- **Running job**：`DELETE /api/queue/<id>` → 202 + `{ok:true, status:"cancelling"}`。Worker 喺下一個 checkpoint 自動停（ASR：每 segment 之間，~1 秒；MT：每 batch 之間，~30 秒最差情況）。最終 status flip 出現喺 next polling round。

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

## V6 Dual-ASR Pipeline（粵語廣播 / 多語素材）

dev v3.19 加入 V6 pipeline，處理 mlx-whisper 處理唔好嘅素材（特別係粵語廣播）。架構：

1. **VAD 預分段** — Silero VAD 由源頭切走靜音段，eliminate cascade hallucination
2. **Qwen3-ASR** — 內容權威，per-region 識別，支援 entity name context（人名 / 地名提示）
3. **mlx-whisper** — 純做時間軸 reference，text 唔輸出
4. **Refiner LLM** — Ollama qwen3.5:35b-a3b-mlx-bf16 整理廣播風格

### 啟用 V6

```bash
# 1. 安裝 main venv 嘅 silero-vad（已喺 requirements.txt）
cd backend && source venv/bin/activate
pip install -r requirements.txt

# 2. 起 Qwen3-ASR 嘅 py3.11 subprocess venv（一次性）
bash backend/scripts/setup_v6.sh

# 3. 重啟 backend
python app.py
```

### 點切換 V6

> **注意（2026-06）**：之前喺 topbar 嘅 **pipeline strip**（preset dropdown + ASR / Qwen3 Context / Refiner column 即時切換）**已經移除**，由上方嘅進度條（`#topProgress`）取代。

目前 pipeline 預設由「上傳流程 / active 設定」決定，唔再經 topbar strip 手動切：

1. 上傳影片時喺彈出嘅「處理設定」視窗揀來源 / 輸出語言（output_lang 流程，見上文 2b 節）；或
2. 透過 active pipeline 設定（`POST /api/active`，`kind=pipeline_v6` + pipeline id）選用某條 V6 pipeline；上傳時會 snapshot 當時嘅 active pipeline。

已 import 嘅 V6 pipeline 範本包括 `[v6] 賽馬廣播 (Cantonese)` 同 `[v6] Winning Factor (English)`，內含 Qwen3 entity name context 同 Refiner prompt 預設。

### Per-file override

per-file `prompt_overrides` 資料模型（含 `qwen3_context` / `refiner_prompt`）及 `PATCH /api/files/<id>` API 仍然保留。

> **注意（2026-05-30）**：「自訂 Prompt」嘅前端編輯入口已從校對頁（Proofread page）移除；如需設定 override，仍可直接透過 `PATCH /api/files/<id>` API 寫入。

### 唔需要 V6？

完全唔影響 — Pipeline 預設仍係 Profile 系統。冇 mlx_qwen3_asr venv 嘅機器，V6 section 自動灰咗（boot 時 `V6_AVAILABLE=False`），現有 Profile 流程全部如常運作。

### V6 常見問題

**V6 pipeline 跑超過 15 分鐘自動 timeout / job 變 failed**

預設受 `R5_QWEN3_TIMEOUT_SEC=900`（15 分鐘）控制，超出會自動 terminate Qwen3 subprocess 並 mark job failed。15 分鐘係按 4-6 min 健康 broadcast budget × ~1.5× headroom 定，覆蓋大多數新聞 / 廣播片段。如果你嘅廣播片 routine 都過 15 分鐘，喺 `backend/.env` 加返環境變數：

```bash
R5_QWEN3_TIMEOUT_SEC=1800   # 30 分鐘
```

然後重啟 backend。配合 v3.20 嘅 concurrent-drain IPC fix（stdout/stderr 由兩個 daemon thread 即時 drain），再唔會出現 pipe-buffer 16-64 KB 撐爆引起嘅 deadlock 情況。CLAUDE.md v3.20 entry 同 [docs/superpowers/validation/2026-05-29-v6-ipc-fix-prototype-report.md](docs/superpowers/validation/2026-05-29-v6-ipc-fix-prototype-report.md) 有完整 root cause + empirical evidence。

### 連續旁白自動分句（2026-05-30 新增）

V6 pipeline 喺 Refiner 之後自動將過長字幕（超過 24 字）喺中文標點位置切細，避免連續旁白片（無自然停頓）出現一行跨多個子句嘅情況，同時保證每行最少 1.0 秒顯示時間、起點嚴格單調遞增。廣播片（有停頓）靠 VAD 自然分句，一般唔受影響。

### 為 V6 影片加第二語言（2026-05-30 新增）

V6 pipeline 預設只輸出一個語言（Refiner 結果 = 原文，例如粵語）。第二語言字幕屬可選 —— 唔加就維持單語言輸出。

> **注意（2026-06）**：之前喺 topbar pipeline strip 嘅「+ 加第二語言」按鈕已隨 pipeline strip 一同移除，**目前冇 topbar UI 入口**。後端 `POST /api/files/<id>/translate-second`（body `{lang}`，V6 only，目前支援 zh↔en）端點仍然保留可用 —— 經 API 觸發後，系統會用 qwen3.5 將原文翻譯做目標語言，完成後即可喺校對頁編輯、燒入、或匯出（`source=second` 取譯文、`source=bilingual` 雙語）。

### 詳細設計文檔

完整 spec 喺 [docs/superpowers/specs/2026-05-28-v6-dual-asr-merge-design.md](docs/superpowers/specs/2026-05-28-v6-dual-asr-merge-design.md)；feat branch 原 V6 design 喺 [docs/superpowers/specs/2026-05-21-v6-vad-dual-asr-refiner-design.md](docs/superpowers/specs/2026-05-21-v6-vad-dual-asr-refiner-design.md)。CLAUDE.md v3.19 entry 有完整 changelog。

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

### 2b. 揀輸出語言（上傳後彈窗）

揀片之後會彈出「處理設定」視窗，揀：

- **影片來源語言**：粵語 / 普通話 / 英文 / 日文 —— 呢個會驅動字幕點生成（**重要**），亦會決定第一輸出語言。
- **目標輸出第一語言**（必）：**鎖定跟來源語言**，唔可以自由揀 ——
  - 英文片只出現「英文」、普通話片只出現「普通話」、日文片只出現「日文」（單一選項、disabled、改唔到）；
  - **粵語片**例外，可揀「口語廣東話」或「中文書面語」兩種（**預設中文書面語**，廣播旁白慣用）。
- **目標輸出第二語言**（可選，揀「無」就單語言）：口語廣東話 / 中文書面語 / 普通話 / 英文 / 日文。第二語言會**自動排除與來源同一語系嘅選項**（粵語、普通話、中文書面語同屬中文系；英文、日文各自一系），以防同語系雙輸出做 index-merge 時造成時間軸 drift。👉 如果你想同時要兩種中文格式（例如口語廣東話＋中文書面語），請**分開上傳兩次**，分別揀唔同嘅第一輸出語言。
- **翻譯風格**：通用 / 體育新聞 / 馬會賽馬（**預設通用**）。只喺**英文 → 中文（書面語／普通話）嘅跨語系翻譯**時生效 —— 會載入 `backend/config/mt_style_prompts/` 下對應 prompt（`generic.txt` / `sportsnews.txt` / `racing.txt`，其中 racing 採用香港賽馬會賽馬用語）；同語系直出（如粵語直出粵語）唔經 LLM 翻譯，所以呢個選項唔影響。
- **中文字體**：繁體 / 簡體（只影響中文輸出，OpenCC s2hk / t2s）。

系統會**按來源 vs 輸出語言自動選最佳方法**：

- 輸出語言同來源**同一種**（例：粵語片→口語廣東話、普通話片→普通話/中文書面語、英文片→英文）→ **Whisper 直接轉錄**，分句同質量最好。
- 輸出語言**唔同**來源（例：粵語片→英文、英文片→中文、普通話片→口語廣東話、任何→日文）→ 先用內容語言轉錄，再用 LLM 翻譯做目標語言，避免 Whisper 夾硬迫語言時嘅亂碼/重複/誤譯。跨語系輸出採用「**內容語言轉錄一次 → 以對齊基底逐句 1:1 派生各輸出語言**」嘅做法（唔做同語系合併，從根本避免時間軸 drift），同時產生一個 `aligned_bilingual` 對齊網格供雙語匯出 / 渲染逐句配對。
- 「中文書面語」會額外經書面語潤飾（正式新聞書面語）；「普通話」保持原樣；繁/簡由你揀。

> 小貼士：來源語言揀啱好緊要 —— 揀錯（例如普通話片標成粵語）會令路由用錯方法、第一輸出語言鎖錯，影響字幕質量。

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

**校對段落分割／合併（僅限輸出語言檔案）：**

每行段落左側有兩個按鈕：
- **AI 智能分割**（✨）— 呼叫 LLM 按語意及標點位置將該段切成兩段，時間軸按內容語言字數比例分配；LLM 失敗時自動改用機械式切法
- **機械式對半分割**（✂）— 固定用 50/50 時間點切開，兩段均保留完整原文（適合之後手動改字）

每行段落右側有：
- **合併下一段** — 將當前段與下一段合併，文字以空格接合，時間取兩段聯集，並重設為待批核

分割／合併後，所有語言的字幕、時間軸、SRT 匯出及渲染均自動同步更新。段落短於 0.4 秒時，分割按鈕會變灰不可用；最後一段嘅合併按鈕同樣停用。

| 快捷鍵 | 功能 |
|--------|------|
| Ctrl+Shift+S | AI 智能分割當前段落 |
| Ctrl+Shift+D | 機械式對半分割當前段落 |
| Ctrl+Shift+M | 合併當前段落與下一段 |

> 以上快捷鍵在編輯文字框時同樣有效。部分瀏覽器可能佔用 Ctrl+Shift+D / M，此時可改用行按鈕操作。

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
| `max_words_per_segment` | ASR 每段最大字數 | 12 |
| `max_segment_duration` | ASR 每段最大時長（秒） | 60.0 |
| `merge_short_max_words` | 合併「短 segment」嘅字數門檻（≤ 此字數視為短，0 = 停用） | 2 |
| `merge_short_max_gap` | 合併嘅時間 gap 容忍度（秒，超過唔合併） | 0.5 |
| `batch_size` | 翻譯批次大小（**1 = 單段模式**，廣播質量優先；> 1 = 批次模式，速度優先） | 1 |
| `temperature` | 翻譯隨機度 | 0.0 |

> **`merge_short_*` 用途**（v3.8 新增）：Whisper 偶爾喺句子邊界生成單字 segment（如 `'a'`、`'settle.'`），燒入字幕只顯示 0.3 秒。後處理會用句子標點啟發式合返去鄰居 — 以 `.!?` 結尾 → 合上一段尾；唔以標點結尾 → 合下一段頭。中文配置（zh.json）預設 `merge_short_max_words: 0` 停用，因為現時只支援英文標點，中文 `。！？` 支援將來加。

> **`batch_size: 1` 單段模式**（v3.8 新增）：每個 ASR segment 獨立發送畀 LLM 翻譯，無 neighbour context。解決 batched mode 嘅三類問題：(1) 跨段內容錯位（一段嘅 ZH 變咗鄰段嘅內容），(2) Bloat（譯文加咗原文無嘅主語、連接詞、形容詞），(3) 相鄰段重複介紹同一人名。代價：對代詞（he / they / it）解析靠 LLM 自己估，可能影響準確性；速度比 `batch_size=10` 慢約 30%（115 段約 41 秒）。EN 預設啟用，ZH 預設用 `batch_size: 8`。

### 輸出語言 Pipeline 路由（ASR / Refiner / MT 架構）

> 適用於上傳彈窗選擇「輸出語言」的流程（`active_kind=output_lang`，現時的主要流程）。整條 pipeline 由頭到尾**只用兩個模型**。

**兩個模型**

| 角色 | 模型 | 說明 |
|---|---|---|
| **ASR** 語音辨識 | **mlx-whisper large-v3**（`mlx-community/whisper-large-v3-mlx`） | `condition_on_previous_text=False`、`task=transcribe` |
| **LLM**（MT + Refiner 共用） | **Qwen3.5 35B-A3B**（Ollama `qwen3.5:35b-a3b-mlx-bf16`，temperature 0.3） | MoE 混合專家模型：**總參數 35.1B、每個 token 只激活 3B（即「A3B」）**。MT 翻譯與書面語 Refiner 用同一個模型，差別只在於餵入的 prompt |

**核心原則：ASR 的 Whisper 語言純由「來源語音」決定，輸出語言不影響 ASR。** 內容音訊只轉錄一次，之後每個輸出語言各自由這個 base 作 1:1 衍生（多個輸出共用同一次 ASR）。

**表 1 — ASR 層（來源語音 → Whisper 語言）**

| 來源語音（上傳時選） | Whisper language |
|---|---|
| 粵語 `yue` | `yue` |
| 普通話 `cmn` | `zh`（Whisper 的 `zh` 以普通話為主，無獨立 cmn 代碼） |
| 英文 `en` | `en` |
| 日文 `ja` | `ja` |

**表 2 — 衍生模式矩陣（來源 × 輸出）**

語系劃分：`yue / cmn / zh` 屬中文系、`en`、`ja`。

| 來源 ＼ 輸出 | 口語粵語 `yue` | 書面語 `zh` | 普通話 `cmn` | 英文 `en` | 日文 `ja` |
|---|---|---|---|---|---|
| **粵語 yue** | 直通 | 書面化 | 書面化 | 翻譯 | 翻譯 |
| **普通話 cmn** | 翻譯 | 書面化 | 直通 | 翻譯 | 翻譯 |
| **英文 en** | 翻譯 | 翻譯 | 翻譯 | 直通 | 翻譯 |
| **日文 ja** | 翻譯 | 翻譯 | 翻譯 | 翻譯 | 直通 |

- **直通（passthrough）**：與來源同語言，直接複製文字，**不經 LLM**。
- **書面化（refine）**：同語系不同語體（口語 → 書面語 / 普通話），由 Refiner 改寫 register。
- **翻譯（MT）**：跨語系，由 MT 翻譯。

**表 3 — 每個模式用什麼模型與 Prompt**

| 模式 | 模型 | Prompt |
|---|---|---|
| **直通** | 無 LLM | 無（中文輸出最後過 OpenCC 繁/簡轉換） |
| **書面化 Refiner** | Qwen3.5 35B-A3B | **隨風格切換**：通用（預設）→ 中性 Refiner `zh_written_register_generic.json`；馬會賽馬 → 賽馬 Refiner `zh_written_register_v6.json` |
| **翻譯 MT** | Qwen3.5 35B-A3B | `英 → 中文書面語`：風格模板 `config/mt_style_prompts/{generic,racing,sportsnews}.txt`；**其餘語言對**：通用廣播 MT prompt（`_MT_SYS`，輸出中文時再附加「書面語規則」） |

**表 4 — Prompt 內容重點**

| Prompt | 用於 | 重點內容 |
|---|---|---|
| **通用 MT**（`_MT_SYS`） | 除「英 → 中文」外所有跨語系翻譯 | 廣播口播風格、自然流暢；**不得加入原文沒有的資訊或領域術語；保留專有名詞**；輸出中文時附加規則（禁用粵語口語字、禁將通用詞改成原文沒有的領域術語） |
| **風格模板**（generic / racing / sportsnews） | **僅**「英 → 中文書面語」翻譯 | 通用＝中性；馬會賽馬＝賽馬詞；體育新聞＝體育詞 |
| **中性 Refiner**（預設） | 任何「→ 書面語 / 普通話」書面化 | 口語 → 書面語 register；保留阿拉伯數字；**逐字保留人名 / 地名 / 英文詞**；**嚴禁注入賽馬 / 體育 / 財經等領域術語** |
| **賽馬 Refiner**（選用） | 書面化 + 已選「馬會賽馬」風格 | 同上，但帶賽馬語境、保留賽馬術語與賽事名 |

> **「逐字保留（byte-for-byte）」不是獨立模型或步驟，而是 prompt 規則**：MT 與兩個 Refiner 都要求人名、地名、英文詞、數字原樣不變。
>
> **OpenCC 繁/簡轉換**：所有中文輸出最後經 `apply_script`（繁體 `s2hk` / 簡體 `t2s`），與模型無關。
>
> **風格選擇器（`mt_style`）同時影響 MT 與 Refiner**：預設「通用」會用**中性** Refiner（不會把非賽馬內容寫成賽馬味）；製作真正賽馬素材時，於上傳彈窗選「馬會賽馬」才切換到賽馬 Refiner。

**表 5 — 完整流程例子**

| 來源 → 輸出 | ASR | 模式 | 模型 + Prompt |
|---|---|---|---|
| **粵語 → 書面語** | Whisper `yue` ×1 | 書面化 | Qwen3.5 + 中性 Refiner（選「馬會賽馬」才用賽馬 Refiner）+ OpenCC |
| **粵語 → 口語廣東話** | Whisper `yue` ×1 | 直通 | 無 LLM + OpenCC |
| **粵語 → 英文** | Whisper `yue` ×1 | 翻譯 | Qwen3.5 + 通用 MT |
| **普通話 → 書面語** | Whisper `zh` ×1 | 書面化 | Qwen3.5 + 中性 Refiner + OpenCC |
| **英文 → 書面語** | Whisper `en` ×1 | 翻譯 | Qwen3.5 + 英→中文風格模板（預設通用＝中性）+ OpenCC |

> 多個輸出共用同一次 ASR：例如「粵語 → 書面語 + 英文」只跑一次 Whisper `yue`，再由同一 base 分別書面化（書面語）與翻譯（英文），逐句對齊。

### 前端頁面

| 頁面 | 功能 | 與後端通訊 |
|------|------|-----------|
| **index.html** | 主控台 — 上傳、轉錄、翻譯、設定 | REST API + WebSocket（即時進度） |
| **proofread.html** | 校對編輯器 — 審核、編輯、批核、渲染 | REST API（輪詢渲染狀態） |
| **Files.html** | 檔案總覽頁 — 列出所有檔案及狀態 | REST API（`/api/files`，`js/files-page.js`） |
| **Glossary.html** | 術語表管理頁 — entry CRUD、CSV 匯入/匯出 | REST API（`/api/glossaries`） |
| **user.html** | 帳戶 / 改密碼 / admin 用戶管理 + 審計 | REST API（`/api/me`、`/api/admin/*`） |
| **login.html** | 登入頁 | `POST /login`（Flask-Login session） |

> 五頁共用同一套左側 rail（主頁 / 檔案 / 校對 / 術語表 / User）。

**index.html 主要面板：**
- 🚀 上傳影片（揀片後彈「處理設定」popup，選來源 / 輸出語言）
- 📊 工作隊列 panel（實時 stage label + 0–100% 進度條）
- 📖 術語表管理
- 🎬 字幕設定 / 字型控制

> **注意（2026-06）**：dashboard 右上角原本嘅「⚙ 設定」齒輪（語言配置管理入口）已**移除**（依 Ka Lok 設計，user chip 只剩「管理」＋「登出」）；語言配置管理功能因少用已退役。

### 資料流（完整流程）

```
1. 用戶上傳影片 (index.html)
   │
   ├─ POST /api/transcribe → 上傳文件 + 開始轉錄
   │
2. 後端處理
   │
   ├─ FFmpeg 提取音頻 (16kHz WAV)
   ├─ ASR 引擎轉錄（mlx-whisper 一次過轉錄、唔 stream；ASR 階段進度條由前端時間估算驅動，完成時校正至 100%）
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
│   │   ├── crosslang_mt.py #   跨語系 MT（per-segment 1:1，注入 llm_call）
│   │   └── mock_engine.py  #   Mock 翻譯（開發測試）
│   ├── output_lang_router.py   # 輸出語言路由（route_output / whisper_direct_params / content_asr_lang）
│   ├── output_lang_aligned.py  # 對齊基底逐句 1:1 派生 + aligned_bilingual 網格
│   ├── config/             # 配置文件
│   │   ├── settings.json   #   active_kind / active_id 指標
│   │   ├── profiles/       #   Profile JSON 文件
│   │   ├── glossaries/     #   術語表 JSON 文件
│   │   ├── mt_style_prompts/ # 翻譯風格 prompt (generic / sportsnews / racing .txt)
│   │   └── languages/      #   語言參數 JSON 文件 (en.json, zh.json)
│   ├── tests/              # 測試套件
│   └── data/               # 上傳文件及渲染輸出（自動生成，gitignore）
├── frontend/
│   ├── index.html          # 主控台 — 上傳、轉錄、翻譯、設定
│   ├── proofread.html      # 校對編輯器 — 審核、編輯、批核、渲染
│   ├── Files.html          # 檔案總覽頁（wire 到 /api/files）
│   ├── Glossary.html       # 術語表管理頁
│   ├── user.html           # 帳戶 / 改密碼 / admin 用戶管理 + 審計
│   ├── login.html          # 登入頁
│   └── js/                 # 前端模組（files-page.js / queue-panel.js / step-diagram.js / auth.js / user.js / font-preview.js）
├── docs/superpowers/       # 設計文檔及實作計劃
├── setup.sh                # 一鍵安裝腳本
├── start.sh                # 一鍵啟動腳本
└── README.md               # 本文件
```

---

## 術語表（多語言）

每個術語表帶有自己嘅原文同譯文語言設定。支援 8 種語言：英文、中文、日文、韓文、西班牙文、法文、德文、泰文。

可以建立任何語言組合：
- 英文 → 中文（傳統用法）
- 中文 → 中文（風格統一）
- 英文 → 英文（術語規範化）
- 日文 → 中文（日語節目翻譯）

每條 entry 有 `原文` / `譯文` 兩個必填欄位，加可選嘅 `譯文別名` 列表。

### CSV 匯入格式

三欄（第三欄可選）：

```csv
source,target,target_aliases
broadcast,廣播,
anchor,主播,主持;新聞主播
```

別名用 `;` 分隔。

⚠️ 由 v3.15 起，舊嘅 `en,zh` CSV header **唔再接受**。如要遷移舊資料，先 export 做 CSV、手動將 header 改為 `source,target`、再喺新建立嘅 glossary 度 import 返。

### 術語表自動套用（output_lang pipeline）

上傳影片時可喺 popup 揀選一個或多個術語表（順序即優先），並決定是否開啟 LLM 精修（預設開啟）。Pipeline 完成後，系統會自動在每個輸出語言的字幕裡，以 deterministic 方式將馬名、騎師名、專有名詞規範化成術語表指定譯文。

- **校對頁逐段對照**：「詞彙對照」欄位顯示 `原文 → 規範後 · 術語表名稱`，有改動的段落在段列表顯示 📖 標記，方便快速確認套用結果。
- **改完術語表後可即時重新套用**：校對頁「重新套用詞彙表」按鈕 → 系統由已快取的 ASR base 直接 re-derive，**無需重新轉錄**，幾秒內更新全片字幕。
- **多術語表衝突**：以輸入順序為優先（first-wins），不同術語表同一詞目以排前者為準。

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
