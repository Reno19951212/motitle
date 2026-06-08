# macOS Server Packaging Implementation Plan (Phase 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.
>
> **⚠️ INTRUSIVE STEPS:** Tasks 4–6 install/load real launchd **system** services (require `sudo`, write to `/Library/LaunchDaemons`, pull a large Ollama model). When executing, run the service-install verification ONLY when the operator explicitly consents to register services on this machine. File-creation + script-syntax tasks (1–4 authoring, 7) are non-intrusive.

**Goal:** Turn the existing `setup-mac.sh` into a complete macOS Apple-Silicon **server appliance** install: one script provisions everything (venv + mlx-whisper + ffmpeg + Ollama + model), and two launchd LaunchDaemons keep the app + Ollama running at boot (RunAtLoad/KeepAlive, sleep-prevented), reachable on the LAN at `https?://<mac>:5001`.

**Architecture:** Keep the MLX model stack unchanged (no model code touched → no Validation-First gate). Add a `packaging/macos/` directory with a launcher script, two plist templates, and a `motitle-service.sh` management CLI. Extend `setup-mac.sh` to auto-install ffmpeg/Ollama, disk-check + pull the model, and optionally register the services. No Apple Developer ID / code-signing (script-based install).

**Tech Stack:** bash, launchd (`launchctl bootstrap`/`bootout`/`kickstart`), Homebrew (`ffmpeg`, `ollama`), `caffeinate`, the existing Flask/SocketIO `python app.py` entrypoint.

**Key constraints (from ops memory + audit):**
- App crashes at startup without `FLASK_SECRET_KEY` → launcher MUST load `backend/.env`.
- A stale capital-`Python` process can squat port 5001 → management script must detect/handle.
- Bind `0.0.0.0` for LAN; macOS firewall prompts on first listen.
- LaunchDaemon plists must be `root:wheel`, not group/other-writable, or launchd refuses them.
- Homebrew prefix on Apple Silicon is `/opt/homebrew`.

---

### Task 1: launcher script (the process the daemon runs)

**Files:**
- Create: `packaging/macos/motitle-launcher.sh`

- [ ] **Step 1: Write the launcher**

```bash
#!/usr/bin/env bash
# motitle-launcher.sh — the long-running process launchd supervises.
# Loads FLASK_SECRET_KEY from backend/.env, activates the venv, binds 0.0.0.0,
# and runs the Flask/SocketIO server under caffeinate (no idle/system sleep).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"

cd "$BACKEND_DIR"

# --- required secret (app aborts without it) ---
if [[ ! -f .env ]]; then
  echo "[motitle] FATAL: $BACKEND_DIR/.env missing (run setup-mac.sh)" >&2
  exit 1
fi
FLASK_SECRET_KEY="$(grep -E '^FLASK_SECRET_KEY=' .env | cut -d= -f2-)"
if [[ -z "${FLASK_SECRET_KEY:-}" ]]; then
  echo "[motitle] FATAL: FLASK_SECRET_KEY empty in .env" >&2
  exit 1
fi
export FLASK_SECRET_KEY

# --- optional .env passthroughs ---
for _k in R5_HTTPS R5_HTTPS_CERT_DIR R5_OLLAMA_URL R5_ASR_BACKEND R5_OLLAMA_MODEL; do
  _v="$(grep -E "^${_k}=" .env | cut -d= -f2- || true)"
  [[ -n "${_v:-}" ]] && export "${_k}=${_v}"
done

# --- LAN bind ---
export BIND_HOST="${BIND_HOST:-0.0.0.0}"
export FLASK_PORT="${FLASK_PORT:-5001}"

# Homebrew tools (ffmpeg, ollama) on PATH for the daemon context
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

source venv/bin/activate

# caffeinate keeps the Mac awake while the server runs; exec so launchd
# supervises caffeinate (python is its child); KeepAlive restarts on exit.
exec caffeinate -is python app.py
```

- [ ] **Step 2: Make executable + syntax-check**

```bash
chmod +x packaging/macos/motitle-launcher.sh
bash -n packaging/macos/motitle-launcher.sh && echo "syntax OK"
```
Expected: `syntax OK`

- [ ] **Step 3: Commit**

```bash
git add packaging/macos/motitle-launcher.sh
git commit -m "feat(macos): launchd launcher script (env load + 0.0.0.0 + caffeinate)"
```

---

### Task 2: app server LaunchDaemon plist template

**Files:**
- Create: `packaging/macos/com.motitle.server.plist.template`

- [ ] **Step 1: Write the template** (tokens `__USER__`, `__REPO__` are filled by the installer)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.motitle.server</string>
    <key>UserName</key>
    <string>__USER__</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>__REPO__/packaging/macos/motitle-launcher.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>__REPO__/backend</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>__REPO__/backend/data/logs/server.out.log</string>
    <key>StandardErrorPath</key>
    <string>__REPO__/backend/data/logs/server.err.log</string>
</dict>
</plist>
```

- [ ] **Step 2: Validate it is well-formed XML once tokens are substituted (dry run)**

```bash
sed -e "s|__USER__|$(whoami)|g" -e "s|__REPO__|$(pwd)|g" \
  packaging/macos/com.motitle.server.plist.template | plutil -lint -
```
Expected: `- : OK` (plutil reads the substituted plist from stdin)

- [ ] **Step 3: Commit**

```bash
git add packaging/macos/com.motitle.server.plist.template
git commit -m "feat(macos): app server LaunchDaemon plist template"
```

---

### Task 3: Ollama LaunchDaemon plist template

**Files:**
- Create: `packaging/macos/com.motitle.ollama.plist.template`

- [ ] **Step 1: Write the template** (tokens `__USER__`, `__OLLAMA_BIN__`, `__REPO__`)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.motitle.ollama</string>
    <key>UserName</key>
    <string>__USER__</string>
    <key>ProgramArguments</key>
    <array>
        <string>__OLLAMA_BIN__</string>
        <string>serve</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>OLLAMA_HOST</key>
        <string>0.0.0.0:11434</string>
        <key>OLLAMA_KEEP_ALIVE</key>
        <string>30m</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>__REPO__/backend/data/logs/ollama.out.log</string>
    <key>StandardErrorPath</key>
    <string>__REPO__/backend/data/logs/ollama.err.log</string>
</dict>
</plist>
```

- [ ] **Step 2: Dry-run lint**

```bash
sed -e "s|__USER__|$(whoami)|g" -e "s|__OLLAMA_BIN__|/opt/homebrew/bin/ollama|g" -e "s|__REPO__|$(pwd)|g" \
  packaging/macos/com.motitle.ollama.plist.template | plutil -lint -
```
Expected: `- : OK`

- [ ] **Step 3: Commit**

```bash
git add packaging/macos/com.motitle.ollama.plist.template
git commit -m "feat(macos): Ollama LaunchDaemon plist template (0.0.0.0:11434)"
```

---

### Task 4: service management CLI

**Files:**
- Create: `packaging/macos/motitle-service.sh`

- [ ] **Step 1: Write the management script**

```bash
#!/usr/bin/env bash
# motitle-service.sh — install/manage the MoTitle macOS LaunchDaemons.
# Usage: sudo ./motitle-service.sh <install|uninstall|start|stop|restart|status|logs>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LDAEMONS="/Library/LaunchDaemons"
SERVER_LABEL="com.motitle.server"
OLLAMA_LABEL="com.motitle.ollama"
PORT="${FLASK_PORT:-5001}"

# The non-root user the daemons run as. When invoked via sudo, SUDO_USER is the
# real operator; fall back to whoami otherwise.
INSTALL_USER="${SUDO_USER:-$(whoami)}"
OLLAMA_BIN="$(command -v ollama || echo /opt/homebrew/bin/ollama)"

_need_root() { [[ "$(id -u)" == "0" ]] || { echo "Run with sudo." >&2; exit 1; }; }

_render() {
  # _render <template> <dest>
  sed -e "s|__USER__|${INSTALL_USER}|g" \
      -e "s|__REPO__|${REPO_ROOT}|g" \
      -e "s|__OLLAMA_BIN__|${OLLAMA_BIN}|g" \
      "$1" > "$2"
  chown root:wheel "$2"
  chmod 644 "$2"
}

cmd_install() {
  _need_root
  mkdir -p "${REPO_ROOT}/backend/data/logs"
  chown "${INSTALL_USER}" "${REPO_ROOT}/backend/data/logs"
  # Avoid conflict with a Homebrew-managed ollama service
  sudo -u "${INSTALL_USER}" brew services stop ollama 2>/dev/null || true
  _render "${SCRIPT_DIR}/com.motitle.ollama.plist.template" "${LDAEMONS}/${OLLAMA_LABEL}.plist"
  _render "${SCRIPT_DIR}/com.motitle.server.plist.template" "${LDAEMONS}/${SERVER_LABEL}.plist"
  launchctl bootstrap system "${LDAEMONS}/${OLLAMA_LABEL}.plist"
  launchctl bootstrap system "${LDAEMONS}/${SERVER_LABEL}.plist"
  echo "Installed + loaded: ${OLLAMA_LABEL}, ${SERVER_LABEL}"
}

cmd_uninstall() {
  _need_root
  launchctl bootout "system/${SERVER_LABEL}" 2>/dev/null || true
  launchctl bootout "system/${OLLAMA_LABEL}" 2>/dev/null || true
  rm -f "${LDAEMONS}/${SERVER_LABEL}.plist" "${LDAEMONS}/${OLLAMA_LABEL}.plist"
  echo "Uninstalled."
}

cmd_start()   { _need_root; launchctl kickstart  "system/${OLLAMA_LABEL}"; launchctl kickstart  "system/${SERVER_LABEL}"; echo "started"; }
cmd_stop()    { _need_root; launchctl kill SIGTERM "system/${SERVER_LABEL}" 2>/dev/null || true; launchctl kill SIGTERM "system/${OLLAMA_LABEL}" 2>/dev/null || true; echo "stopped"; }
cmd_restart() { _need_root; launchctl kickstart -k "system/${OLLAMA_LABEL}"; launchctl kickstart -k "system/${SERVER_LABEL}"; echo "restarted"; }

cmd_status() {
  echo "== launchd =="
  launchctl print "system/${SERVER_LABEL}" 2>/dev/null | grep -E "state =|pid =" || echo "${SERVER_LABEL}: not loaded"
  launchctl print "system/${OLLAMA_LABEL}" 2>/dev/null | grep -E "state =|pid =" || echo "${OLLAMA_LABEL}: not loaded"
  echo "== health =="
  curl -sk "http://localhost:${PORT}/api/ready" || echo "(server not responding on ${PORT})"
  echo ""
  "${OLLAMA_BIN}" ps 2>/dev/null || echo "(ollama not responding)"
}

cmd_logs() {
  tail -n 50 -F "${REPO_ROOT}/backend/data/logs/server.err.log" "${REPO_ROOT}/backend/data/logs/server.out.log"
}

case "${1:-}" in
  install)   cmd_install ;;
  uninstall) cmd_uninstall ;;
  start)     cmd_start ;;
  stop)      cmd_stop ;;
  restart)   cmd_restart ;;
  status)    cmd_status ;;
  logs)      cmd_logs ;;
  *) echo "Usage: sudo $0 <install|uninstall|start|stop|restart|status|logs>"; exit 1 ;;
esac
```

- [ ] **Step 2: Make executable + syntax-check (non-intrusive)**

```bash
chmod +x packaging/macos/motitle-service.sh
bash -n packaging/macos/motitle-service.sh && echo "syntax OK"
packaging/macos/motitle-service.sh 2>&1 | grep -q "Usage:" && echo "usage OK"
```
Expected: `syntax OK` then `usage OK` (running with no arg prints usage and exits non-zero; the grep still succeeds).

- [ ] **Step 3: Commit**

```bash
git add packaging/macos/motitle-service.sh
git commit -m "feat(macos): launchd service management CLI (install/status/logs)"
```

---

### Task 5: enhance setup-mac.sh — ffmpeg + Ollama + model pull (idempotent)

**Files:**
- Modify: `setup-mac.sh`

- [ ] **Step 1: Replace the prerequisite + venv section**

Current `setup-mac.sh` lines 12–23 hard-require ffmpeg and unconditionally rebuild the venv. Replace lines 12–23 with an idempotent, auto-installing block:

```bash
# --- Prerequisites (auto-install via Homebrew when missing) ---
command -v brew >/dev/null || { echo "Homebrew required: https://brew.sh"; exit 1; }
command -v python3 >/dev/null || brew install python@3.11
command -v ffmpeg  >/dev/null || brew install ffmpeg
command -v ollama  >/dev/null || brew install ollama

# Backend venv (idempotent — reuse if mlx-whisper already imports)
cd backend
if [[ -d venv ]] && venv/bin/python -c "import mlx_whisper" 2>/dev/null; then
  echo "venv present and mlx-whisper importable — skipping rebuild"
  source venv/bin/activate
else
  python3 -m venv venv
  # shellcheck disable=SC1091
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  pip install mlx-whisper
fi
```

- [ ] **Step 2: Add the model-pull block with a disk check** — insert AFTER the HTTPS cert step (after current line 63), before the final "Setup complete." line:

```bash
echo ""
echo "=== Ollama model (qwen3.5:35b-a3b-mlx-bf16) ==="
MODEL_TAG="qwen3.5:35b-a3b-mlx-bf16"
# bf16 35B is large (~70GB); require generous free space on the boot volume.
NEED_GB=90
FREE_GB=$(df -g / | awk 'NR==2 {print $4}')
if ollama list 2>/dev/null | grep -q "qwen3.5:35b-a3b-mlx-bf16"; then
  echo "Model already pulled — skipping."
elif (( FREE_GB < NEED_GB )); then
  echo "WARNING: only ${FREE_GB}GB free (need ~${NEED_GB}GB for ${MODEL_TAG})."
  echo "  Free up space then run:  ollama pull ${MODEL_TAG}"
else
  echo "Pulling ${MODEL_TAG} (large download)…"
  ollama pull "${MODEL_TAG}"
fi
```

- [ ] **Step 3: Syntax-check (non-intrusive — do NOT run the script itself)**

```bash
bash -n setup-mac.sh && echo "syntax OK"
```
Expected: `syntax OK`

- [ ] **Step 4: Commit**

```bash
git add setup-mac.sh
git commit -m "feat(macos): setup-mac.sh auto-installs ffmpeg/ollama + idempotent venv + model pull"
```

---

### Task 6: setup-mac.sh — optional service registration + final runbook output

**Files:**
- Modify: `setup-mac.sh`

- [ ] **Step 1: Append a service-install prompt** at the very end (after "Setup complete."):

```bash
echo ""
echo "=== Auto-start service (launchd) ==="
echo "Install MoTitle + Ollama as boot services (survives reboot, restarts on crash)?"
read -p "Install launchd services now? [y/N]: " INSTALL_SVC
if [[ "${INSTALL_SVC:-N}" =~ ^[Yy]$ ]]; then
  sudo "$(cd "$(dirname "$0")" && pwd)/packaging/macos/motitle-service.sh" install
  echo ""
  echo "Service installed. Check:  sudo packaging/macos/motitle-service.sh status"
else
  echo "Skipped. To install later:  sudo packaging/macos/motitle-service.sh install"
  echo "Or run in foreground:        ./start.sh"
fi

IP=$(ipconfig getifaddr en0 2>/dev/null || echo "<this-mac-ip>")
echo ""
echo "=================================================="
echo "  Clients on the LAN open:  http://${IP}:5001"
echo "  (first connection may trigger a macOS firewall prompt — Allow)"
echo "=================================================="
```

- [ ] **Step 2: Syntax-check**

```bash
bash -n setup-mac.sh && echo "syntax OK"
```
Expected: `syntax OK`

- [ ] **Step 3 (OPTIONAL, INTRUSIVE — only with operator consent on a real Mac):** End-to-end install verification

```bash
# Registers REAL system services + pulls the model. Only run if you intend to.
./setup-mac.sh                         # answer 'y' to the service prompt
sudo packaging/macos/motitle-service.sh status
# Expected: server state=running with a pid; curl /api/ready returns {"ready":true};
#           `ollama ps` lists the model. Then from another LAN device:
#           open http://<mac-ip>:5001  → login page loads.
sudo packaging/macos/motitle-service.sh logs   # tails server logs
```
If not consenting to install, SKIP this step and note it as deferred.

- [ ] **Step 4: Commit**

```bash
git add setup-mac.sh
git commit -m "feat(macos): setup-mac.sh optional launchd service install + LAN URL hint"
```

---

### Task 7: operator runbook + docs

**Files:**
- Create: `docs/deployment/macos-server.md`
- Modify: `CLAUDE.md` (add a "macOS server deployment" pointer), `README.md` (繁體 operator section)

- [ ] **Step 1: Write `docs/deployment/macos-server.md`** with these sections (full prose, no placeholders): Prerequisites (Apple Silicon, Homebrew, ~90GB free, RAM note for bf16); Install (`./setup-mac.sh`, what it does, admin bootstrap, model pull); Service management (`sudo packaging/macos/motitle-service.sh install|status|restart|logs|uninstall`); LAN access (`http://<mac-ip>:5001`, firewall Allow, stable IP / `<name>.local`); Troubleshooting (FLASK_SECRET_KEY missing → check `backend/.env`; stale capital-`Python` squatting 5001 → `lsof -i :5001` then `sudo packaging/macos/motitle-service.sh restart`; HTTPS self-signed cert note; sleep prevention via caffeinate in the daemon); Uninstall.

- [ ] **Step 2: Add to `CLAUDE.md`** a one-line pointer under deployment/Current State referencing `docs/deployment/macos-server.md` and the `packaging/macos/` directory.

- [ ] **Step 3: Add a 繁體中文 operator section to `README.md`** ("macOS 伺服器部署") summarising install + service commands + LAN URL.

- [ ] **Step 4: Commit**

```bash
git add docs/deployment/macos-server.md CLAUDE.md README.md
git commit -m "docs(macos): server deployment runbook + CLAUDE.md/README pointers"
```

---

## Self-Review (against design §5.1)

**Coverage:**
- "增強 setup-mac.sh (auto Ollama + pull 模型 + 磁碟檢查)" → Task 5 ✅
- "launchd LaunchDaemon (app + Ollama, RunAtLoad/KeepAlive/防睡眠)" → Tasks 1–3 (launcher caffeinate, two plist templates) ✅
- "start/stop/status 管理腳本" → Task 4 ✅
- "operator runbook" → Task 7 ✅
- FLASK_SECRET_KEY load → Task 1 launcher ✅
- stale-Python port squat → Task 7 troubleshooting + `status`/`restart` in Task 4 ✅
- 0.0.0.0 LAN bind + firewall note → Task 1 + Task 6 ✅
- root:wheel plist perms → Task 4 `_render` ✅
- No model code touched → confirmed (only packaging + setup) → no Validation-First gate ✅

**Placeholder scan:** every file has full content; no TBD. ✅

**Consistency:** labels `com.motitle.server` / `com.motitle.ollama`, token names `__USER__`/`__REPO__`/`__OLLAMA_BIN__`, and `motitle-service.sh` subcommands are identical across Tasks 2–6. ✅

**Out of scope (noted):** signed `.pkg`/notarization (deferred — operator chose script install); bundling a vendored arm64 ffmpeg (uses Homebrew ffmpeg per operator choice); Windows/GB10/Phase-0 (pending hardware).

**Intrusiveness flagged:** Tasks 1–4 authoring + Task 7 are safe to run anywhere. Task 5 model pull and Task 6 Step 3 register real services / download ~70GB — execute only with explicit operator consent on the target Mac.
