"""One-shot: inject a synthetic done+translated file into the registry so
test_user_features.spec.js SRT export test has a fixture to scan."""

import json
import os
import sys
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REGISTRY = BACKEND / "data" / "registry.json"

FIXTURE_ID = "srt_fixture_synthetic"


def main():
    if not REGISTRY.exists():
        print(f"Registry not found at {REGISTRY}", file=sys.stderr)
        return 1
    # Registry format is a flat dict: {file_id: entry, ...}
    # (NOT nested under a "files" key — that is the in-memory save format).
    d = json.loads(REGISTRY.read_text())
    if FIXTURE_ID in d:
        print(f"Fixture {FIXTURE_ID} already exists. Skipping.")
        return 0
    now = time.time()
    d[FIXTURE_ID] = {
        "id": FIXTURE_ID,
        "original_name": "srt_fixture.wav",
        "stored_name": f"{FIXTURE_ID}.wav",
        "size": 44,
        "status": "done",
        "translation_status": "done",
        "uploaded_at": now,
        "user_id": 1,  # admin (bootstrap user, id=1 on fresh installs)
        "model": "small",
        "backend": "mlx",
        "translation_engine": "mock",
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "hello"},
            {"start": 1.0, "end": 2.0, "text": "world"},
        ],
        "translations": [
            {
                "start": 0.0,
                "end": 1.0,
                "en_text": "hello",
                "zh_text": "你好",
                "baseline_target": "你好",
                "applied_terms": [],
                "status": "approved",
            },
            {
                "start": 1.0,
                "end": 2.0,
                "en_text": "world",
                "zh_text": "世界",
                "baseline_target": "世界",
                "applied_terms": [],
                "status": "approved",
            },
        ],
        "text": "hello world",
        "asr_seconds": 0.1,
        "translation_seconds": 0.1,
        "pipeline_seconds": 0.2,
    }
    # Write back using the same flat structure
    REGISTRY.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    print(f"Injected fixture {FIXTURE_ID} with 2 segments + 2 approved translations.")

    # Also place 0-byte placeholder media files in case any endpoint
    # tries to open the source. Backend resolves via `stored_name`
    # under per-user upload dirs (R5 Phase 1) — put it in all common paths.
    candidates = [
        BACKEND / "data" / "uploads" / f"{FIXTURE_ID}.wav",
        BACKEND / "data" / "users" / "1" / "uploads" / f"{FIXTURE_ID}.wav",
    ]
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_bytes(b"")
        except Exception as e:
            print(f"Note: couldn't place placeholder at {p}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
