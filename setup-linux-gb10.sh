#!/usr/bin/env bash
# setup-linux-gb10.sh — NVIDIA GB10 (Linux aarch64) installer (R5 Phase 2)
# Mirror of setup-mac.sh / setup-win.ps1 with CUDA wheels for aarch64.
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: This script targets Linux. For macOS use setup-mac.sh; for Windows use setup-win.ps1"
  exit 1
fi

# Detect CUDA-capable GPU (informational only — CPU fallback works without)
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "✓ Detected NVIDIA GPU:"
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader | head -1
else
  echo "⚠ nvidia-smi not found — CPU-only mode will be used"
fi

# Check prerequisites
command -v python3 >/dev/null || { echo "Python 3.11+ required: sudo apt install python3.11 python3.11-venv"; exit 1; }
command -v ffmpeg >/dev/null  || { echo "FFmpeg required: sudo apt install ffmpeg"; exit 1; }

# Backend setup
cd backend
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# CUDA runtime wheels (aarch64-compatible) for ctranslate2 4.7
pip install nvidia-cublas-cu12==12.4.5.8 nvidia-cudnn-cu12

# Bootstrap admin (env-driven — see setup-mac.sh for shell-injection rationale)
echo ""
echo "=== Set up admin user ==="
read -p "Admin username [admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}
read -s -p "Admin password: " ADMIN_PW
echo ""
read -s -p "Confirm password: " ADMIN_PW2
echo ""
[[ "$ADMIN_PW" == "$ADMIN_PW2" ]] || { echo "Passwords don't match"; exit 1; }

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

# Generate FLASK_SECRET_KEY
SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
echo "FLASK_SECRET_KEY=$SECRET" > .env
echo ""
echo "Saved backend/.env (gitignored). Next:"
echo "  source backend/.env && cd backend && source venv/bin/activate && python app.py"
echo ""
echo "=== Generate self-signed HTTPS cert ==="
python scripts/generate_https_cert.py data/certs && \
  echo "Cert: backend/data/certs/server.crt" || \
  echo "Cert generation failed (HTTPS will be disabled; install mkcert or openssl to enable)"
echo ""
echo "Setup complete."
