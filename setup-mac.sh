#!/usr/bin/env bash
# setup-mac.sh — macOS Apple Silicon installer (R5 Phase 1)
# Provisions venv + mlx-whisper, bootstraps an admin user, and writes
# backend/.env with a freshly-generated FLASK_SECRET_KEY.
set -euo pipefail

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "ERROR: This script targets Apple Silicon (arm64). For Intel Mac, use setup.sh"
  exit 1
fi

# Check prerequisites
command -v python3 >/dev/null || { echo "Python 3.11+ required: brew install python@3.11"; exit 1; }
command -v ffmpeg >/dev/null  || { echo "FFmpeg required: brew install ffmpeg"; exit 1; }

# Backend setup
cd backend
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install mlx-whisper

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
echo "Saved backend/.env (gitignored). Source it before running app.py:"
echo ""
echo "  source backend/.env && cd backend && source venv/bin/activate && python app.py"
echo ""
echo "Setup complete."
