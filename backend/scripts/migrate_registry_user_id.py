"""One-off: backfill user_id for pre-R5 registry entries.

Strategy: assign all orphan files to admin user (id=1). Admin can then
manually re-assign via DB if needed. Safe to re-run (idempotent).

Usage:
    python backend/scripts/migrate_registry_user_id.py [path/to/registry.json]

Defaults to backend/data/registry.json relative to CWD.
"""
import json
import sys
from pathlib import Path


def migrate(registry_path: str, admin_user_id: int = 1) -> int:
    """Returns count of records modified."""
    p = Path(registry_path)
    reg = json.loads(p.read_text(encoding="utf-8"))
    count = 0
    for fid, entry in reg.items():
        if "user_id" not in entry or entry["user_id"] is None:
            entry["user_id"] = admin_user_id
            count += 1
    if count > 0:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(p)
    return count


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "backend/data/registry.json"
    n = migrate(path)
    print(f"Migrated {n} entries to admin (user_id=1) in {path}")
