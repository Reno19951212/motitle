# V6 Pipeline 靜默執行 + /media 噪音 — 調查與交接報告

**日期**: 2026-05-29
**Reporter**: 調查 session by 3 parallel investigation agents
**Status**: Investigated + hypothesis ✅ **empirically validated** via `sample 49396` (see [validation/2026-05-29-v6-ipc-deadlock-evidence.md](../validation/2026-05-29-v6-ipc-deadlock-evidence.md))
**Branch**: `fix/v6-subprocess-ipc` (worktree at `../whisper-subtitle-ai-v6fix/`, cut from `Finalize` @ 611f7fd)
**Receiving agent**: 任何具備 backend Python + Flask + 前端 vanilla HTML/JS 修改權限嘅 agent

---

## 1. 事件摘要

用戶 16:20:29 上傳一條 34.6 MB 粵語廣播片 (`gamehub-遊戲-八卦-花生-新聞-cc中文字幕---瘋狂退款赤色沙漠急救搞唔搞得掂.mp4`)，選用 V6 dual-ASR pipeline (`[v6] 賽馬廣播 (Cantonese)`, id `4696bbaa-b988-49bd-859c-e742cb365634`)。9 分鐘後：

- Registry status 仍然 `transcribing`、`segments: []`
- Job DB row：`type=asr, status=running, attempt_count=1, error_msg=NULL`
- 後端 log 完全冇 V6 stage 級 stdout
- 同時 log 出現大量 (~80+ in 1 秒) `/api/files/<id>/media` 206 burst

用戶感知：「條 pipeline 唔係正喺度跑」+「log 好嘈，似有 bug」。

實際上有**兩個獨立問題**重疊：

| # | 問題 | 嚴重度 | Root cause type |
|---|------|--------|------------------|
| 1 | V6 pipeline 有可能真係 hang，而且就算唔 hang 都完全冇 progress observability | **High** — 可能無限等 | Subprocess IPC + logging 設計缺陷 |
| 2 | 單一 user click 觸發 80+ `/media` byte-range request | Low — 純噪音 | 前端 `<video>` element preload 默認值 |

兩個問題**唔互相影響**：問題 2 唔阻塞 ASR worker（不同 Flask route）。但兩個一齊出現製造咗「pipeline 死咗」嘅錯覺。

---

## 2. Forensic Evidence (Snapshot at 16:29:36)

```
File:    183e38257865  (user_id=627, 34,686,554 bytes)
Pipeline: 4696bbaa-b988-49bd-859c-e742cb365634 (V6 dual-ASR Cantonese)
Job ID:  2f6198039fef412fb3fc85cf81c05976
Job:     type=asr, status=running, started_at=16:20:29, finished_at=NULL
Elapsed: 9 min 7 sec
Next ASR queue:   8c943068b742 (queued at 16:20:59, waiting)
```

**Process state**:

| PID | Process | CPU since boot | Wall time | Notes |
|-----|---------|----------------|-----------|-------|
| 48537 | main backend (py3.9 `app.py`) | 0:07.7 | ~10 min | Healthy, polling subprocess in 0.5s sleep loop |
| 49396 | `qwen3_vad_subprocess.py` (py3.11 venv) | **0:36.5** | ~10 min | Spawned at backend boot, ALIVE, suspicious low CPU |

對 35B-equivalent MLX model 嚟講，9 min wall × 6.6% CPU 嘅 profile **唔似** active inference（應該係 steady 高 CPU），更似「load 完 model 之後 blocked 喺某個 IO 等」。

**Log 觀察**:
- Backend `/tmp/backend.log` 完全冇任何 V6 stage 字串（`Stage`, `VAD`, `Qwen3`, `Refiner`, `MLX`）
- 唯一見到嘅 entry 都係：Werkzeug HTTP access lines + `Loading faster-whisper model: small`（boot legacy path）
- DB jobs table 確認唔係空 — V6 worker 有 pick up 條 job 並標 `running`

---

## 3. 問題 1 分析 — V6 Pipeline 點解「冇執行」嘅錯覺

### 3.1 第一層：V6 pipeline 設計上**冇任何 stdout 痕跡**

`grep` 跨 V6 整條鏈：

| File | print/logger calls |
|------|-------------------|
| `backend/pipeline_runner.py` | **0**（只有 `_socketio_emit`） |
| `backend/stages/v6/silero_vad_stage.py` | 0 |
| `backend/stages/v6/qwen3_per_region_stage.py` | 0 |
| `backend/stages/v6/time_anchored_merge_stage.py` | 0 |
| `backend/stages/v5/refiner_stage.py` | 0 |
| `backend/engines/refiner/llm_refiner.py` | 0 |
| `backend/engines/llm/ollama.py` | 0 |
| `backend/engines/transcribe/qwen3_vad_engine.py` | 0 |
| `backend/asr/mlx_whisper_engine.py:44` | 明確 `verbose: False` |

加上 `backend/app.py` 冇 `logging.basicConfig`、Flask `app.logger.info` 喺 production WARNING level 全部 silently dropped。

**結論**：就算 V6 完全正常跑緊，`/tmp/backend.log` 都應該係空白嘅。**呢個係 by design omission，唔係 logger config 漏配**。

### 3.2 第二層：Registry status 中途唔 update

`_asr_handler` (`backend/app.py:281+`) 只喺：
- **Entry** (`app.py:324`) 將 status 標 `transcribing`
- **Exit** (`app.py:340`) 標 `completed` / `error`

中間任何 stage progress 都**唔寫 registry**。SocketIO 有 emit `pipeline_stage_start` / `_done` / `_progress` (`pipeline_runner.py:217, 260, 409, 446`) 但只去到**當時連住嘅 client**，唔會寫 stdout 亦唔會 persist 入 registry — refresh 頁面就消失。

**結論**：用戶見到 `status: "transcribing"` 9 分鐘係 expected behavior，唔係 stuck 嘅證明。

### 3.3 第三層：但係 9 分鐘 + 6.6% CPU 確實過界

健康時間預算 (operator-validated 4-min Cantonese 廣播):
- Stage 0 VAD: ~5s
- Stage 1A Qwen3-ASR (per region): ~2-4 min（1-3× realtime on MLX）
- Stage 1B mlx-whisper full audio: ~30s
- Stage 2 time-anchored merge: <1s
- Stage 3 Ollama refiner (~100 segs × 0.5s): ~1 min
- **Total expected**: 4-6 min

實際 9 min 已經 1.5-2× expected，疊埋 Qwen3 subprocess 嘅 36s CPU 過度低，**高度懷疑真係 hang**。

### 3.4 最 likely root cause — **Qwen3 subprocess pipe-buffer deadlock**

睇 `backend/engines/transcribe/qwen3_vad_engine.py:140-176`（parent 側）：

```python
proc = subprocess.Popen(
    [...],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,    # ← 全程 NOT drained
    stderr=subprocess.PIPE,    # ← 全程 NOT drained
)
proc.stdin.write(payload_bytes)
proc.stdin.close()

while proc.poll() is None:     # ← line 154-165
    if cancel_event.is_set():
        proc.terminate()
        ...
    time.sleep(0.5)             # ← parent thread 嘅 0:07 CPU 全部喺度

# 只喺 subprocess EXIT 之後先 drain：
stdout = proc.stdout.read()    # line 168
stderr = proc.stderr.read()    # line 169
```

睇 `backend/scripts/v5_prototype/qwen3_vad_subprocess.py:128`（child 側）：

```python
for region in regions:
    result = mlx_qwen3_asr.transcribe(region.wav_path, ...)
    sys.stderr.write(f"region {i} done: {result.summary}\n")  # ← 每個 region 一行
    sys.stderr.flush()
# 最後一次過：
json.dump(big_payload, sys.stdout)  # ← line 130
```

**Deadlock 機制**：
- macOS OS pipe buffer = **16 KB** (lsof 確認 PID 49396 fd 2 → PIPE 16KB)
- 多 region 廣播片，stderr 累積到 16 KB → subprocess `sys.stderr.write()` **block on write**
- Parent 永遠等 `proc.poll()` 變 non-None，但 child block 喺 stderr write → poll 永遠係 None
- 兩邊都係阻塞態 → infinite wait
- **冇 `subprocess.communicate(timeout=...)`、冇 wall-clock timeout**
- Docstring 提到嘅「1800s timeout」係 **stale comment**，code 入面冇 `timeout=` kwarg

呢個係 classic Python `subprocess` antipattern。

---

## 4. 問題 2 分析 — `/media` 80+ burst 噪音

### 4.1 確認唔係 JS bug
3 個獨立 grep pass：
- `frontend/js/font-preview.js`、`frontend/js/queue-panel.js`、`frontend/js/auth.js` — **完全冇** touch `/media`
- `frontend/index.html` 全文得 **1 個** `video.src =` 寫入位 (`index.html:4048`)，屬於 `loadMediaPreview(id)` function
- `loadMediaPreview` 觸發點得 2 個：
  - `selectFile(id)` (`index.html:4039`) — 用戶 click file card
  - upload handler (`index.html:4303`) — 上傳完即時 preload

SocketIO handler (`index.html:4941-5007`)、`renderAll/renderQueue/renderProgressOnly/renderInspectorBody` 全部冇再 set `video.src`。

### 4.2 80+ burst 嘅 root cause
單一 `video.src =` 寫入 → **HTML5 `<video>` element 嘅 native preload 行為**：

- `frontend/index.html:1413`: `<video id="videoPlayer" controls>` — 冇 `preload` attribute
- 默認 = `preload="auto"` → 瀏覽器aggressive 預載
- MP4 如果 `moov` atom 喺檔尾（即係冇 fast-start re-mux）→ Chromium walk 個檔：先 head metadata → 跳去 tail 攞 `moov` → 然後 progressive chunks
- 每個 byte range 都係獨立 HTTP request → Flask `send_file` 重新開檔
- 80+ 次 206 Partial Content 喺 1 秒內爆出嚟係**標準 Chromium behavior on Flask backend without fast-start**

### 4.3 影響評估
- ❌ **唔阻塞** ASR worker（不同 background thread + 不同 Flask route）
- ❌ **唔阻塞** queue polling、SocketIO emit
- ⚠️ 80× `open(file, 'rb')` 對大 MXF 檔（幾百 MB）會浪費 disk I/O
- ⚠️ 純 log noise，但會掩埋真實 error log

---

## 5. Top 5 行動項目 (排序：immediate triage → 永久 fix)

### 🚨 Immediate triage (對住 stuck 嘅 `183e38257865`)

**T1. 確認 Qwen3 subprocess 真係 deadlock**（5 分鐘，read-only）
```bash
# macOS sample tool — 拎 subprocess 嘅 C-level stack trace
sample 49396 1 -file /tmp/qwen3_sample.txt
# 如果見到 stack top 係 write() / Py_BlockOnFile / similar → pipe deadlock 確認
# 如果見到 mlx kernel inference → 唔係 deadlock，只係慢
```

**T2. Unblock worker**（如果 T1 確認 deadlock）
```bash
# Cancel 條 job — DELETE /api/queue/<job_id> 會 set cancel_event；
# worker 喺 0.5s sleep loop 入面會 pick 到 → proc.terminate() → 3s 後 kill()
# 整個 unblock 時間 < 5s
# 另一條 queued ASR job (8c943068b742) 即時開始
```

### 🛠 永久 Fix (落 code，需要 PR)

**T3. 修 Qwen3 subprocess IPC**（Problem 1 真正解法）
- File: `backend/engines/transcribe/qwen3_vad_engine.py:140-176`
- 換掉 hand-rolled `while poll(): sleep(0.5)` 為：
  ```python
  # Option A：parallel drain thread
  out_buf, err_buf = [], []
  t_out = threading.Thread(target=lambda: out_buf.append(proc.stdout.read()))
  t_err = threading.Thread(target=lambda: err_buf.append(proc.stderr.read()))
  t_out.start(); t_err.start()
  # poll for cancel_event in main, terminate proc if set
  proc.wait(timeout=900)  # ← 加 wall-clock timeout
  t_out.join(); t_err.join()
  ```
- 加 `R5_QWEN3_TIMEOUT_SEC` env var (default 900s)
- 同時：將 child 側 progress 信號從 stderr-per-region 改做 stdout-jsonl-streaming，畀 parent drain 嗰陣可以即時 forward 上 SocketIO

**T4. 加 V6 pipeline 嘅 logging + per-stage registry update**（Problem 1 observability）
- `backend/pipeline_runner.py`：每個 stage 前後加 `app.logger.info(f"[V6 stage {name}] start/done")`
- 修 `backend/app.py` boot：加 `logging.basicConfig(level=logging.INFO)` 或者特登 `app.logger.setLevel(logging.INFO)` 對 V6 namespace
- `_asr_handler` 入面，每個 V6 stage 完成後寫 registry 個 `progress_stage` field（serializable string）— 配合前端 polling 顯示「正在 Stage 1A Qwen3...」
- 仲可以考慮 mirror 一份 stage event 入 audit_log

**T5. 修 `<video>` preload 噪音**（Problem 2，10-min change）
- `frontend/index.html:1413`: 加 `preload="metadata"`（或 `preload="none"`，更激進）
  ```html
  <video id="videoPlayer" preload="metadata" controls></video>
  ```
- Bonus：upload 時 backend 自動 `ffmpeg -movflags +faststart -c copy` re-mux MP4 → `moov` 移到頭，唔再有 tail seek
- Bonus：`backend/app.py:3531` `serve_media` 加 `send_file(..., conditional=True)` 讓 Flask 處理 Range 更高效

### 🔍 Diagnostic (做完 T1/T2 之後，confirm pipe-deadlock 真係 root cause)
- 重跑同一條片，**先唔修 code**
- 用 `strace -p 49396 -e write,read`（Linux）或 `dtruss -p 49396 -t write`（macOS）監察 subprocess 嘅 write syscall
- 如果 confirm `write` block on stderr fd → 100% pipe deadlock
- 寫返入 [docs/superpowers/validation/](docs/superpowers/validation/) 嗰邊作 PR evidence

---

## 6. 關鍵 File:Line 索引

**V6 stuck point (highest priority)**:
- `backend/engines/transcribe/qwen3_vad_engine.py:140-176` — Popen + sleep poll loop, no drain, no timeout
- `backend/engines/transcribe/qwen3_vad_engine.py:168-169` — drain 只喺 exit 後 (`stdout/stderr.read()`)
- `backend/scripts/v5_prototype/qwen3_vad_subprocess.py:128` — per-region stderr write (deadlock 起源)
- `backend/scripts/v5_prototype/qwen3_vad_subprocess.py:130` — 最終 stdout JSON dump (亦有 deadlock 風險)

**V6 logging gap**:
- `backend/pipeline_runner.py:217, 260, 409, 446` — SocketIO emit 點 (只去 client, 唔去 stdout)
- `backend/app.py:324, 340` — registry status entry/exit (中間冇 update)
- `backend/app.py` 全文 — 冇 `logging.basicConfig`、`app.logger.info` 喺 production WARNING dropped
- `backend/asr/mlx_whisper_engine.py:44` — `verbose: False` 屏蔽 mlx-whisper 自己嘅 tqdm

**Worker pool**:
- `backend/jobqueue/queue.py:30-31` — `_ASR_CONCURRENCY = 1`, `_MT_CONCURRENCY = 3`
- `backend/jobqueue/queue.py:138-150` — `start_workers()` daemon thread creation
- `backend/jobqueue/queue.py:164` — `cancel_job()` 嘅 `cancel_event.set()`
- `backend/jobqueue/queue.py:182-202` — `_run_one` invocation 鏈

**V6 dispatch**:
- `backend/app.py:281-341` — `_asr_handler` + V6 branch
- `backend/pipeline_runner.py:482-519` — `_run_v6` stage 鏈
- `backend/stages/v6/qwen3_per_region_stage.py:46` — Stage 1A entry

**/media 噪音**:
- `frontend/index.html:1413` — `<video id="videoPlayer">` (missing `preload`)
- `frontend/index.html:4048` — `video.src =` (唯一寫入)
- `frontend/index.html:4039, 4303` — `loadMediaPreview` 觸發點
- `backend/app.py:3531-3544` — `serve_media` route handler

---

## 7. Non-issues (排除咗嘅紅鯡魚)

- `backend/data/jobs.db` 係 **0 bytes** 但**唔重要** — 真正嘅 jobs table 喺 `app.db`（`AUTH_DB_PATH = DATA_DIR / 'app.db'` at `app.py:222-223`）。`jobs.db` 係 leftover stub，刪左唔影響。
- `auth.db` 只有 `users` table 都係**正常** — 同 `app.db` 共存，可能係 conftest / test fixture 嗰邊用。
- Frontend `queue-panel.js` 3s polling `/api/queue` **唔係** `/media` burst 來源（已 grep 確認）。

---

## 8. 接收 agent 嘅 suggested workflow

1. **先做 T1 + T2** confirm hypothesis + 解 user 嘅當下 pain
2. **跑 diagnostic** (strace/dtruss) 取得 100% confirmation evidence
3. **寫 spec + plan** 喺 `docs/superpowers/specs/2026-05-30-v6-subprocess-ipc-fix-design.md` + 對應 plan
4. **依 Validation-First Mode 規矩**（見 CLAUDE.md「Validation-First Mode」section）— V6 屬於 ASR/MT 範圍，任何 code change **必須**先寫 prototype script 量化驗證 (e.g., 跑 5 條長度不同嘅粵語片，count subprocess hang rate before/after fix)
5. T3 / T4 / T5 三組改動可以平行，但 T3 係 root cause，優先
6. 寫 verification report 入 `docs/superpowers/validation/2026-05-30-v6-ipc-fix-report.md`，包括 before/after hang rate + stderr buffer 累積量 + Qwen3 wall time

預計 effort: T3 ~1 day (含 prototype + tests), T4 ~0.5 day, T5 ~1h, end-to-end PR including validation: ~2-3 days.

---

## 附錄 A：3 個調查 agent 嘅 raw finding 摘要

**Agent 1 (logging path)**: V6 stages 完全冇用 `print` / `logger`，silence by design omission，唔係 config bug。健康時間 budget 4-6 min，9 min @ 6.6% CPU 已係臨界。

**Agent 2 (/media burst)**: 確認 JS 冇 bug。Browser native `<video>` preload="auto" + MP4 moov-at-tail = 80+ range requests on src assign. Single trigger = single user click on file card.

**Agent 3 (worker + IPC)**: Worker thread 喺 `qwen3_vad_engine.py:154-165` `sleep(0.5)` 等 subprocess exit。Subprocess 高度懷疑 deadlock 喺 stderr write — child 寫 stderr per region，parent 直到 exit 先 drain，pipe 16KB 滿就互鎖。冇 wall-clock timeout。

---

**End of report.**
