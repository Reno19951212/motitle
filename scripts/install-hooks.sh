#!/bin/bash
# Install repository git hooks. Run once after cloning.
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK_PATH="$REPO_ROOT/.git/hooks/pre-commit"
SCRIPT_PATH="$REPO_ROOT/scripts/check_wrap_parity.sh"

if [ ! -d "$REPO_ROOT/.git" ]; then
  echo "❌ Not a git repo: $REPO_ROOT"
  exit 1
fi

chmod +x "$SCRIPT_PATH"
ln -sf "$SCRIPT_PATH" "$HOOK_PATH"
chmod +x "$HOOK_PATH"

echo "✓ pre-commit hook installed → $HOOK_PATH"
echo "  Test it: edit backend/subtitle_wrap.py without editing frontend/js/subtitle-wrap.js,"
echo "  then 'git commit' — should be blocked."
