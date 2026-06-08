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

# --- Prerequisites (auto-install via Homebrew when missing) ---
command -v brew >/dev/null || { echo "Homebrew required: https://brew.sh"; exit 1; }
command -v python3 >/dev/null || brew install python@3.11 || { echo "ERROR: brew install python@3.11 failed"; exit 1; }
command -v ffmpeg  >/dev/null || brew install ffmpeg || { echo "ERROR: brew install ffmpeg failed"; exit 1; }
command -v ollama  >/dev/null || brew install ollama || { echo "ERROR: brew install ollama failed"; exit 1; }

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

# Validate PyNaCl (licensing gate) actually imports — a failed native build on
# arm64 can leave pip exit 0 but the app crashes at boot importing `nacl`.
python -c "from nacl.signing import SigningKey" 2>/dev/null \
  || { echo "ERROR: PyNaCl import failed (licensing needs it). Try: pip install --force-reinstall PyNaCl"; exit 1; }

# Bootstrap admin
echo ""
echo "=== Set up admin user ==="
read -p "Admin username [admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}
read -s -p "Admin password: " ADMIN_PW
echo ""
read -s -p "Confirm password: " ADMIN_PW2
echo ""
[[ "$ADMIN_PW" == "$ADMIN_PW2" ]] || { echo "Passwords don't match"; exit 1; }

# Pass username + password via env (NOT string interpolation) so values
# containing quotes / shell metacharacters can't break out.
ADMIN_USER="$ADMIN_USER" ADMIN_PW="$ADMIN_PW" python -c "
import os
from auth.users import init_db, create_user
init_db('data/app.db')
try:
    create_user('data/app.db',
                os.environ['ADMIN_USER'],
                os.environ['ADMIN_PW'],
                is_admin=True)
    print('Admin created.')
except ValueError as e:
    print(f'Skipped: {e}')
"

echo ""
echo "=== Generate Flask SECRET_KEY ==="
SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
echo "FLASK_SECRET_KEY=$SECRET" > .env
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
echo "=== Ollama model (qwen3.5:35b-a3b-mlx-bf16) ==="
MODEL_TAG="qwen3.5:35b-a3b-mlx-bf16"
# bf16 35B is large (~70GB); require generous free space on the boot volume.
NEED_GB=90
FREE_GB=$(df -g / | awk 'NR==2 {print $4}')
# Guard: non-numeric df output (e.g. unexpected locale/format) must not crash arithmetic.
[[ "$FREE_GB" =~ ^[0-9]+$ ]] || FREE_GB=0
if ollama list 2>/dev/null | grep -q "qwen3.5:35b-a3b-mlx-bf16"; then
  echo "Model already pulled — skipping."
elif (( FREE_GB < NEED_GB )); then
  echo "WARNING: only ${FREE_GB}GB free (need ~${NEED_GB}GB for ${MODEL_TAG})."
  echo "  Free up space then run:  ollama pull ${MODEL_TAG}"
else
  echo "Pulling ${MODEL_TAG} (large download)…"
  ollama pull "${MODEL_TAG}"
fi
echo ""
echo "Setup complete."

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
