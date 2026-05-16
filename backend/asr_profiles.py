"""
ASR profile management — v4.0 Phase 1.

ASR profiles are standalone entities (one file per profile in
config/asr_profiles/<uuid>.json) that describe a Whisper configuration:
engine, model_size, mode (same-lang / emergent-translate / translate-to-en),
language hint, initial_prompt, etc.

Per design doc §3.1 — replaces the `asr` sub-block of the legacy bundled
profile schema. Legacy profiles continue to work via backend/profiles.py
during P1-P2; P3 migration script will auto-split bundled profiles into
asr_profile + mt_profile + pipeline triples.
"""

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

VALID_ENGINES = {"whisper", "mlx-whisper"}
VALID_MODEL_SIZES = {"large-v3"}
VALID_MODES = {"same-lang", "emergent-translate", "translate-to-en"}
VALID_LANGUAGES = {"en", "zh", "ja", "ko", "fr", "de", "es"}
VALID_DEVICES = {"auto", "cpu", "cuda"}
MAX_INITIAL_PROMPT_CHARS = 512
MAX_NAME_CHARS = 64
MAX_DESCRIPTION_CHARS = 256


def validate_asr_profile(data: Any) -> list:
    """Return list of human-readable error strings; empty = valid."""
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

    model_size = data.get("model_size", "large-v3")
    if model_size not in VALID_MODEL_SIZES:
        errors.append(f"model_size must be one of {sorted(VALID_MODEL_SIZES)}")

    mode = data.get("mode")
    if mode not in VALID_MODES:
        errors.append(f"mode must be one of {sorted(VALID_MODES)}")

    lang = data.get("language")
    if lang not in VALID_LANGUAGES:
        errors.append(f"language must be one of {sorted(VALID_LANGUAGES)}")
    if mode == "translate-to-en" and lang != "en":
        errors.append("when mode is translate-to-en, language must be 'en' (Whisper translate output is always English)")

    for key in ("word_timestamps", "condition_on_previous_text", "simplified_to_traditional"):
        if key in data and not isinstance(data[key], bool):
            errors.append(f"{key} must be bool")

    initial_prompt = data.get("initial_prompt", "")
    if initial_prompt and (not isinstance(initial_prompt, str) or len(initial_prompt) > MAX_INITIAL_PROMPT_CHARS):
        errors.append(f"initial_prompt must be string of {MAX_INITIAL_PROMPT_CHARS} chars or less")

    device = data.get("device", "auto")
    if device not in VALID_DEVICES:
        errors.append(f"device must be one of {sorted(VALID_DEVICES)}")

    return errors


# ---------------------------------------------------------------------------
# Per-resource lock dict (mirrors backend/profiles.py R5 Phase 5 T2.8 pattern)
# ---------------------------------------------------------------------------

_ASR_LOCKS: dict = {}
_ASR_MASTER_LOCK = threading.Lock()


def _get_asr_lock(profile_id: str) -> threading.Lock:
    with _ASR_MASTER_LOCK:
        lock = _ASR_LOCKS.get(profile_id)
        if lock is None:
            lock = threading.Lock()
            _ASR_LOCKS[profile_id] = lock
        return lock


class ASRProfileManager:
    """CRUD + ownership for ASR profiles.

    Storage: one JSON file per profile in config_dir/asr_profiles/<uuid>.json.
    Cache: in-memory dict loaded at __init__; mutating ops write through to
    disk before updating cache.
    """

    DIRNAME = "asr_profiles"

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
                print(f"[asr_profiles] skip malformed file {fpath}: {exc}")

    def _save(self, profile: dict):
        (self._dir / f"{profile['id']}.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2)
        )

    def create(self, data: dict, user_id: Optional[int]) -> dict:
        errors = validate_asr_profile(data)
        if errors:
            raise ValueError("; ".join(errors))
        now = int(time.time())
        profile = {
            "id": str(uuid.uuid4()),
            "name": data["name"].strip(),
            "description": data.get("description", ""),
            "engine": data["engine"],
            "model_size": data.get("model_size", "large-v3"),
            "mode": data["mode"],
            "language": data["language"],
            "word_timestamps": bool(data.get("word_timestamps", False)),
            "initial_prompt": data.get("initial_prompt", ""),
            "condition_on_previous_text": bool(data.get("condition_on_previous_text", False)),
            "simplified_to_traditional": bool(data.get("simplified_to_traditional", False)),
            "device": data.get("device", "auto"),
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        self._save(profile)
        self._cache[profile["id"]] = profile
        return dict(profile)

    def get(self, profile_id: str) -> Optional[dict]:
        cached = self._cache.get(profile_id)
        return dict(cached) if cached else None

    def list_all(self) -> list:
        return [dict(p) for p in self._cache.values()]

    def list_visible(self, user_id: Optional[int], is_admin: bool) -> list:
        if is_admin:
            return self.list_all()
        return [
            dict(p) for p in self._cache.values()
            if p.get("user_id") is None or p.get("user_id") == user_id
        ]

    def can_view(self, profile_id: str, user_id: Optional[int], is_admin: bool) -> bool:
        p = self._cache.get(profile_id)
        if p is None:
            return False
        if is_admin:
            return True
        owner = p.get("user_id")
        return owner is None or owner == user_id

    def can_edit(self, profile_id: str, user_id: Optional[int], is_admin: bool) -> bool:
        p = self._cache.get(profile_id)
        if p is None:
            return False
        if is_admin:
            return True
        owner = p.get("user_id")
        return owner is not None and owner == user_id

    def update_if_owned(
        self,
        profile_id: str,
        user_id: Optional[int],
        is_admin: bool,
        patch: dict,
    ):
        with _get_asr_lock(profile_id):
            if not self.can_edit(profile_id, user_id, is_admin):
                return False, ["permission denied"]
            current = self._cache.get(profile_id)
            merged = {**current, **patch}
            errors = validate_asr_profile(merged)
            if errors:
                return False, errors
            merged["updated_at"] = int(time.time())
            merged["id"] = current["id"]          # immutable
            merged["user_id"] = current["user_id"]  # immutable
            merged["created_at"] = current["created_at"]  # immutable
            self._save(merged)
            self._cache[profile_id] = merged
            return True, []

    def delete_if_owned(
        self,
        profile_id: str,
        user_id: Optional[int],
        is_admin: bool,
    ) -> bool:
        with _get_asr_lock(profile_id):
            if not self.can_edit(profile_id, user_id, is_admin):
                return False
            fpath = self._dir / f"{profile_id}.json"
            if fpath.exists():
                fpath.unlink()
            self._cache.pop(profile_id, None)
            return True
