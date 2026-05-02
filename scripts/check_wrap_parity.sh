#!/bin/bash
# Pre-commit hook: enforce F/B parity for wrap algorithm.
# If backend/subtitle_wrap.py is staged but frontend/js/subtitle-wrap.js is not,
# block the commit. The two files MUST evolve together (Tier P4 of v3.9 parity harness).
PY_CHANGED=$(git diff --cached --name-only | grep -E "^backend/subtitle_wrap\.py$" || true)
JS_CHANGED=$(git diff --cached --name-only | grep -E "^frontend/js/subtitle-wrap\.js$" || true)

if [ -n "$PY_CHANGED" ] && [ -z "$JS_CHANGED" ]; then
  echo "❌ Pre-commit blocked: subtitle_wrap.py staged but subtitle-wrap.js NOT staged."
  echo ""
  echo "   F/B parity required for wrap algorithm. Either:"
  echo "   1. Update frontend/js/subtitle-wrap.js to mirror your Python change."
  echo "   2. Or update backend/tests/validation/wrap_canonical_fixtures.json"
  echo "      (then both Python pytest + Playwright parity tests fail until JS catches up)."
  echo ""
  echo "   Reference: docs/superpowers/specs/2026-05-02-line-budget-a3v3-design.md (Mod 5)."
  exit 1
fi
exit 0
