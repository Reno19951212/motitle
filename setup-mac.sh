#!/usr/bin/env bash
# setup-mac.sh — macOS Apple Silicon installer (R5 Phase 1)
# Provisions venv + mlx-whisper, bootstraps an admin user, and writes
# backend/.env with a freshly-generated FLASK_SECRET_KEY.
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "ERROR: This script targets Apple Silicon (arm64). For Intel Mac, use setup.sh"
  exit 1
fi

# --- macOS privacy (TCC) guard ---
# Background services (launchd) CANNOT execute files under ~/Documents, ~/Desktop
# or ~/Downloads — they fail at boot with "Operation not permitted" and crash-loop.
# Catch it HERE, before building the venv, so relocating is cheap (no broken venv).
case "${SCRIPT_ROOT}/" in
  "$HOME"/Documents/*|"$HOME"/Desktop/*|"$HOME"/Downloads/*)
    echo "ERROR: $SCRIPT_ROOT is under a macOS privacy-protected folder"
    echo "(Documents / Desktop / Downloads). A background service (launchd) cannot run"
    echo "from here — you'd hit 'Operation not permitted'. Move the app to /opt first:"
    echo ""
    echo "  sudo mv \"$SCRIPT_ROOT\" /opt/motitle"
    echo "  sudo chown -R \"$(whoami)\" /opt/motitle"
    echo "  cd /opt/motitle && ./setup-mac.sh"
    exit 1
    ;;
esac

# --- Prerequisites ---
if ! command -v brew >/dev/null; then
  echo "Homebrew not found — installing (you'll be asked to press Return + your password)…"
  /bin/bash -c "$(/usr/bin/curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    || { echo "ERROR: Homebrew install failed — install it from https://brew.sh then re-run."; exit 1; }
  # Put brew on PATH for the rest of this script (Apple Silicon prefix).
  eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
fi
# ffmpeg WITH libass — subtitle burn-in uses the `ass` filter. Homebrew's lean
# `ffmpeg` formula no longer bundles libass (the `ass`/`subtitles` filters are
# missing → render fails), so use `ffmpeg-full` (keg-only; force-link onto PATH).
if ! ffmpeg -hide_banner -h filter=ass 2>&1 | grep -qi "^Filter ass"; then
  echo "Installing ffmpeg-full (libass for subtitle burn-in)…"
  brew install ffmpeg-full || { echo "ERROR: brew install ffmpeg-full failed"; exit 1; }
  brew unlink ffmpeg >/dev/null 2>&1 || true
  brew link --overwrite --force ffmpeg-full >/dev/null 2>&1 || true
fi
command -v ollama >/dev/null || brew install ollama || { echo "ERROR: brew install ollama failed"; exit 1; }
# uv provides a self-contained standalone CPython for the venv. Do NOT rely on
# brew's python: on bleeding-edge macOS its pyexpat can fail to load (a libexpat
# symbol mismatch), which breaks pip/venv creation entirely.
command -v uv >/dev/null || brew install uv || { echo "ERROR: brew install uv failed"; exit 1; }

# Backend venv (idempotent — reuse if mlx-whisper already imports)
cd backend
# Runtime dirs must exist before init_db / cert / logs write into them
# (a fresh checkout has no data/ — it is gitignored).
mkdir -p data data/certs data/logs data/uploads data/results data/renders
if [[ -d venv ]] && venv/bin/python -c "import mlx_whisper" 2>/dev/null; then
  echo "venv present and mlx-whisper importable — skipping rebuild"
  source venv/bin/activate
else
  # Self-contained Python 3.11 via uv (bundles its own expat/ssl).
  uv venv --seed --python 3.11 venv || { echo "ERROR: uv venv failed"; exit 1; }
  # shellcheck disable=SC1091
  source venv/bin/activate
  # NB: whisper-streaming is intentionally NOT in requirements.txt — it pulls
  # Linux-only pyalsaaudio and cannot build on macOS/Windows; streaming was
  # removed in v2.0 and its import is guarded in app.py.
  uv pip install -r requirements.txt || { echo "ERROR: dependency install failed"; exit 1; }
  uv pip install mlx-whisper || { echo "ERROR: mlx-whisper install failed"; exit 1; }
fi

# Validate PyNaCl (licensing gate) actually imports — a failed native build on
# arm64 can leave pip exit 0 but the app crashes at boot importing `nacl`.
python -c "from nacl.signing import SigningKey" 2>/dev/null \
  || { echo "ERROR: PyNaCl import failed (licensing needs it). Try: pip install --force-reinstall PyNaCl"; exit 1; }

# Bootstrap admin — loop until a valid admin exists; do NOT silently skip a
# weak/mismatched password (that previously left the DB with zero accounts and
# nobody able to log in).
echo ""
echo "=== Set up admin user ==="
if python -c "import sys; from auth.users import init_db, count_admins; init_db('data/app.db'); sys.exit(0 if count_admins('data/app.db') > 0 else 1)" 2>/dev/null; then
  echo "An admin already exists — skipping admin creation."
else
  while true; do
    read -p "Admin username [admin]: " ADMIN_USER
    ADMIN_USER=${ADMIN_USER:-admin}
    read -s -p "Admin password (min 8 chars, not a common password): " ADMIN_PW
    echo ""
    read -s -p "Confirm password: " ADMIN_PW2
    echo ""
    if [[ "$ADMIN_PW" != "$ADMIN_PW2" ]]; then
      echo "  Passwords don't match — try again."
      continue
    fi
    # Pass via env (NOT string interpolation) so quotes / metacharacters are safe.
    if ADMIN_USER="$ADMIN_USER" ADMIN_PW="$ADMIN_PW" python -c "
import os, sys
from auth.users import init_db, create_user
init_db('data/app.db')
try:
    create_user('data/app.db', os.environ['ADMIN_USER'], os.environ['ADMIN_PW'], is_admin=True)
    print('  Admin created.')
except Exception as e:
    print(f'  REJECTED: {e}')
    sys.exit(1)
"; then
      break
    fi
    echo "  Please try again with a stronger password (or a different username)."
  done
fi

echo ""
echo "=== Flask SECRET_KEY ==="
# Preserve an existing key on re-run — overwriting would rotate the secret
# (invalidating sessions) AND wipe other vars like OPENROUTER_API_KEY.
if [[ -f .env ]] && grep -q '^FLASK_SECRET_KEY=' .env; then
  echo "FLASK_SECRET_KEY already in backend/.env — keeping it (and any other vars)."
else
  SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
  printf 'FLASK_SECRET_KEY=%s\n' "$SECRET" >> .env   # append, don't clobber
  echo "Generated FLASK_SECRET_KEY into backend/.env."
fi
chmod 600 .env
echo "Saved backend/.env (gitignored). Source it before running app.py:"
echo ""
echo "  source backend/.env && cd backend && source venv/bin/activate && python app.py"
echo ""
echo "=== Generate self-signed HTTPS cert ==="
python scripts/generate_https_cert.py data/certs && \
  echo "Cert: backend/data/certs/server.crt" || \
  echo "Cert generation failed (HTTPS will be disabled; install mkcert or openssl to enable)"
echo ""
echo "Core setup complete (venv, admin, secret, cert)."

echo ""
echo "=== Auto-start service (launchd) ==="
echo "Install MoTitle + Ollama as boot services (survives reboot, restarts on crash)?"
read -p "Install launchd services now? [y/N]: " INSTALL_SVC
if [[ "${INSTALL_SVC:-N}" =~ ^[Yy]$ ]]; then
  sudo "${SCRIPT_ROOT}/packaging/macos/motitle-service.sh" install
  echo ""
  echo "Service installed. Check:  sudo packaging/macos/motitle-service.sh status"
else
  echo "Skipped. To install later:  sudo packaging/macos/motitle-service.sh install"
  echo "Or run in foreground:        ./start.sh"
fi

# --- Ollama model (done AFTER the service decision on purpose) ---
# Pulling here means the download runs against the now-stable ollama server
# (the motitle launchd daemon if the service was installed), so installing the
# service can't interrupt an in-progress pull. It runs in the BACKGROUND, so the
# install never waits ~70GB before finishing.
echo ""
echo "=== Ollama model (qwen3.5:35b-a3b-mlx-bf16) ==="
MODEL_TAG="qwen3.5:35b-a3b-mlx-bf16"
NEED_GB=90
FREE_GB=$(df -g / | awk 'NR==2 {print $4}')
[[ "$FREE_GB" =~ ^[0-9]+$ ]] || FREE_GB=0
mkdir -p data/logs
# Ensure an ollama server is reachable (a fresh brew install does not auto-start
# one; the motitle daemon, if installed, is already up on 0.0.0.0:11434).
if ! ollama list >/dev/null 2>&1; then
  brew services start ollama >/dev/null 2>&1 || (ollama serve >/dev/null 2>&1 &)
  for _i in $(seq 1 15); do ollama list >/dev/null 2>&1 && break; sleep 1; done
fi
if ollama list 2>/dev/null | grep -q "qwen3.5:35b-a3b-mlx-bf16"; then
  echo "Model already pulled — skipping."
elif (( FREE_GB < NEED_GB )); then
  echo "WARNING: only ${FREE_GB}GB free (need ~${NEED_GB}GB). Skipping model pull."
  echo "  Free space then run:  ollama pull ${MODEL_TAG}"
else
  echo "Pulling ${MODEL_TAG} in the BACKGROUND (~70GB) — install does not wait."
  echo "  Watch progress:  tail -f \"$(pwd)/data/logs/ollama-pull.log\"   (or: ollama list)"
  nohup ollama pull "${MODEL_TAG}" > data/logs/ollama-pull.log 2>&1 &
fi

IP=$(ipconfig getifaddr en0 2>/dev/null || echo "<this-mac-ip>")
echo ""
echo "=================================================="
echo "  Clients on the LAN open:  http://${IP}:5001"
echo "  (first connection may trigger a macOS firewall prompt — Allow)"
echo ""
echo "  ⚠️  LICENSE REQUIRED: this build gates AI features behind a license."
echo "      On first open the app redirects to a License Activation page."
echo "      Log in as admin, copy the install ID, get a signed token from the"
echo "      vendor, then paste it at  http://${IP}:5001/license.html"
echo "      Full steps: docs/deployment/macos-server.md (License Activation)."
echo "=================================================="
