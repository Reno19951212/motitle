"""One-shot migration: normalize all profile asr.model_size to 'large-v3'.

Run once after v3.17 narrow. Idempotent — safe to re-run.

Usage:
    python backend/scripts/migrate_v317_asr_models.py
"""
import json
import sys
from pathlib import Path
from typing import Optional, Tuple

TARGET_MODEL = "large-v3"
PROFILES_DIR = Path(__file__).resolve().parent.parent / "config" / "profiles"


def migrate_profile(profile_path: Path) -> Tuple[bool, Optional[str]]:
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"parse error: {e}"
    asr = profile.get("asr") or {}
    current = asr.get("model_size")
    if current and current != TARGET_MODEL:
        old = current
        asr["model_size"] = TARGET_MODEL
        profile["asr"] = asr
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True, f"{old} → {TARGET_MODEL}"
    return False, None


def main():
    if not PROFILES_DIR.exists():
        print(f"Profiles dir not found: {PROFILES_DIR}", file=sys.stderr)
        return 1
    modified_count = 0
    skipped_count = 0
    error_count = 0
    for p in sorted(PROFILES_DIR.glob("*.json")):
        ok, info = migrate_profile(p)
        if ok:
            print(f"MIGRATED  {p.name}: {info}")
            modified_count += 1
        elif info and "parse error" in info:
            print(f"ERROR     {p.name}: {info}", file=sys.stderr)
            error_count += 1
        else:
            print(f"SKIPPED   {p.name} (already large-v3 or no asr.model_size)")
            skipped_count += 1
    print(f"\nTotal: {modified_count} migrated, {skipped_count} skipped, {error_count} errors")
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
