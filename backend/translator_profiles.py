"""TranslatorProfile manager — v5-A1.

NEW v5 entity. Cross-lingual translation profile: source_lang → target_lang.

Different from RefinerProfile (same-lingual polish): TranslatorProfile MUST have
source_lang ≠ target_lang. Use RefinerProfile for same-language register cleanup.

Refers to LLMProfile via `llm_profile_id` for backend LLM config and a
`prompt_template_id` for the system prompt template (loaded at runtime from
`backend/config/prompt_templates_v5/translator/`).

Follows v5 ProfileManager pattern (per-resource lock, immutable id/user_id/
created_at on update, can_view for admin/owner/shared, updated_at audit).
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

VALID_LANGS = {"en", "zh", "ja", "ko", "yue", "fr", "de", "es", "th"}
MAX_NAME_CHARS = 64

_LOCK = threading.Lock()
_RES_LOCKS: dict = {}


def _res_lock(rid: str) -> threading.Lock:
    with _LOCK:
        lock = _RES_LOCKS.get(rid)
        if lock is None:
            lock = threading.Lock()
            _RES_LOCKS[rid] = lock
        return lock


def validate_translator_profile(data: Any) -> list:
    """Return list of human-readable error strings; empty = valid."""
    errors: list = []
    if not isinstance(data, dict):
        return ["payload must be object"]
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name required")
    elif len(name.strip()) > MAX_NAME_CHARS:
        errors.append(f"name max {MAX_NAME_CHARS} chars")
    source_lang = data.get("source_lang")
    if source_lang not in VALID_LANGS:
        errors.append(f"source_lang must be in {sorted(VALID_LANGS)}")
    target_lang = data.get("target_lang")
    if target_lang not in VALID_LANGS:
        errors.append(f"target_lang must be in {sorted(VALID_LANGS)}")
    # Cross-field: Translator requires different langs (same-lang polish is Refiner's job).
    if (
        source_lang in VALID_LANGS
        and target_lang in VALID_LANGS
        and source_lang == target_lang
    ):
        errors.append("source_lang and target_lang must differ (use RefinerProfile for same-language polish)")
    llm_pid = data.get("llm_profile_id")
    if not isinstance(llm_pid, str) or not llm_pid.strip():
        errors.append("llm_profile_id required (non-empty string)")
    tpl_id = data.get("prompt_template_id")
    if not isinstance(tpl_id, str) or not tpl_id.strip():
        errors.append("prompt_template_id required (non-empty string)")
    return errors


class TranslatorProfileManager:
    """CRUD + ownership for TranslatorProfile entities.

    Storage: one JSON file per profile in ``config_dir/<uuid>.json``. No
    in-memory cache — file system is the source of truth (mirrors the
    simpler v5-A1 pattern; v4 cache pattern can be added later if perf
    becomes an issue).
    """

    def __init__(self, config_dir):
        self.dir = Path(config_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self, data: dict, *, user_id: int) -> str:
        errors = validate_translator_profile(data)
        if errors:
            raise ValueError("; ".join(errors))
        pid = str(uuid.uuid4())
        now = time.time()
        # Defensive: strip name; force `shared` to bool; set audit fields
        normalized = {
            **data,
            "name": data["name"].strip(),
            "id": pid,
            "user_id": user_id,
            "shared": bool(data.get("shared", False)),
            "created_at": now,
            "updated_at": now,
        }
        path = self.dir / f"{pid}.json"
        path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        return pid

    def get(self, pid: str) -> Optional[dict]:
        path = self.dir / f"{pid}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_visible(self, user_id: int, is_admin: bool) -> list:
        out = []
        for f in self.dir.glob("*.json"):
            try:
                p = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if is_admin or p.get("user_id") == user_id or p.get("shared"):
                out.append(p)
        return out

    def can_edit(self, pid: str, user_id: int, is_admin: bool) -> bool:
        p = self.get(pid)
        return p is not None and (is_admin or p.get("user_id") == user_id)

    def can_view(self, pid: str, user_id: int, is_admin: bool) -> bool:
        """Admin OR owner OR shared profile may read."""
        p = self.get(pid)
        if p is None:
            return False
        return is_admin or p.get("user_id") == user_id or bool(p.get("shared"))

    def update_if_owned(
        self,
        pid: str,
        user_id: int,
        is_admin: bool,
        patch: dict,
    ) -> Optional[dict]:
        with _res_lock(pid):
            p = self.get(pid)
            if p is None or not (is_admin or p.get("user_id") == user_id):
                return None
            # Merge patch but ALWAYS preserve immutable identity / audit fields.
            # Without this, a patch with {"user_id": <other>} could escalate ownership.
            merged = {**p, **patch}
            merged["id"] = p["id"]
            merged["user_id"] = p["user_id"]
            merged["created_at"] = p.get("created_at")
            if "name" in patch and isinstance(patch["name"], str):
                merged["name"] = patch["name"].strip()
            errors = validate_translator_profile(merged)
            if errors:
                raise ValueError("; ".join(errors))
            merged["updated_at"] = time.time()
            (self.dir / f"{pid}.json").write_text(
                json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return merged

    def delete_if_owned(self, pid: str, user_id: int, is_admin: bool) -> bool:
        with _res_lock(pid):
            p = self.get(pid)
            if p is None or not (is_admin or p.get("user_id") == user_id):
                return False
            (self.dir / f"{pid}.json").unlink()
            return True
