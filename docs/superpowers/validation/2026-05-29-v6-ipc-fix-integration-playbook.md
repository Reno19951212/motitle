# T6 Integration Playbook — Live Replay on Real Audio

**Goal**: Replay the original stuck job (`gamehub-…赤色沙漠.mp4`) under the fix-branch backend on an alt port, confirm completion within ≤600s, capture before/after timing.

**Why alt port instead of swapping the main backend**: your `finalize-debug` session is still running on port 5001 with its own state. We start a SECOND backend from the worktree on port 5002 so both can coexist. After validation we can decide whether to swap main.

---

## Pre-flight (1 min)

1. Open a NEW terminal (separate from your `finalize-debug` session).
2. Confirm port 5002 is free:
   ```bash
   lsof -i :5002 | head -3
   # (no output expected)
   ```

## Step 1 — Boot fix-branch backend on port 5002 (5 min including model warm-up)

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai-v6fix"

# Bring up the venv (re-using main folder's venv — no IPC conflict, just imports)
source "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/activate"

# Load .env from main folder (FLASK_SECRET_KEY etc.)
set -a
source "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/.env"
set +a

# Point to a separate data dir so we don't share registry/uploads/db with main backend
export DATA_DIR="/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai-v6fix/backend/data"
mkdir -p "$DATA_DIR"

# Alt port + (optional) tune the new timeout to a value you want exercised
export FLASK_PORT=5002
export R5_QWEN3_TIMEOUT_SEC=900    # change if you want shorter for quicker timeout test

cd backend
python -u app.py 2>&1 | tee /tmp/backend-5002.log
```

You should see boot lines including `faster-whisper available`, model load lines, and `* Running on http://...:5002`. **Leave this terminal open.**

## Step 2 — Bootstrap an admin user on port 5002 (one-time, 30 sec)

In another terminal:
```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai-v6fix/backend"
source "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/activate"
export DATA_DIR="/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai-v6fix/backend/data"
python - <<'PY'
import os
os.environ.setdefault("AUTH_DB_PATH", os.path.join(os.environ["DATA_DIR"], "app.db"))
from auth.users import init_db, create_user
init_db(os.environ["AUTH_DB_PATH"])
try:
    create_user("admin", "ChangeMe-Local-T6!", is_admin=True)
    print("admin created")
except Exception as e:
    print(f"admin already exists or error: {e}")
PY
```

## Step 3 — Login + copy the stuck file into the alt registry (2 min)

The original mp4 still sits at `whisper-subtitle-ai/backend/data/users/627/uploads/183e38257865.mp4` (34.6 MB). Easiest path is to **re-upload** it via the browser:

1. Open `http://localhost:5002/` in browser.
2. Login as `admin` / `ChangeMe-Local-T6!`.
3. Activate the V6 Cantonese preset — but **the alt data dir is empty**, so first re-import the pipeline. Either:
   - **Option A (simplest)**: in the V6 fix terminal, copy across the pipeline/refiner/transcribe profiles you need:
     ```bash
     # Copy V6 [v6] 賽馬廣播 (Cantonese) + its refiner + transcribe profile
     SRC="/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/config"
     DST="/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai-v6fix/backend/config"
     mkdir -p "$DST/pipelines" "$DST/refiner_profiles" "$DST/transcribe_profiles" "$DST/llm_profiles"
     cp "$SRC/pipelines/4696bbaa-b988-49bd-859c-e742cb365634.json" "$DST/pipelines/"
     # refiner profile (the one referenced inside the pipeline)
     cp "$SRC/refiner_profiles/f7f72bd9-3f27-47a4-92bd-5727f336916a.json" "$DST/refiner_profiles/" 2>/dev/null || true
     cp "$SRC/transcribe_profiles/82338761-e6ed-47eb-b153-64789ed7327e.json" "$DST/transcribe_profiles/" 2>/dev/null || true
     ```
     Then **restart the port-5002 backend** to reload configs.
   - **Option B**: dispatch a one-off pipeline JSON via API. Slower path; skip unless A fails.
4. Set active: top-right Pipeline menu → `Dual-ASR Pipeline (V6)` → `[v6] 賽馬廣播 (Cantonese)`.
5. Drag the file `183e38257865.mp4` into the upload zone (or use the file picker).

## Step 4 — Watch the run (4-8 min wall time)

Trigger upload → V6 pipeline kicks off automatically.

What you'll see if the fix is working:
- Within ~5s: file card flips to `transcribing` with a queue badge
- VAD stage completes quickly (~5s)
- **Stage 1A Qwen3 progress lines appear in `tail -f /tmp/backend-5002.log`** (T7 hook forwards `[region N] …` lines through `socketio.emit("pipeline_stage_progress", …)`). You should also see them in the browser DevTools Network → WS frames (filter `pipeline_stage_progress`).
- Per-region throughput: ~5-15s/region on Apple Silicon
- Stage 1B mlx-whisper runs in parallel-ish: ~30-60s total
- Stage 3 refiner: ~30-60s for ~100 segments
- File card flips to `done` / segments populated

## Step 5 — Capture metrics + write the integration report

After completion (or after T6 plateau if it doesn't complete), gather:

```bash
# In the port-5002 backend terminal — Ctrl+C to stop, then:
grep -E "Stage|stage_done|qwen3|refiner|elapsed" /tmp/backend-5002.log | tail -60

# Job timing from DB:
sqlite3 "$DATA_DIR/app.db" \
  "SELECT id, type, status, started_at, finished_at, (finished_at - started_at) AS dur_sec, attempt_count
   FROM jobs WHERE file_id LIKE '%183e3%' OR file_id LIKE '%gamehub%' OR type IN ('asr','translate')
   ORDER BY created_at DESC LIMIT 5"
```

Then create `docs/superpowers/validation/2026-05-29-v6-ipc-fix-report.md` with this template:

```markdown
# T6 Integration Report — Live Replay

## Setup
- Backend: fix/v6-subprocess-ipc @ <commit SHA>
- Port: 5002 (alt instance)
- File: gamehub-…赤色沙漠.mp4 (34.6 MB, ~4-min Cantonese broadcast)
- Pipeline: [v6] 賽馬廣播 (Cantonese)
- R5_QWEN3_TIMEOUT_SEC: 900

## Before (incident snapshot from 2026-05-29 16:20)
- ASR job 2f6198039fef…: status=running, started=16:20:29, NEVER COMPLETED
- Wall time at investigation: 9 min, zero stage progress visible
- Qwen3 subprocess wedged in write() syscall

## After (this run)
- ASR job <new id>: status=<done/failed/timeout>
- Wall time: <X>s
- Stage breakdown (from log):
  - VAD: <X>s
  - Qwen3 per-region (×N): <X>s
  - mlx-whisper full: <X>s
  - Refiner: <X>s
- Per-region progress events forwarded to SocketIO: yes / no
- segments[] count: <N>
- text length: <chars>

## Verdict
- ✅ Completes within ≤600s budget: yes/no
- ✅ No deadlock observed: yes/no
- ✅ Progress visible to client: yes/no

## Sample output (first 3 segments)
<paste>
```

## Step 6 — Cleanup

If integration passes:
```bash
# Stop port-5002 backend (Ctrl+C in that terminal)
# Optionally clear the alt data dir if you want to leave the worktree pristine:
rm -rf "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai-v6fix/backend/data"
```

## Troubleshooting

- **Port 5002 already in use**: change `FLASK_PORT` to 5003+ or kill old instance with `lsof -i :5002` → `kill <PID>`.
- **`ModuleNotFoundError: silero_vad`**: install in the borrowed venv: `pip install silero-vad>=6.2.1`.
- **Qwen3 subprocess fails with `mlx_qwen3_asr` not found**: the worktree shares the `backend/scripts/v5_prototype/venv_qwen/` only if you point to main folder's. Add this BEFORE Step 1:
  ```bash
  ln -s "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/scripts/v5_prototype/venv_qwen" \
        "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai-v6fix/backend/scripts/v5_prototype/venv_qwen"
  ```
- **No SocketIO progress events**: confirm `pipeline_stage_progress` is listed in `_socketio_emit` calls — should be from T7. Frontend listener exists from v3.19 V6 merge but may need DevTools to verify reception.
- **Job hangs again (deadlock not fixed)**: not expected, but if it happens, `sample <child_pid>` to confirm where; the fix should have replaced the deadlock-prone poll loop. Compare against `qwen3_vad_engine.py:_drain_subprocess` to confirm the fix is actually in the running code.

## What "PASS" looks like for T6

Numeric thresholds (set in spec §2):
- Total V6 wall time ≤ 600s (1.5× healthy 4-6 min budget)
- `segments[]` length > 50 (Cantonese broadcast at ~5s/segment = ~50+ for 4 min audio)
- Job DB row `status='done'`, `error_msg IS NULL`
- No process named `qwen3_vad_subprocess.py` left over after run

If T6 passes, hand control back and I'll dispatch Agent-Docs (T8 + T9). If T6 fails, file the failure mode in the integration report and we'll iterate.
