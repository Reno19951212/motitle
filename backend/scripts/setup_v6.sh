#!/usr/bin/env bash
# Set up Qwen3-ASR Python 3.11 subprocess venv.
# Idempotent — skips if already present and working.

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_QWEN="$BACKEND_DIR/scripts/v5_prototype/venv_qwen"

echo "[setup_v6] target venv: $VENV_QWEN"

# Check if py3.11 is available
if ! command -v python3.11 >/dev/null 2>&1; then
  echo "[setup_v6] ERROR: python3.11 not found in PATH. Install via:"
  echo "  macOS:  brew install python@3.11"
  echo "  Linux:  sudo apt-get install python3.11 python3.11-venv"
  exit 1
fi

# Skip if venv already set up + mlx_qwen3_asr import works
if [ -x "$VENV_QWEN/bin/python" ]; then
  if "$VENV_QWEN/bin/python" -c "import mlx_qwen3_asr" 2>/dev/null; then
    echo "[setup_v6] venv already set up — skip"
    exit 0
  fi
fi

# Create venv
mkdir -p "$(dirname "$VENV_QWEN")"
python3.11 -m venv "$VENV_QWEN"
echo "[setup_v6] created py3.11 venv at $VENV_QWEN"

# Upgrade pip
"$VENV_QWEN/bin/pip" install --upgrade pip

# Install Qwen3-ASR + transitive deps
"$VENV_QWEN/bin/pip" install \
  "mlx_qwen3_asr==0.3.5" \
  "soundfile>=0.13.0" \
  "numpy"

# Smoke test
"$VENV_QWEN/bin/python" -c "
import mlx_qwen3_asr
import soundfile
print(f'mlx_qwen3_asr {getattr(mlx_qwen3_asr, \"__version__\", \"\")} OK')
print(f'soundfile {soundfile.__version__} OK')
"

echo "[setup_v6] done. V6 pipelines are now available."
