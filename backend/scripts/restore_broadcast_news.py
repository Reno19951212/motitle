"""One-shot restoration of pre-v3.15 'Broadcast News' glossary.

Reads the deleted JSON from git history, transforms each entry to the
v3.15 schema ({source, target, target_aliases}), and writes to disk
under a new UUID via GlossaryManager.create() — idempotent (skips
silently if a glossary named 'Broadcast News' already exists for
user_id=null).

Run:
  cd backend
  source venv/bin/activate
  python scripts/restore_broadcast_news.py
"""

import json
import sys
import uuid
from pathlib import Path

# Allow importing the backend package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from glossary import GlossaryManager  # noqa: E402


def _transform_entry(old):
    """Old: {en, zh, zh_aliases?, id?}  ->  New: {source, target, target_aliases?, id}"""
    new = {
        "id": str(uuid.uuid4()),
        "source": old["en"],
        "target": old["zh"],
    }
    aliases = old.get("zh_aliases") or []
    if aliases:
        new["target_aliases"] = list(aliases)
    return new


def main():
    config_dir = Path(__file__).resolve().parent.parent / "config"
    gm = GlossaryManager(config_dir)

    # Idempotency check — skip if already restored
    existing = gm.list_all()
    if any(g.get("name") == "Broadcast News" and g.get("user_id") is None for g in existing):
        print("Broadcast News (shared) already exists. Nothing to do.")
        return 0

    # Read the source JSON. Path is hardcoded to the script's caller convention.
    old_path = Path("/tmp/old_broadcast.json")
    if not old_path.exists():
        print(
            "ERROR: /tmp/old_broadcast.json not found. Run first:\n"
            "  git show 02bdfe4^:backend/config/glossaries/broadcast-news.json"
            " > /tmp/old_broadcast.json",
            file=sys.stderr,
        )
        return 1

    old = json.loads(old_path.read_text())
    old_entries = old.get("entries") or []
    new_entries = [_transform_entry(e) for e in old_entries]

    # Create via the API — handles validation + on-disk write
    created = gm.create({
        "name": old["name"],
        "description": old.get("description", ""),
        "source_lang": "en",
        "target_lang": "zh",
        "entries": new_entries,
        "user_id": None,  # shared
    })

    print(
        f"Restored: id={created['id']}, name='{created['name']}', "
        f"source_lang={created['source_lang']}, target_lang={created['target_lang']}, "
        f"entries={len(created['entries'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
