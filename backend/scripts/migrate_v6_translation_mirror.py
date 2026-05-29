"""Backfill legacy mirror fields (zh_text, status, flags) on V6 translation rows.

V6 files store per-language translation data under
    entry["translations"][i]["by_lang"][lang]["text"]  (+ .status, .flags)

Legacy API endpoints (approve-all, subtitle export, render) still read from
top-level  t["zh_text"] / t["status"]  which are absent on pre-Sprint-1 V6
rows.  This idempotent migration adds those mirror fields so all legacy
endpoints work correctly without touching their implementations.

Run once at backend boot (wired after migrate_active_kind); safe to re-run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def migrate_registry(registry_path: Path) -> int:
    """Backfill legacy mirror fields for V6 translation rows.

    Criteria for a row needing backfill:
        - entry.active_kind == "pipeline_v6"
        - entry has a non-empty translations list
        - at least one translation row has by_lang populated but is missing
          the top-level <lang>_text or status mirror

    Returns the count of FILE entries modified (not individual rows).
    """
    registry_path = Path(registry_path)
    if not registry_path.exists():
        return 0

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0

    modified_files = 0

    for fid, entry in registry.items():
        # Only process V6 files
        if entry.get("active_kind") != "pipeline_v6":
            continue

        translations = entry.get("translations")
        if not translations:
            continue

        file_changed = False
        for t in translations:
            by_lang = t.get("by_lang")
            if not by_lang:
                continue

            # Determine primary language from translation row
            lang = t.get("source_lang", "zh")
            primary = by_lang.get(lang)
            if primary is None:
                continue

            lang_text_key = f"{lang}_text"
            expected_text = primary.get("text", "")
            expected_status = primary.get("status", "pending")

            # Check if mirror fields are already correct (idempotent guard)
            already_correct = (
                t.get(lang_text_key) == expected_text
                and t.get("status") == expected_status
            )
            if already_correct:
                continue

            # Write mirror fields
            t[lang_text_key] = expected_text
            t["status"] = expected_status
            # Mirror flags only when by_lang has non-empty flags
            primary_flags = primary.get("flags")
            if primary_flags:
                t["flags"] = list(primary_flags)
            elif "flags" not in t:
                t["flags"] = []

            file_changed = True

        if file_changed:
            modified_files += 1

    if modified_files:
        registry_path.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return modified_files


if __name__ == "__main__":
    backend = Path(__file__).resolve().parents[1]
    reg_path = backend / "data" / "registry.json"
    n = migrate_registry(reg_path)
    print(f"migrated {n} V6 file entries (backfilled legacy translation mirror fields)")
