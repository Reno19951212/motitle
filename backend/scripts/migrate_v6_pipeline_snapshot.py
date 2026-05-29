"""v3.19 Sprint 3 B-10 — backfill active_pipeline_snapshot for existing V6 entries.

Reads every registry entry with active_kind='pipeline_v6' that lacks an
active_pipeline_snapshot, loads the current pipeline JSON, and writes it into
the entry. Idempotent: entries that already have the field are skipped.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/migrate_v6_pipeline_snapshot.py [--registry PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_REGISTRY = _REPO_ROOT / "backend" / "data" / "registry.json"
_DEFAULT_PIPELINES_DIR = _REPO_ROOT / "backend" / "config" / "pipelines"


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_pipeline(pipeline_id: str, pipelines_dir: Path) -> dict | None:
    """Try to load a pipeline JSON file by id from the pipelines directory."""
    candidate = pipelines_dir / f"{pipeline_id}.json"
    if candidate.exists():
        return _load_json(candidate)
    # Also scan all JSON files for an entry with matching id
    for p in pipelines_dir.glob("*.json"):
        try:
            data = _load_json(p)
            if data.get("id") == pipeline_id:
                return data
        except Exception:
            continue
    return None


def migrate(registry_path: Path, pipelines_dir: Path, dry_run: bool = False) -> int:
    """Backfill active_pipeline_snapshot for V6 registry entries.

    Returns the number of entries updated.
    """
    if not registry_path.exists():
        print(f"[INFO] Registry not found at {registry_path} — nothing to migrate.")
        return 0

    registry = _load_json(registry_path)
    updated = 0
    skipped_no_pipeline = 0

    for fid, entry in registry.items():
        if entry.get("active_kind") != "pipeline_v6":
            continue
        if entry.get("active_pipeline_snapshot") is not None:
            continue  # already has snapshot, skip

        pipeline_id = entry.get("active_id")
        if not pipeline_id:
            continue

        pipeline = _load_pipeline(pipeline_id, pipelines_dir)
        if pipeline is None:
            print(f"[WARN] Pipeline {pipeline_id!r} not found for file {fid} — skipping.")
            skipped_no_pipeline += 1
            continue

        if not dry_run:
            entry["active_pipeline_snapshot"] = dict(pipeline)
        print(
            f"[{'DRY-RUN' if dry_run else 'UPDATE'}] file={fid} pipeline={pipeline_id} "
            f"snapshot_keys={list(pipeline.keys())[:5]}"
        )
        updated += 1

    if not dry_run and updated > 0:
        _save_json(registry_path, registry)
        print(f"[OK] Saved registry. {updated} entries updated, {skipped_no_pipeline} skipped (no pipeline).")
    else:
        print(f"[DRY-RUN] Would update {updated} entries, skip {skipped_no_pipeline}.")

    return updated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill active_pipeline_snapshot for V6 registry entries.")
    parser.add_argument("--registry", type=Path, default=_DEFAULT_REGISTRY,
                        help=f"Path to registry.json (default: {_DEFAULT_REGISTRY})")
    parser.add_argument("--pipelines-dir", type=Path, default=_DEFAULT_PIPELINES_DIR,
                        help=f"Path to config/pipelines/ (default: {_DEFAULT_PIPELINES_DIR})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be updated without writing.")
    args = parser.parse_args()

    n = migrate(args.registry, args.pipelines_dir, dry_run=args.dry_run)
    sys.exit(0 if n >= 0 else 1)
