"""File-registry helpers extracted from ``app.py`` (v4 A6 C2 T13a).

These helpers mutate the in-memory ``_file_registry`` dict that lives in
``backend/managers.py``. Look-ups go through the ``managers`` module each
call so that tests which monkeypatch ``app._file_registry`` (and therefore
``managers._file_registry`` via app.py's re-export) see the patched dict.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import List

import managers as _managers


def _data_dir():
    """``app.DATA_DIR`` if available (honors tmp-path test fixture)."""
    try:
        import app as _app
        return _app.DATA_DIR
    except Exception:
        return _managers.DATA_DIR


def _upload_dir():
    """``app.UPLOAD_DIR`` if available (honors tmp-path test fixture)."""
    try:
        import app as _app
        return _app.UPLOAD_DIR
    except Exception:
        return _managers.UPLOAD_DIR


# ---------------------------------------------------------------------------
# Per-user upload directory + lookup chain
# ---------------------------------------------------------------------------
def _user_upload_dir(user_id: int) -> Path:
    """Per-user uploads directory (R5 Phase 1).

    Creates ``data/users/<uid>/uploads/`` lazily. New uploads land here so
    storage layout is owner-scoped. Legacy files at UPLOAD_DIR root are
    still readable via :func:`_resolve_file_path`.
    """
    p = _data_dir() / "users" / str(user_id) / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _resolve_file_path(entry: dict) -> str:
    """Return the on-disk path for a registry entry.

    Prefers the per-user ``file_path`` recorded at save time (R5+); falls
    back to the legacy UPLOAD_DIR root layout for entries created before
    Phase 1 (which only stored ``stored_name``).
    """
    fp = entry.get("file_path")
    if fp and os.path.exists(fp):
        return fp
    return str(_upload_dir() / entry["stored_name"])


def _filter_files_by_owner(registry: dict, user) -> dict:
    """Return registry subset visible to current user (R5 Phase 1).

    - Admin sees all.
    - Other users see only files where ``user_id == user.id``.
    - Files with no ``user_id`` (pre-R5 era / orphan) are NOT shown to
      non-admin users; admin can re-assign via DB or migration script.
    - When ``R5_AUTH_BYPASS`` is set (test mode) and the user has no
      ``id`` attribute, the full registry is returned.
    """
    # Late-bind so tests can monkeypatch ``app.app`` (Flask app's config).
    import app as _app
    if getattr(user, "is_admin", False):
        return dict(registry)
    if _app.app.config.get("R5_AUTH_BYPASS") and not hasattr(user, "id"):
        return dict(registry)
    return {
        fid: f for fid, f in registry.items()
        if f.get("user_id") == user.id
    }


# ---------------------------------------------------------------------------
# Registry CRUD
# ---------------------------------------------------------------------------
def _register_file(file_id, original_name, stored_name, size_bytes, user_id=None,
                   file_path=None, duration_seconds=None):
    """Register an uploaded file.

    ``user_id`` is the owner (R5 Phase 1 — required once auth lands;
    defaults to None for backward compatibility with any pre-R5 path that
    may still upload anonymously). ``file_path`` is the absolute on-disk
    path (R5 Phase 1 — set when files land under per-user dirs; legacy
    entries without it fall back to UPLOAD_DIR root).
    ``duration_seconds`` is the media duration obtained via ffprobe (Q2 —
    None when ffprobe is unavailable or fails).
    """
    # Lazy import to avoid app.py ↔ helpers cycle at module load.
    import app as _app

    with _managers._registry_lock:
        _managers._file_registry[file_id] = {
            "id": file_id,
            "user_id": user_id,
            "original_name": original_name,
            "stored_name": stored_name,
            "file_path": file_path,
            "size": size_bytes,
            "duration_seconds": duration_seconds,  # Q2: ffprobe-derived media duration
            "status": "uploaded",   # uploaded | transcribing | done | error
            "uploaded_at": time.time(),
            "segments": [],
            "text": "",
            "error": None,
            "model": None,           # whisper model used (e.g. 'small', 'tiny')
            "backend": None,         # 'openai-whisper' or 'faster-whisper'
            "subtitle_source": None,
            "bilingual_order": None,
            "prompt_overrides": None,  # v3.18 Stage 2: per-file MT prompt override
        }
        _app._save_registry()
    return _managers._file_registry[file_id]


def _update_file(file_id, **kwargs):
    """Update file metadata."""
    import app as _app
    with _managers._registry_lock:
        if file_id in _managers._file_registry:
            _managers._file_registry[file_id].update(kwargs)
            _app._save_registry()


def _delete_file_entry(file_id):
    """Delete a file from registry and disk."""
    import app as _app
    with _managers._registry_lock:
        entry = _managers._file_registry.pop(file_id, None)
        _app._save_registry()
    if entry:
        media_path = Path(_resolve_file_path(entry))
        if media_path.exists():
            media_path.unlink()
    return entry is not None


# ---------------------------------------------------------------------------
# Translation legacy-prefix normalization
# ---------------------------------------------------------------------------
# Legacy QA prefix migration: registry entries written before flags were
# structured may still carry "[LONG] " / "[NEEDS REVIEW] " in ``zh_text``.
# Normalize on read so the API always exposes a clean zh_text + flags pair.
_LEGACY_QA_PREFIX_RE = re.compile(r"^\s*(?:\[(LONG|NEEDS REVIEW)\])\s*")


def _normalize_translation_for_api(t: dict) -> dict:
    """Return a copy of ``t`` with structured ``flags`` and clean ``zh_text``.

    If ``t`` already has a ``flags`` field, it is returned unchanged.
    Otherwise legacy [LONG] / [NEEDS REVIEW] prefixes (possibly stacked)
    are parsed out of zh_text and converted into a flags list.
    """
    if "flags" in t:
        return t
    zh = t.get("zh_text", "") or ""
    flags: List[str] = []
    while True:
        m = _LEGACY_QA_PREFIX_RE.match(zh)
        if not m:
            break
        tag = m.group(1)
        flag = "long" if tag == "LONG" else "review"
        if flag not in flags:
            flags.append(flag)
        zh = zh[m.end():]
    return {**t, "zh_text": zh, "flags": flags}
