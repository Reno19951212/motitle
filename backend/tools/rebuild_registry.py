"""Rebuild registry.json from files in data/uploads/ after registry wipe.

Usage:
    python tools/rebuild_registry.py              # rebuild (overwrites current registry)
    python tools/rebuild_registry.py --dry-run    # preview only, no write
    python tools/rebuild_registry.py --merge      # keep existing entries, add missing

Fields that cannot be recovered (left empty/default):
    - original_name (falls back to stored_name)
    - segments, text, translations, translation_status
    - model, backend
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Match only the expected file_id pattern: 12 hex chars + video extension
FILE_ID_PATTERN = re.compile(r"^([0-9a-fA-F]{12})\.(mp4|mov|mxf|mkv|webm)$", re.IGNORECASE)


def scan_uploads(uploads_dir: Path) -> dict:
    """Return a dict of {file_id: minimal_entry} for every matching file."""
    entries = {}
    for path in sorted(uploads_dir.iterdir()):
        if not path.is_file():
            continue
        match = FILE_ID_PATTERN.match(path.name)
        if not match:
            continue
        file_id = match.group(1)
        stat = path.stat()
        entries[file_id] = {
            "id": file_id,
            "original_name": path.name,
            "stored_name": path.name,
            "size": stat.st_size,
            "status": "uploaded",
            "uploaded_at": float(stat.st_mtime),
            "segments": [],
            "text": "",
            "error": None,
            "model": None,
            "backend": None,
        }
    return entries


def rebuild(data_dir: Path, dry_run: bool, merge: bool) -> dict:
    """Scan, merge if requested, and optionally write the registry. Returns final dict."""
    uploads_dir = data_dir / "uploads"
    registry_path = data_dir / "registry.json"

    if not uploads_dir.exists():
        raise FileNotFoundError(f"{uploads_dir} does not exist")

    scanned = scan_uploads(uploads_dir)

    existing = {}
    if merge and registry_path.exists():
        with open(registry_path) as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError(
                f"{registry_path} is not a JSON object (got {type(loaded).__name__})"
            )
        existing = loaded

    # Merge: existing entries take precedence over scanned (preserve real metadata)
    final = {**scanned, **existing} if merge else scanned

    print(f"Scanned {len(scanned)} file(s) from {uploads_dir}")
    if merge:
        print(f"Preserving {len(existing)} existing entries; final count: {len(final)}")
    else:
        action = "overwrite" if registry_path.exists() else "create"
        print(f"Will {action} {registry_path}")
        print(f"Final entry count: {len(final)}")

    # Entries from a damaged/merged registry may be missing fields — print defensively.
    for fid, entry in sorted(final.items()):
        name = entry.get("stored_name", "?") if isinstance(entry, dict) else "?"
        size = entry.get("size", "?") if isinstance(entry, dict) else "?"
        print(f"  {fid}  {name}  {size} bytes")

    if dry_run:
        print("\n(dry-run: no changes written)")
        return final

    with open(registry_path, "w") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {registry_path}")
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print plan, don't write")
    parser.add_argument("--merge", action="store_true", help="Preserve existing registry entries")
    args = parser.parse_args()

    data_dir = Path(__file__).parent.parent / "data"
    try:
        rebuild(data_dir, dry_run=args.dry_run, merge=args.merge)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: existing registry.json is corrupt: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
