"""
MT profile management — v4.0 Phase 1.

MT profiles are standalone entities (one file per profile in
config/mt_profiles/<uuid>.json) that describe a machine translation
configuration: qwen3.5-35b-a3b only (Phase 1 scope), same-lang
transformation, system_prompt and user_message_template with {text}
placeholder, batch_size, temperature, parallel_batches knobs.

Per design doc §3.2 — replaces the `translation` sub-block of the legacy
bundled profile schema. Legacy profiles continue to work via backend/profiles.py
during P1-P2; P3 migration script will auto-split bundled profiles into
asr_profile + mt_profile + pipeline triples.
"""

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

VALID_ENGINES = {"qwen3.5-35b-a3b"}
VALID_LANGUAGES = {"en", "zh", "ja", "ko", "fr", "de", "es"}
MAX_NAME_CHARS = 64
MAX_DESCRIPTION_CHARS = 256
MAX_SYSTEM_PROMPT_CHARS = 4096
MAX_USER_TEMPLATE_CHARS = 1024
MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 64
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
MIN_PARALLEL_BATCHES = 1
MAX_PARALLEL_BATCHES = 16

_MT_LOCKS: dict = {}
_MT_MASTER_LOCK = threading.Lock()


def _get_mt_lock(profile_id: str) -> threading.Lock:
    with _MT_MASTER_LOCK:
        lock = _MT_LOCKS.get(profile_id)
        if lock is None:
            lock = threading.Lock()
            _MT_LOCKS[profile_id] = lock
        return lock


def validate_mt_profile(data: Any) -> list:
    errors: list = []
    if not isinstance(data, dict):
        return ["payload must be an object"]

    name = data.get("name")
    if not name or not isinstance(name, str) or not name.strip():
        errors.append("name is required")
    elif len(name) > MAX_NAME_CHARS:
        errors.append(f"name must be {MAX_NAME_CHARS} chars or less")

    desc = data.get("description", "")
    if desc and (not isinstance(desc, str) or len(desc) > MAX_DESCRIPTION_CHARS):
        errors.append(f"description must be string of {MAX_DESCRIPTION_CHARS} chars or less")

    engine = data.get("engine")
    if engine not in VALID_ENGINES:
        errors.append(f"engine must be one of {sorted(VALID_ENGINES)}")

    input_lang = data.get("input_lang")
    output_lang = data.get("output_lang")
    if input_lang not in VALID_LANGUAGES:
        errors.append(f"input_lang must be one of {sorted(VALID_LANGUAGES)}")
    if output_lang not in VALID_LANGUAGES:
        errors.append(f"output_lang must be one of {sorted(VALID_LANGUAGES)}")
    if input_lang and output_lang and input_lang != output_lang:
        errors.append("MT is same-lang only — input_lang must equal output_lang (v4.0)")

    system_prompt = data.get("system_prompt", "")
    if not system_prompt or not isinstance(system_prompt, str) or not system_prompt.strip():
        errors.append("system_prompt is required")
    elif len(system_prompt) > MAX_SYSTEM_PROMPT_CHARS:
        errors.append(f"system_prompt must be {MAX_SYSTEM_PROMPT_CHARS} chars or less")

    template = data.get("user_message_template", "")
    if not template or not isinstance(template, str) or not template.strip():
        errors.append("user_message_template is required")
    elif "{text}" not in template:
        errors.append("user_message_template must contain {text} placeholder")
    elif len(template) > MAX_USER_TEMPLATE_CHARS:
        errors.append(f"user_message_template must be {MAX_USER_TEMPLATE_CHARS} chars or less")

    batch = data.get("batch_size", 1)
    if not isinstance(batch, int) or batch < MIN_BATCH_SIZE or batch > MAX_BATCH_SIZE:
        errors.append(f"batch_size must be int {MIN_BATCH_SIZE}-{MAX_BATCH_SIZE}")

    temp = data.get("temperature", 0.1)
    if not isinstance(temp, (int, float)) or temp < MIN_TEMPERATURE or temp > MAX_TEMPERATURE:
        errors.append(f"temperature must be {MIN_TEMPERATURE}-{MAX_TEMPERATURE}")

    pb = data.get("parallel_batches", 1)
    if not isinstance(pb, int) or pb < MIN_PARALLEL_BATCHES or pb > MAX_PARALLEL_BATCHES:
        errors.append(f"parallel_batches must be int {MIN_PARALLEL_BATCHES}-{MAX_PARALLEL_BATCHES}")

    return errors


class MTProfileManager:
    """Mirror of ASRProfileManager pattern, for MT profile entities."""

    DIRNAME = "mt_profiles"

    def __init__(self, config_dir):
        self._config_dir = Path(config_dir)
        self._dir = self._config_dir / self.DIRNAME
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict = {}
        self._load_all()

    def _load_all(self):
        for fpath in self._dir.glob("*.json"):
            try:
                data = json.loads(fpath.read_text())
                if isinstance(data, dict) and data.get("id"):
                    self._cache[data["id"]] = data
            except Exception as exc:
                print(f"[mt_profiles] skip malformed file {fpath}: {exc}")

    def _save(self, profile: dict):
        (self._dir / f"{profile['id']}.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2)
        )

    def create(self, data: dict, user_id: Optional[int]) -> dict:
        errors = validate_mt_profile(data)
        if errors:
            raise ValueError("; ".join(errors))
        now = int(time.time())
        profile = {
            "id": str(uuid.uuid4()),
            "name": data["name"].strip(),
            "description": data.get("description", ""),
            "engine": data["engine"],
            "input_lang": data["input_lang"],
            "output_lang": data["output_lang"],
            "system_prompt": data["system_prompt"],
            "user_message_template": data["user_message_template"],
            "batch_size": int(data.get("batch_size", 1)),
            "temperature": float(data.get("temperature", 0.1)),
            "parallel_batches": int(data.get("parallel_batches", 1)),
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        self._save(profile)
        self._cache[profile["id"]] = profile
        return dict(profile)

    def get(self, profile_id):
        cached = self._cache.get(profile_id)
        return dict(cached) if cached else None

    def list_all(self):
        return [dict(p) for p in self._cache.values()]

    def list_visible(self, user_id, is_admin):
        if is_admin:
            return self.list_all()
        return [dict(p) for p in self._cache.values()
                if p.get("user_id") is None or p.get("user_id") == user_id]

    def can_view(self, profile_id, user_id, is_admin):
        p = self._cache.get(profile_id)
        if p is None:
            return False
        if is_admin:
            return True
        owner = p.get("user_id")
        return owner is None or owner == user_id

    def can_edit(self, profile_id, user_id, is_admin):
        p = self._cache.get(profile_id)
        if p is None:
            return False
        if is_admin:
            return True
        owner = p.get("user_id")
        return owner is not None and owner == user_id

    def update_if_owned(self, profile_id, user_id, is_admin, patch):
        with _get_mt_lock(profile_id):
            if not self.can_edit(profile_id, user_id, is_admin):
                return False, ["permission denied"]
            current = self._cache.get(profile_id)
            merged = {**current, **patch}
            errors = validate_mt_profile(merged)
            if errors:
                return False, errors
            merged["updated_at"] = int(time.time())
            merged["id"] = current["id"]
            merged["user_id"] = current["user_id"]
            merged["created_at"] = current["created_at"]
            self._save(merged)
            self._cache[profile_id] = merged
            return True, []

    def delete_if_owned(self, profile_id, user_id, is_admin):
        with _get_mt_lock(profile_id):
            if not self.can_edit(profile_id, user_id, is_admin):
                return False
            fpath = self._dir / f"{profile_id}.json"
            if fpath.exists():
                fpath.unlink()
            self._cache.pop(profile_id, None)
            return True
