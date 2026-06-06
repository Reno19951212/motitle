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
