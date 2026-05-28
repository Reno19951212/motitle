"""Backfill active_kind + active_id on legacy file registry entries.

Idempotent — entries already carrying active_kind are left untouched.
Run once at backend boot (or manually); safe to re-run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def migrate_registry(registry_path: Path, *, default_profile_id: str = "prod-default") -> int:
    """Backfill missing active_kind/active_id fields on legacy entries.

    Returns the count of entries modified.
    """
    registry_path = Path(registry_path)
    if not registry_path.exists():
        return 0
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    modified = 0
    for fid, entry in registry.items():
        if "active_kind" in entry and "active_id" in entry:
            continue
        entry["active_kind"] = "profile"
        # Prefer profile_id field (v3.10 R5 Phase 2) — falls back to default
        entry["active_id"] = entry.get("profile_id") or default_profile_id
        modified += 1
    if modified:
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return modified


if __name__ == "__main__":
    backend = Path(__file__).resolve().parents[1]
    reg_path = backend / "data" / "registry.json"
    n = migrate_registry(reg_path)
    print(f"migrated {n} legacy file entries")
