"""One-shot migration: backfill `duration_seconds` for pre-Q2 registry entries.

Idempotent — re-running on an already-backfilled registry produces 0 changes.

Usage (from repo root):
    cd backend && source venv/bin/activate
    python scripts/backfill_duration.py

Reads/writes the running app's registry by importing it. If the app is running,
restart it after migration so the in-memory copy reloads from disk.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def _probe(path: str) -> "float | None":
    if not path or not os.path.exists(path):
        return None
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        return float(json.loads(result.stdout).get("format", {}).get("duration") or 0) or None
    except Exception:
        return None


def backfill_registry(registry: dict) -> int:
    """Mutate registry in place; return count of entries newly populated.

    Entries already with non-None duration_seconds are skipped (idempotent).
    Entries with missing or unreadable file_path get duration_seconds = None.
    """
    modified = 0
    for fid, entry in registry.items():
        if entry.get("duration_seconds") is not None:
            continue
        path = entry.get("file_path", "")
        entry["duration_seconds"] = _probe(path)
        modified += 1
    return modified


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import app as _app  # noqa: E402

    n = backfill_registry(_app._file_registry)
    # Use synchronous write — no background flusher running in CLI context.
    _app._save_registry_to_disk()
    print(f"[backfill_duration] populated {n} entries")
