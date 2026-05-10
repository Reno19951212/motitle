# backend/scripts/migrate_owner_fields.py
"""One-off: backfill `user_id: null` (= shared) on existing profile + glossary
JSON files. Safe to re-run."""
import json
import sys
from pathlib import Path


def migrate(config_dir: Path) -> int:
    count = 0
    for sub in ("profiles", "glossaries"):
        d = config_dir / sub
        if not d.is_dir():
            continue
        for f in d.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            if "user_id" not in data:
                data["user_id"] = None
                tmp = f.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                               encoding="utf-8")
                tmp.replace(f)
                count += 1
    return count


if __name__ == "__main__":
    cfg = Path(sys.argv[1] if len(sys.argv) > 1 else "backend/config")
    n = migrate(cfg)
    print(f"Migrated {n} entries to user_id=null in {cfg}")
