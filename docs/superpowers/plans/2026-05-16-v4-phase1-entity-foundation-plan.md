# v4.0 Phase 1 — Entity Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build 3 standalone entity managers (ASR profile / MT profile / Pipeline) with CRUD + per-resource ownership + REST endpoints, **without touching the legacy bundled profile pipeline** (which keeps running unchanged for now).

**Architecture:** Mirror the existing `backend/profiles.py` + `backend/glossary.py` pattern — JSON-file storage at `config/<entity>/<uuid>.json`, in-memory dict cache loaded at boot, per-resource `threading.Lock` dict for TOCTOU-free edits, `ProfileManager`-style class with `list_all` / `list_visible` / `get` / `create` / `update_if_owned` / `delete_if_owned` methods. Each manager also exposes a Pipeline-side **cascade visibility check** so a Pipeline referencing an ASR/MT profile or glossary the requesting user can't see is reported as broken (per design doc §7).

**Tech Stack:** Python 3.9, Flask 3.x, pytest. No new third-party deps. JSON-file storage. Existing R5 Phase 5 T2.8 `_PM_LOCKS` pattern carried forward per entity manager.

**Reference design doc:** [docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md](../specs/2026-05-16-asr-mt-emergent-pipeline-design.md). All schema fields in this plan match §3.1.1 (ASR), §3.2.1 (MT), §3.4.1 (Pipeline) of that doc.

**Out of scope for P1** (deferred to later phases):
- Stage executor / pipeline_runner / actual pipeline run (→ P2)
- Migration script + legacy compat shim (→ P3)
- Any frontend changes (→ P4)
- Deletion of `alignment_pipeline.py` / `sentence_pipeline.py` / `openrouter_engine.py` (→ P6)
- `en_text` / `zh_text` → `stage_outputs` segment schema rename (→ P3)
- `subtitle_source` enum generalization (→ P3 or P6)

---

## File Structure

### New backend files

| File | Responsibility |
|---|---|
| `backend/asr_profiles.py` | `ASRProfileManager` class + `validate_asr_profile()` helper |
| `backend/mt_profiles.py` | `MTProfileManager` class + `validate_mt_profile()` helper |
| `backend/pipelines.py` | `PipelineManager` class + `validate_pipeline()` helper (cascade ref check delegates to managers) |
| `backend/config/asr_profiles/` (dir) | Per-entity JSON storage (one file per ASR profile) |
| `backend/config/mt_profiles/` (dir) | Per-entity JSON storage |
| `backend/config/pipelines/` (dir) | Per-entity JSON storage |

### New test files

| File | Responsibility |
|---|---|
| `backend/tests/test_asr_profiles.py` | Manager + validator tests |
| `backend/tests/test_mt_profiles.py` | Manager + validator tests |
| `backend/tests/test_pipelines.py` | Manager + cascade ref tests |
| `backend/tests/test_v4_entity_endpoints.py` | Flask REST integration tests (24 endpoints total) |
| `backend/tests/test_v4_cascade_visibility.py` | Cross-manager cascade ownership tests |

### Modified backend files

| File | What changes |
|---|---|
| `backend/app.py` | (1) Boot: instantiate `_asr_profile_manager`, `_mt_profile_manager`, `_pipeline_manager` next to existing `_profile_manager`. (2) Register 24 new REST endpoints (6 per entity × 3 entities + 6 misc). All gated by `@login_required` + per-resource owner checks. |
| `backend/auth/decorators.py` | Add `@require_asr_profile_owner`, `@require_mt_profile_owner`, `@require_pipeline_owner` mirroring the existing `@require_file_owner` pattern. |

---

## Task Decomposition (19 tasks)

### Task 1: Storage dirs + module skeletons

**Files:**
- Create: `backend/config/asr_profiles/.gitkeep`
- Create: `backend/config/mt_profiles/.gitkeep`
- Create: `backend/config/pipelines/.gitkeep`
- Create: `backend/asr_profiles.py`
- Create: `backend/mt_profiles.py`
- Create: `backend/pipelines.py`

- [ ] **Step 1: Create storage directories with .gitkeep**

```bash
mkdir -p backend/config/asr_profiles backend/config/mt_profiles backend/config/pipelines
touch backend/config/asr_profiles/.gitkeep backend/config/mt_profiles/.gitkeep backend/config/pipelines/.gitkeep
```

- [ ] **Step 2: Create empty module files with docstrings**

`backend/asr_profiles.py`:
```python
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
```

Same pattern for `mt_profiles.py` (reference §3.2) and `pipelines.py` (reference §3.4).

- [ ] **Step 3: Run pytest baseline to confirm no regressions**

Run: `cd backend && pytest tests/ -x --tb=no -q 2>&1 | tail -5`
Expected: same pass count as pre-P1 baseline (currently ~780 backend tests + a few pre-existing failures unrelated to this work)

- [ ] **Step 4: Commit**

```bash
git add backend/config/asr_profiles backend/config/mt_profiles backend/config/pipelines \
        backend/asr_profiles.py backend/mt_profiles.py backend/pipelines.py
git commit -m "scaffold(v4): storage dirs + empty manager modules for ASR/MT profile + Pipeline"
```

---

### Task 2: ASR profile validator

**Files:**
- Modify: `backend/asr_profiles.py`
- Test: `backend/tests/test_asr_profiles.py` (new)

- [ ] **Step 1: Write the failing validator test**

```python
# backend/tests/test_asr_profiles.py
import pytest
from asr_profiles import validate_asr_profile


VALID_MIN_ASR = {
    "name": "粵語廣播 (emergent)",
    "engine": "mlx-whisper",
    "model_size": "large-v3",
    "mode": "emergent-translate",
    "language": "zh",
}


def test_valid_minimum_profile_returns_empty_errors():
    assert validate_asr_profile(VALID_MIN_ASR) == []


def test_missing_name_rejected():
    data = {**VALID_MIN_ASR, "name": ""}
    errors = validate_asr_profile(data)
    assert any("name" in e.lower() for e in errors)


def test_unknown_engine_rejected():
    data = {**VALID_MIN_ASR, "engine": "openai-realtime"}
    errors = validate_asr_profile(data)
    assert any("engine" in e.lower() for e in errors)


def test_unknown_mode_rejected():
    data = {**VALID_MIN_ASR, "mode": "auto-detect"}
    errors = validate_asr_profile(data)
    assert any("mode" in e.lower() for e in errors)


def test_translate_to_en_mode_forces_language_en():
    data = {**VALID_MIN_ASR, "mode": "translate-to-en", "language": "zh"}
    errors = validate_asr_profile(data)
    assert any("translate-to-en" in e.lower() and "language" in e.lower() for e in errors)


def test_unknown_language_rejected():
    data = {**VALID_MIN_ASR, "language": "tlh"}  # Klingon
    errors = validate_asr_profile(data)
    assert any("language" in e.lower() for e in errors)


def test_boolean_field_type_check():
    data = {**VALID_MIN_ASR, "word_timestamps": "yes"}
    errors = validate_asr_profile(data)
    assert any("word_timestamps" in e.lower() and "bool" in e.lower() for e in errors)


def test_initial_prompt_length_cap():
    data = {**VALID_MIN_ASR, "initial_prompt": "x" * 600}
    errors = validate_asr_profile(data)
    assert any("initial_prompt" in e.lower() and "512" in e for e in errors)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_asr_profiles.py -v`
Expected: FAIL with `ImportError: cannot import name 'validate_asr_profile' from 'asr_profiles'`

- [ ] **Step 3: Implement validator**

Add to `backend/asr_profiles.py`:
```python
from typing import Any

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_asr_profiles.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/asr_profiles.py backend/tests/test_asr_profiles.py
git commit -m "feat(v4): ASR profile schema validator (mode enum + translate-to-en lang lock)"
```

---

### Task 3: ASRProfileManager (CRUD + ownership)

**Files:**
- Modify: `backend/asr_profiles.py`
- Modify: `backend/tests/test_asr_profiles.py`

- [ ] **Step 1: Write failing manager tests**

Append to `backend/tests/test_asr_profiles.py`:
```python
import json
import pytest
from pathlib import Path
from asr_profiles import ASRProfileManager


@pytest.fixture
def manager(tmp_path):
    return ASRProfileManager(tmp_path)


def _make(manager, name="test", user_id=None):
    data = {
        "name": name,
        "engine": "mlx-whisper",
        "model_size": "large-v3",
        "mode": "emergent-translate",
        "language": "zh",
    }
    return manager.create(data, user_id=user_id)


def test_create_assigns_uuid_and_timestamps(manager):
    p = _make(manager)
    assert len(p["id"]) == 36
    assert p["created_at"] > 0
    assert p["updated_at"] == p["created_at"]
    assert p["user_id"] is None


def test_create_with_user_id_records_owner(manager):
    p = _make(manager, user_id=42)
    assert p["user_id"] == 42


def test_create_persists_to_json_file(manager, tmp_path):
    p = _make(manager)
    fpath = tmp_path / "asr_profiles" / f"{p['id']}.json"
    assert fpath.exists()
    loaded = json.loads(fpath.read_text())
    assert loaded["id"] == p["id"]


def test_create_rejects_invalid(manager):
    with pytest.raises(ValueError):
        manager.create({"name": ""}, user_id=None)


def test_get_returns_none_for_missing(manager):
    assert manager.get("nonexistent-id") is None


def test_list_all_returns_all_regardless_of_owner(manager):
    _make(manager, name="a", user_id=1)
    _make(manager, name="b", user_id=2)
    _make(manager, name="c", user_id=None)
    assert len(manager.list_all()) == 3


def test_list_visible_admin_sees_all(manager):
    _make(manager, name="a", user_id=1)
    _make(manager, name="b", user_id=2)
    _make(manager, name="c", user_id=None)
    visible = manager.list_visible(user_id=99, is_admin=True)
    assert len(visible) == 3


def test_list_visible_user_sees_own_plus_shared(manager):
    _make(manager, name="a", user_id=1)
    _make(manager, name="b", user_id=2)
    _make(manager, name="c", user_id=None)  # shared
    visible = manager.list_visible(user_id=1, is_admin=False)
    names = sorted(p["name"] for p in visible)
    assert names == ["a", "c"]


def test_can_view_owner(manager):
    p = _make(manager, user_id=5)
    assert manager.can_view(p["id"], user_id=5, is_admin=False) is True


def test_can_view_non_owner(manager):
    p = _make(manager, user_id=5)
    assert manager.can_view(p["id"], user_id=6, is_admin=False) is False


def test_can_view_shared(manager):
    p = _make(manager, user_id=None)
    assert manager.can_view(p["id"], user_id=99, is_admin=False) is True


def test_can_view_admin(manager):
    p = _make(manager, user_id=5)
    assert manager.can_view(p["id"], user_id=99, is_admin=True) is True


def test_update_if_owned_success(manager):
    p = _make(manager, user_id=5)
    ok, errors = manager.update_if_owned(
        p["id"], user_id=5, is_admin=False, patch={"name": "renamed"}
    )
    assert ok is True
    assert errors == []
    assert manager.get(p["id"])["name"] == "renamed"


def test_update_if_owned_rejects_non_owner(manager):
    p = _make(manager, user_id=5)
    ok, errors = manager.update_if_owned(
        p["id"], user_id=6, is_admin=False, patch={"name": "x"}
    )
    assert ok is False
    assert any("permission" in e.lower() or "forbid" in e.lower() for e in errors)


def test_update_if_owned_validates(manager):
    p = _make(manager, user_id=5)
    ok, errors = manager.update_if_owned(
        p["id"], user_id=5, is_admin=False, patch={"engine": "fake"}
    )
    assert ok is False
    assert errors  # validator picked it up


def test_delete_if_owned_success(manager):
    p = _make(manager, user_id=5)
    assert manager.delete_if_owned(p["id"], user_id=5, is_admin=False) is True
    assert manager.get(p["id"]) is None


def test_delete_if_owned_rejects_non_owner(manager):
    p = _make(manager, user_id=5)
    assert manager.delete_if_owned(p["id"], user_id=6, is_admin=False) is False


def test_manager_reloads_from_disk_on_init(manager, tmp_path):
    p = _make(manager, name="persisted")
    manager2 = ASRProfileManager(tmp_path)
    assert manager2.get(p["id"])["name"] == "persisted"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_asr_profiles.py -v -k "manager or create or get or list or can_view or update_if or delete_if or reloads"`
Expected: All new tests FAIL with `ImportError: cannot import name 'ASRProfileManager'`

- [ ] **Step 3: Implement manager**

Append to `backend/asr_profiles.py`:
```python
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

# Per-resource lock dict (mirrors backend/profiles.py R5 Phase 5 T2.8 pattern)
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

    def update_if_owned(self, profile_id: str, user_id: Optional[int], is_admin: bool, patch: dict):
        with _get_asr_lock(profile_id):
            if not self.can_edit(profile_id, user_id, is_admin):
                return False, ["permission denied"]
            current = self._cache.get(profile_id)
            merged = {**current, **patch}
            errors = validate_asr_profile(merged)
            if errors:
                return False, errors
            merged["updated_at"] = int(time.time())
            merged["id"] = current["id"]  # immutable
            merged["user_id"] = current["user_id"]  # immutable
            merged["created_at"] = current["created_at"]  # immutable
            self._save(merged)
            self._cache[profile_id] = merged
            return True, []

    def delete_if_owned(self, profile_id: str, user_id: Optional[int], is_admin: bool) -> bool:
        with _get_asr_lock(profile_id):
            if not self.can_edit(profile_id, user_id, is_admin):
                return False
            fpath = self._dir / f"{profile_id}.json"
            if fpath.exists():
                fpath.unlink()
            self._cache.pop(profile_id, None)
            return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_asr_profiles.py -v`
Expected: All tests (8 validator + 18 manager) pass

- [ ] **Step 5: Commit**

```bash
git add backend/asr_profiles.py backend/tests/test_asr_profiles.py
git commit -m "feat(v4): ASRProfileManager CRUD + per-resource ownership + TOCTOU lock"
```

---

### Task 4: MT profile validator + manager

**Files:**
- Modify: `backend/mt_profiles.py`
- Test: `backend/tests/test_mt_profiles.py` (new)

- [ ] **Step 1: Write failing validator + manager tests**

```python
# backend/tests/test_mt_profiles.py
import pytest
from mt_profiles import validate_mt_profile, MTProfileManager


VALID_MIN_MT = {
    "name": "粵語廣播風格",
    "engine": "qwen3.5-35b-a3b",
    "input_lang": "zh",
    "output_lang": "zh",
    "system_prompt": "你係香港電視廣播嘅字幕編輯員。",
    "user_message_template": "請將以下文字轉粵語廣播風格：\n{text}",
}


def test_valid_minimum_returns_empty_errors():
    assert validate_mt_profile(VALID_MIN_MT) == []


def test_engine_locked_to_qwen():
    data = {**VALID_MIN_MT, "engine": "claude-opus-4.5"}
    errors = validate_mt_profile(data)
    assert any("engine" in e.lower() for e in errors)


def test_input_must_equal_output_lang():
    data = {**VALID_MIN_MT, "input_lang": "en", "output_lang": "zh"}
    errors = validate_mt_profile(data)
    assert any("same-lang" in e.lower() or "must equal" in e.lower() for e in errors)


def test_user_message_template_must_contain_text_placeholder():
    data = {**VALID_MIN_MT, "user_message_template": "請翻譯。"}
    errors = validate_mt_profile(data)
    assert any("{text}" in e for e in errors)


def test_system_prompt_length_cap():
    data = {**VALID_MIN_MT, "system_prompt": "x" * 5000}
    errors = validate_mt_profile(data)
    assert any("4096" in e for e in errors)


def test_batch_size_range():
    data = {**VALID_MIN_MT, "batch_size": 0}
    errors = validate_mt_profile(data)
    assert any("batch_size" in e for e in errors)
    data = {**VALID_MIN_MT, "batch_size": 999}
    errors = validate_mt_profile(data)
    assert any("batch_size" in e for e in errors)


def test_temperature_range():
    data = {**VALID_MIN_MT, "temperature": -0.1}
    errors = validate_mt_profile(data)
    assert any("temperature" in e for e in errors)
    data = {**VALID_MIN_MT, "temperature": 3.0}
    errors = validate_mt_profile(data)
    assert any("temperature" in e for e in errors)


def test_parallel_batches_range():
    data = {**VALID_MIN_MT, "parallel_batches": 0}
    errors = validate_mt_profile(data)
    assert any("parallel_batches" in e for e in errors)


@pytest.fixture
def manager(tmp_path):
    return MTProfileManager(tmp_path)


def _make(manager, name="test", user_id=None):
    data = {**VALID_MIN_MT, "name": name}
    return manager.create(data, user_id=user_id)


def test_manager_create_and_get(manager):
    p = _make(manager)
    assert manager.get(p["id"])["system_prompt"] == VALID_MIN_MT["system_prompt"]


def test_manager_list_visible_ownership(manager):
    _make(manager, name="a", user_id=1)
    _make(manager, name="b", user_id=2)
    _make(manager, name="c", user_id=None)
    visible = manager.list_visible(user_id=1, is_admin=False)
    assert sorted(p["name"] for p in visible) == ["a", "c"]


def test_manager_update_if_owned_validates(manager):
    p = _make(manager, user_id=5)
    ok, errors = manager.update_if_owned(
        p["id"], user_id=5, is_admin=False, patch={"input_lang": "ja", "output_lang": "zh"}
    )
    assert ok is False  # cross-lang rejected
    assert any("same-lang" in e.lower() for e in errors)


def test_manager_delete_if_owned(manager):
    p = _make(manager, user_id=5)
    assert manager.delete_if_owned(p["id"], user_id=5, is_admin=False) is True
    assert manager.get(p["id"]) is None


def test_manager_persists_across_init(manager, tmp_path):
    p = _make(manager, name="persisted")
    manager2 = MTProfileManager(tmp_path)
    assert manager2.get(p["id"])["name"] == "persisted"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_mt_profiles.py -v`
Expected: All FAIL with `ImportError`

- [ ] **Step 3: Implement validator + manager**

Add to `backend/mt_profiles.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_mt_profiles.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add backend/mt_profiles.py backend/tests/test_mt_profiles.py
git commit -m "feat(v4): MTProfileManager — qwen-locked, same-lang enforce, {text} template required"
```

---

### Task 5: Pipeline validator (with cascade ref check)

**Files:**
- Modify: `backend/pipelines.py`
- Test: `backend/tests/test_pipelines.py` (new)

- [ ] **Step 1: Write failing validator tests**

```python
# backend/tests/test_pipelines.py
import pytest
from pipelines import validate_pipeline, PipelineManager
from asr_profiles import ASRProfileManager
from mt_profiles import MTProfileManager
from glossary import GlossaryManager  # existing v3.15


@pytest.fixture
def stack(tmp_path):
    """Provides asr_mgr + mt_mgr + glossary_mgr + pipeline_mgr."""
    asr = ASRProfileManager(tmp_path)
    mt = MTProfileManager(tmp_path)
    gloss = GlossaryManager(tmp_path / "glossaries")
    pipe = PipelineManager(tmp_path, asr_manager=asr, mt_manager=mt, glossary_manager=gloss)
    return asr, mt, gloss, pipe


def _make_asr(asr_mgr, user_id=None):
    return asr_mgr.create({
        "name": "asr-x", "engine": "mlx-whisper", "model_size": "large-v3",
        "mode": "same-lang", "language": "en",
    }, user_id=user_id)


def _make_mt(mt_mgr, user_id=None):
    return mt_mgr.create({
        "name": "mt-x", "engine": "qwen3.5-35b-a3b",
        "input_lang": "zh", "output_lang": "zh",
        "system_prompt": "test",
        "user_message_template": "polish: {text}",
    }, user_id=user_id)


VALID_FONT = {
    "family": "Noto Sans TC", "size": 35, "color": "#ffffff",
    "outline_color": "#000000", "outline_width": 2, "margin_bottom": 40,
    "subtitle_source": "auto", "bilingual_order": "target_top",
}


def test_valid_minimum_pipeline(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    mt = _make_mt(mt_mgr)
    data = {
        "name": "test-pipeline",
        "asr_profile_id": asr["id"],
        "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit",
                           "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }
    assert pipe_mgr.validate(data) == []


def test_unknown_asr_profile_id_rejected(stack):
    _, mt_mgr, _, pipe_mgr = stack
    mt = _make_mt(mt_mgr)
    data = {
        "name": "p", "asr_profile_id": "ghost-id",
        "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }
    errors = pipe_mgr.validate(data)
    assert any("asr_profile_id" in e for e in errors)


def test_unknown_mt_stage_id_rejected(stack):
    asr_mgr, _, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    data = {
        "name": "p", "asr_profile_id": asr["id"],
        "mt_stages": ["ghost-mt-id"],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }
    errors = pipe_mgr.validate(data)
    assert any("mt_stages" in e for e in errors)


def test_empty_mt_stages_allowed(stack):
    asr_mgr, _, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    data = {
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }
    assert pipe_mgr.validate(data) == []  # ASR-only pipeline is valid


def test_glossary_stage_enabled_requires_ids(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    mt = _make_mt(mt_mgr)
    data = {
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": True, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }
    errors = pipe_mgr.validate(data)
    assert any("glossary_ids" in e for e in errors)


def test_subtitle_source_enum_validated(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    mt = _make_mt(mt_mgr)
    bad_font = {**VALID_FONT, "subtitle_source": "en"}  # legacy enum, rejected in v4
    data = {
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": bad_font,
    }
    errors = pipe_mgr.validate(data)
    assert any("subtitle_source" in e for e in errors)


def test_bilingual_order_enum_validated(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    mt = _make_mt(mt_mgr)
    bad_font = {**VALID_FONT, "bilingual_order": "en_top"}
    data = {
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": bad_font,
    }
    errors = pipe_mgr.validate(data)
    assert any("bilingual_order" in e for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_pipelines.py -v -k "valid_minimum or unknown or empty_mt or glossary_stage_enabled or subtitle_source_enum or bilingual_order_enum"`
Expected: FAIL with `ImportError: cannot import name 'validate_pipeline'` or similar

- [ ] **Step 3: Implement Pipeline validator + manager (initial)**

Add to `backend/pipelines.py`:
```python
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

VALID_SUBTITLE_SOURCES = {"auto", "source", "target", "bilingual"}
VALID_BILINGUAL_ORDERS = {"source_top", "target_top"}
VALID_GLOSSARY_APPLY_ORDERS = {"explicit"}
VALID_GLOSSARY_APPLY_METHODS = {"string-match-then-llm"}
MAX_NAME_CHARS = 64
MAX_DESCRIPTION_CHARS = 256
MAX_MT_STAGES = 8

_PIPE_LOCKS: dict = {}
_PIPE_MASTER_LOCK = threading.Lock()


def _get_pipe_lock(pipeline_id: str) -> threading.Lock:
    with _PIPE_MASTER_LOCK:
        lock = _PIPE_LOCKS.get(pipeline_id)
        if lock is None:
            lock = threading.Lock()
            _PIPE_LOCKS[pipeline_id] = lock
        return lock


def _validate_font(font: Any) -> list:
    errors: list = []
    if not isinstance(font, dict):
        return ["font_config must be object"]
    for key in ("family", "color", "outline_color"):
        if not isinstance(font.get(key), str) or not font.get(key).strip():
            errors.append(f"font_config.{key} required (string)")
    for key in ("size", "outline_width", "margin_bottom"):
        if not isinstance(font.get(key), int) or font.get(key) < 0:
            errors.append(f"font_config.{key} required (non-negative int)")
    src = font.get("subtitle_source")
    if src not in VALID_SUBTITLE_SOURCES:
        errors.append(f"font_config.subtitle_source must be one of {sorted(VALID_SUBTITLE_SOURCES)}")
    order = font.get("bilingual_order")
    if order not in VALID_BILINGUAL_ORDERS:
        errors.append(f"font_config.bilingual_order must be one of {sorted(VALID_BILINGUAL_ORDERS)}")
    return errors


def _validate_glossary_stage(stage: Any) -> list:
    errors: list = []
    if not isinstance(stage, dict):
        return ["glossary_stage must be object"]
    enabled = stage.get("enabled")
    if not isinstance(enabled, bool):
        errors.append("glossary_stage.enabled must be bool")
    glossary_ids = stage.get("glossary_ids", [])
    if not isinstance(glossary_ids, list):
        errors.append("glossary_stage.glossary_ids must be list")
    elif enabled is True and len(glossary_ids) == 0:
        errors.append("glossary_stage.glossary_ids must be non-empty when enabled=true")
    elif any(not isinstance(g, str) or not g for g in glossary_ids):
        errors.append("glossary_stage.glossary_ids entries must be non-empty strings")
    if stage.get("apply_order") not in VALID_GLOSSARY_APPLY_ORDERS:
        errors.append(f"glossary_stage.apply_order must be one of {sorted(VALID_GLOSSARY_APPLY_ORDERS)}")
    if stage.get("apply_method") not in VALID_GLOSSARY_APPLY_METHODS:
        errors.append(f"glossary_stage.apply_method must be one of {sorted(VALID_GLOSSARY_APPLY_METHODS)}")
    return errors


class PipelineManager:
    """Pipeline CRUD + cascade ref validation against ASR/MT/Glossary managers."""

    DIRNAME = "pipelines"

    def __init__(self, config_dir, asr_manager, mt_manager, glossary_manager):
        self._config_dir = Path(config_dir)
        self._dir = self._config_dir / self.DIRNAME
        self._dir.mkdir(parents=True, exist_ok=True)
        self._asr_manager = asr_manager
        self._mt_manager = mt_manager
        self._glossary_manager = glossary_manager
        self._cache: dict = {}
        self._load_all()

    def _load_all(self):
        for fpath in self._dir.glob("*.json"):
            try:
                data = json.loads(fpath.read_text())
                if isinstance(data, dict) and data.get("id"):
                    self._cache[data["id"]] = data
            except Exception as exc:
                print(f"[pipelines] skip malformed file {fpath}: {exc}")

    def validate(self, data: Any) -> list:
        errors: list = []
        if not isinstance(data, dict):
            return ["payload must be object"]

        name = data.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            errors.append("name is required")
        elif len(name) > MAX_NAME_CHARS:
            errors.append(f"name must be {MAX_NAME_CHARS} chars or less")

        desc = data.get("description", "")
        if desc and (not isinstance(desc, str) or len(desc) > MAX_DESCRIPTION_CHARS):
            errors.append(f"description must be string of {MAX_DESCRIPTION_CHARS} chars or less")

        asr_id = data.get("asr_profile_id")
        if not asr_id or not isinstance(asr_id, str):
            errors.append("asr_profile_id is required")
        elif self._asr_manager.get(asr_id) is None:
            errors.append(f"asr_profile_id refers to unknown ASR profile: {asr_id}")

        mt_stages = data.get("mt_stages", [])
        if not isinstance(mt_stages, list):
            errors.append("mt_stages must be list of MT profile ids")
        elif len(mt_stages) > MAX_MT_STAGES:
            errors.append(f"mt_stages must be {MAX_MT_STAGES} entries or fewer")
        else:
            for idx, mt_id in enumerate(mt_stages):
                if not isinstance(mt_id, str) or not mt_id:
                    errors.append(f"mt_stages[{idx}] must be non-empty string")
                elif self._mt_manager.get(mt_id) is None:
                    errors.append(f"mt_stages[{idx}] refers to unknown MT profile: {mt_id}")

        gloss_stage = data.get("glossary_stage")
        if gloss_stage is None:
            errors.append("glossary_stage is required")
        else:
            gloss_errors = _validate_glossary_stage(gloss_stage)
            errors.extend(gloss_errors)
            if not gloss_errors and gloss_stage.get("enabled"):
                for idx, g_id in enumerate(gloss_stage.get("glossary_ids", [])):
                    if self._glossary_manager.get(g_id) is None:
                        errors.append(f"glossary_stage.glossary_ids[{idx}] refers to unknown glossary: {g_id}")

        font = data.get("font_config")
        if font is None:
            errors.append("font_config is required")
        else:
            errors.extend(_validate_font(font))

        return errors

    def _save(self, pipeline: dict):
        (self._dir / f"{pipeline['id']}.json").write_text(
            json.dumps(pipeline, ensure_ascii=False, indent=2)
        )

    def create(self, data: dict, user_id: Optional[int]) -> dict:
        errors = self.validate(data)
        if errors:
            raise ValueError("; ".join(errors))
        now = int(time.time())
        pipeline = {
            "id": str(uuid.uuid4()),
            "name": data["name"].strip(),
            "description": data.get("description", ""),
            "asr_profile_id": data["asr_profile_id"],
            "mt_stages": list(data["mt_stages"]),
            "glossary_stage": dict(data["glossary_stage"]),
            "font_config": dict(data["font_config"]),
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        self._save(pipeline)
        self._cache[pipeline["id"]] = pipeline
        return dict(pipeline)

    def get(self, pipeline_id):
        cached = self._cache.get(pipeline_id)
        return dict(cached) if cached else None

    def list_all(self):
        return [dict(p) for p in self._cache.values()]

    def list_visible(self, user_id, is_admin):
        if is_admin:
            return self.list_all()
        return [dict(p) for p in self._cache.values()
                if p.get("user_id") is None or p.get("user_id") == user_id]

    def can_view(self, pipeline_id, user_id, is_admin):
        p = self._cache.get(pipeline_id)
        if p is None:
            return False
        if is_admin:
            return True
        owner = p.get("user_id")
        return owner is None or owner == user_id

    def can_edit(self, pipeline_id, user_id, is_admin):
        p = self._cache.get(pipeline_id)
        if p is None:
            return False
        if is_admin:
            return True
        owner = p.get("user_id")
        return owner is not None and owner == user_id

    def update_if_owned(self, pipeline_id, user_id, is_admin, patch):
        with _get_pipe_lock(pipeline_id):
            if not self.can_edit(pipeline_id, user_id, is_admin):
                return False, ["permission denied"]
            current = self._cache.get(pipeline_id)
            merged = {**current, **patch}
            errors = self.validate(merged)
            if errors:
                return False, errors
            merged["updated_at"] = int(time.time())
            merged["id"] = current["id"]
            merged["user_id"] = current["user_id"]
            merged["created_at"] = current["created_at"]
            self._save(merged)
            self._cache[pipeline_id] = merged
            return True, []

    def delete_if_owned(self, pipeline_id, user_id, is_admin):
        with _get_pipe_lock(pipeline_id):
            if not self.can_edit(pipeline_id, user_id, is_admin):
                return False
            fpath = self._dir / f"{pipeline_id}.json"
            if fpath.exists():
                fpath.unlink()
            self._cache.pop(pipeline_id, None)
            return True
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_pipelines.py -v`
Expected: 7 validator tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/pipelines.py backend/tests/test_pipelines.py
git commit -m "feat(v4): PipelineManager validator with cascade ref check (ASR/MT/Glossary)"
```

---

### Task 6: Pipeline manager CRUD + visibility broken-link detection

**Files:**
- Modify: `backend/pipelines.py`
- Modify: `backend/tests/test_pipelines.py`

- [ ] **Step 1: Write failing manager + cascade ownership tests**

Append to `backend/tests/test_pipelines.py`:
```python
def test_create_pipeline_persists(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    mt = _make_mt(mt_mgr)
    p = pipe_mgr.create({
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }, user_id=5)
    assert p["user_id"] == 5
    assert pipe_mgr.get(p["id"])["name"] == "p"


def test_pipeline_update_validates_refs(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    mt = _make_mt(mt_mgr)
    p = pipe_mgr.create({
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }, user_id=5)
    ok, errors = pipe_mgr.update_if_owned(
        p["id"], user_id=5, is_admin=False,
        patch={"mt_stages": ["ghost-mt-id"]},
    )
    assert ok is False
    assert any("mt_stages" in e for e in errors)


def test_visibility_check_with_broken_refs(stack):
    """When a pipeline references an ASR profile owned by user A, but user B
    asks to view the pipeline (and B can view the pipeline because it's
    shared), B should see the pipeline but with a 'broken_refs' annotation
    listing the sub-resources B can't access."""
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr, user_id=1)  # owned by user 1 only
    mt = _make_mt(mt_mgr, user_id=None)  # shared
    p = pipe_mgr.create({
        "name": "shared-pipe",
        "asr_profile_id": asr["id"],
        "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }, user_id=None)  # pipeline itself is shared
    annotated = pipe_mgr.annotate_broken_refs(p, user_id=2, is_admin=False)
    assert annotated["broken_refs"] == {"asr_profile_id": asr["id"]}


def test_visibility_check_admin_no_broken_refs(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr, user_id=1)
    mt = _make_mt(mt_mgr, user_id=None)
    p = pipe_mgr.create({
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }, user_id=None)
    annotated = pipe_mgr.annotate_broken_refs(p, user_id=2, is_admin=True)
    assert annotated["broken_refs"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_pipelines.py::test_visibility_check_with_broken_refs -v`
Expected: FAIL with `AttributeError: 'PipelineManager' object has no attribute 'annotate_broken_refs'`

- [ ] **Step 3: Add `annotate_broken_refs` to PipelineManager**

Append to `class PipelineManager:` in `backend/pipelines.py`:
```python
    def annotate_broken_refs(self, pipeline: dict, user_id: Optional[int], is_admin: bool) -> dict:
        """Return pipeline dict with extra `broken_refs` key listing
        sub-resources the requesting user cannot view.

        broken_refs shape:
        {
            "asr_profile_id": "<id>",   # only present if not visible
            "mt_stages": ["<id>", ...],  # subset of mt_stages user can't see
            "glossary_ids": ["<id>", ...],
        }
        """
        out = dict(pipeline)
        broken: dict = {}
        if is_admin:
            out["broken_refs"] = broken
            return out
        asr_id = pipeline.get("asr_profile_id")
        if asr_id and not self._asr_manager.can_view(asr_id, user_id, is_admin):
            broken["asr_profile_id"] = asr_id
        broken_mt = [
            mt_id for mt_id in pipeline.get("mt_stages", [])
            if not self._mt_manager.can_view(mt_id, user_id, is_admin)
        ]
        if broken_mt:
            broken["mt_stages"] = broken_mt
        gloss_ids = pipeline.get("glossary_stage", {}).get("glossary_ids", [])
        broken_gloss = [
            g_id for g_id in gloss_ids
            if not self._glossary_manager.can_view(g_id, user_id, is_admin)
        ]
        if broken_gloss:
            broken["glossary_ids"] = broken_gloss
        out["broken_refs"] = broken
        return out
```

- [ ] **Step 4: Run all pipeline tests**

Run: `cd backend && pytest tests/test_pipelines.py -v`
Expected: 11 passed (7 validator + 4 manager)

- [ ] **Step 5: Commit**

```bash
git add backend/pipelines.py backend/tests/test_pipelines.py
git commit -m "feat(v4): PipelineManager CRUD + annotate_broken_refs cascade visibility"
```

---

### Task 7: Glossary manager `can_view` method

`GlossaryManager` from v3.15 doesn't have `can_view`. Add it.

**Files:**
- Modify: `backend/glossary.py`
- Test: `backend/tests/test_glossary_multilingual.py` (existing — append a test)

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_glossary_multilingual.py`:
```python
def test_can_view_owner(tmp_path):
    mgr = GlossaryManager(tmp_path)
    g = mgr.create({"name": "g1", "source_lang": "en", "target_lang": "zh"}, user_id=5)
    assert mgr.can_view(g["id"], user_id=5, is_admin=False) is True
    assert mgr.can_view(g["id"], user_id=6, is_admin=False) is False
    assert mgr.can_view(g["id"], user_id=99, is_admin=True) is True
    # shared (user_id=None) visible to all
    g_shared = mgr.create({"name": "g2", "source_lang": "en", "target_lang": "zh"}, user_id=None)
    assert mgr.can_view(g_shared["id"], user_id=999, is_admin=False) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_glossary_multilingual.py::test_can_view_owner -v`
Expected: FAIL with `AttributeError: 'GlossaryManager' object has no attribute 'can_view'`

- [ ] **Step 3: Add `can_view` to GlossaryManager**

Locate the existing `can_edit` method in `backend/glossary.py` (R5 Phase 5 D4) and add a sibling `can_view` immediately above it:
```python
    def can_view(self, glossary_id: str, user_id, is_admin: bool) -> bool:
        g = self._cache.get(glossary_id)
        if g is None:
            return False
        if is_admin:
            return True
        owner = g.get("user_id")
        return owner is None or owner == user_id
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_glossary_multilingual.py -v`
Expected: all pass including the new `test_can_view_owner`

- [ ] **Step 5: Commit**

```bash
git add backend/glossary.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(v4): GlossaryManager.can_view — mirror v3.13 ProfileManager Phase 5 pattern"
```

---

### Task 8: Auth decorators for new entities

**Files:**
- Modify: `backend/auth/decorators.py`
- Test: `backend/tests/test_v4_decorators.py` (new)

- [ ] **Step 1: Write failing decorator tests**

```python
# backend/tests/test_v4_decorators.py
"""Tests for @require_asr_profile_owner / @require_mt_profile_owner /
@require_pipeline_owner — mirror of @require_file_owner."""

import pytest
from unittest.mock import MagicMock, patch
from flask import Flask
from auth.decorators import (
    require_asr_profile_owner,
    require_mt_profile_owner,
    require_pipeline_owner,
)


@pytest.fixture
def app():
    a = Flask(__name__)
    a.config["LOGIN_DISABLED"] = True
    a.config["R5_AUTH_BYPASS"] = False
    return a


def test_require_asr_profile_owner_403_for_non_owner(app):
    fake_user = MagicMock(id=99, is_admin=False, is_authenticated=True)
    fake_mgr = MagicMock()
    fake_mgr.can_view.return_value = False

    @app.route("/test/<profile_id>")
    @require_asr_profile_owner
    def view(profile_id):
        return "ok", 200

    with patch("auth.decorators.current_user", fake_user), \
         patch("auth.decorators._asr_manager", fake_mgr, create=True):
        client = app.test_client()
        resp = client.get("/test/some-id")
    assert resp.status_code == 403


def test_require_asr_profile_owner_200_for_owner(app):
    fake_user = MagicMock(id=99, is_admin=False, is_authenticated=True)
    fake_mgr = MagicMock()
    fake_mgr.can_view.return_value = True

    @app.route("/test/<profile_id>")
    @require_asr_profile_owner
    def view(profile_id):
        return "ok", 200

    with patch("auth.decorators.current_user", fake_user), \
         patch("auth.decorators._asr_manager", fake_mgr, create=True):
        client = app.test_client()
        resp = client.get("/test/some-id")
    assert resp.status_code == 200


def test_require_mt_profile_owner_uses_mt_manager(app):
    fake_user = MagicMock(id=1, is_admin=False, is_authenticated=True)
    fake_mgr = MagicMock()
    fake_mgr.can_view.return_value = False

    @app.route("/test/<profile_id>")
    @require_mt_profile_owner
    def view(profile_id):
        return "ok", 200

    with patch("auth.decorators.current_user", fake_user), \
         patch("auth.decorators._mt_manager", fake_mgr, create=True):
        client = app.test_client()
        resp = client.get("/test/some-id")
    assert resp.status_code == 403


def test_require_pipeline_owner_uses_pipeline_manager(app):
    fake_user = MagicMock(id=1, is_admin=False, is_authenticated=True)
    fake_mgr = MagicMock()
    fake_mgr.can_view.return_value = False

    @app.route("/test/<pipeline_id>")
    @require_pipeline_owner
    def view(pipeline_id):
        return "ok", 200

    with patch("auth.decorators.current_user", fake_user), \
         patch("auth.decorators._pipeline_manager", fake_mgr, create=True):
        client = app.test_client()
        resp = client.get("/test/some-id")
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_v4_decorators.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement decorators**

Append to `backend/auth/decorators.py`:
```python
# v4.0 Phase 1 — entity-specific owner decorators
# Mirror require_file_owner pattern. The manager modules are imported
# lazily at call time so this module can stay decoupled from app.py boot.

_asr_manager = None
_mt_manager = None
_pipeline_manager = None


def set_v4_managers(asr_manager, mt_manager, pipeline_manager):
    """Called from app.py boot after managers are instantiated."""
    global _asr_manager, _mt_manager, _pipeline_manager
    _asr_manager = asr_manager
    _mt_manager = mt_manager
    _pipeline_manager = pipeline_manager


def _make_owner_decorator(manager_attr_name: str, url_arg_name: str):
    """Build a decorator that checks can_view on the given manager."""
    def decorator(fn):
        from functools import wraps

        @wraps(fn)
        def wrapper(*args, **kwargs):
            from flask import current_app, abort, jsonify
            from flask_login import current_user

            if current_app.config.get("R5_AUTH_BYPASS"):
                return fn(*args, **kwargs)

            if not getattr(current_user, "is_authenticated", False):
                return jsonify({"error": "authentication required"}), 401

            resource_id = kwargs.get(url_arg_name)
            mgr = globals().get(manager_attr_name)
            if mgr is None:
                return jsonify({"error": f"{manager_attr_name} not initialised"}), 500

            is_admin = bool(getattr(current_user, "is_admin", False))
            user_id = current_user.id

            if not mgr.can_view(resource_id, user_id, is_admin):
                return jsonify({"error": "not found"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


require_asr_profile_owner = _make_owner_decorator("_asr_manager", "profile_id")
require_mt_profile_owner = _make_owner_decorator("_mt_manager", "profile_id")
require_pipeline_owner = _make_owner_decorator("_pipeline_manager", "pipeline_id")
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_v4_decorators.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/auth/decorators.py backend/tests/test_v4_decorators.py
git commit -m "feat(v4): entity-specific owner decorators (ASR/MT profile + pipeline)"
```

---

### Task 9: app.py boot — instantiate managers + wire decorators

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: Locate existing manager initialisation**

Existing pattern in `backend/app.py` (search for `_profile_manager = ProfileManager`):
```python
_profile_manager = ProfileManager(CONFIG_DIR)
_glossary_manager = GlossaryManager(CONFIG_DIR / "glossaries")
_language_config_manager = LanguageConfigManager(CONFIG_DIR / "languages")
```

- [ ] **Step 2: Add v4 manager instantiation immediately after existing managers**

Find the block above and append:
```python
# v4.0 Phase 1 — new entity managers (P1: CRUD only; P2 will add stage executor)
from asr_profiles import ASRProfileManager
from mt_profiles import MTProfileManager
from pipelines import PipelineManager

_asr_profile_manager = ASRProfileManager(CONFIG_DIR)
_mt_profile_manager = MTProfileManager(CONFIG_DIR)
_pipeline_manager = PipelineManager(
    CONFIG_DIR,
    asr_manager=_asr_profile_manager,
    mt_manager=_mt_profile_manager,
    glossary_manager=_glossary_manager,
)

# Wire decorators
from auth.decorators import set_v4_managers
set_v4_managers(_asr_profile_manager, _mt_profile_manager, _pipeline_manager)
```

- [ ] **Step 3: Run baseline pytest to confirm no regression**

Run: `cd backend && pytest tests/ -x --tb=no -q 2>&1 | tail -5`
Expected: same pass count as pre-P1 baseline (no new failures)

- [ ] **Step 4: Commit**

```bash
git add backend/app.py
git commit -m "feat(v4): boot ASR/MT/Pipeline managers + wire owner decorators"
```

---

### Task 10: REST endpoints — ASR profile CRUD

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_v4_entity_endpoints.py` (new)

- [ ] **Step 1: Write failing endpoint tests**

```python
# backend/tests/test_v4_entity_endpoints.py
"""Integration tests for v4 entity REST endpoints (ASR profile / MT profile /
Pipeline). Uses Flask test_client with LOGIN_DISABLED + R5_AUTH_BYPASS so
ownership checks short-circuit (admin-equivalent)."""

import json
import pytest


@pytest.fixture
def client():
    """Reuses the existing app.py boot path. R5_AUTH_BYPASS=True turns the
    @require_*_owner decorators into no-ops so we can hit endpoints without
    setting up real auth."""
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["LOGIN_DISABLED"] = True
    app_module.app.config["R5_AUTH_BYPASS"] = True
    with app_module.app.test_client() as c:
        yield c


VALID_ASR = {
    "name": "test-asr",
    "engine": "mlx-whisper",
    "model_size": "large-v3",
    "mode": "emergent-translate",
    "language": "zh",
}


def test_create_asr_profile_201(client):
    resp = client.post("/api/asr_profiles",
                       data=json.dumps(VALID_ASR),
                       content_type="application/json")
    assert resp.status_code == 201
    body = resp.get_json()
    assert len(body["id"]) == 36
    assert body["name"] == "test-asr"


def test_create_asr_profile_400_on_invalid(client):
    bad = {**VALID_ASR, "mode": "garbage"}
    resp = client.post("/api/asr_profiles",
                       data=json.dumps(bad),
                       content_type="application/json")
    assert resp.status_code == 400
    assert "errors" in resp.get_json()


def test_get_asr_profile_404_when_missing(client):
    resp = client.get("/api/asr_profiles/nonexistent")
    assert resp.status_code == 404


def test_list_asr_profiles(client):
    client.post("/api/asr_profiles",
                data=json.dumps(VALID_ASR),
                content_type="application/json")
    resp = client.get("/api/asr_profiles")
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body["asr_profiles"], list)
    assert any(p["name"] == "test-asr" for p in body["asr_profiles"])


def test_patch_asr_profile(client):
    create = client.post("/api/asr_profiles",
                         data=json.dumps(VALID_ASR),
                         content_type="application/json")
    pid = create.get_json()["id"]
    resp = client.patch(f"/api/asr_profiles/{pid}",
                        data=json.dumps({"name": "renamed"}),
                        content_type="application/json")
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "renamed"


def test_delete_asr_profile(client):
    create = client.post("/api/asr_profiles",
                         data=json.dumps(VALID_ASR),
                         content_type="application/json")
    pid = create.get_json()["id"]
    resp = client.delete(f"/api/asr_profiles/{pid}")
    assert resp.status_code == 204
    follow = client.get(f"/api/asr_profiles/{pid}")
    assert follow.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_v4_entity_endpoints.py -v -k "asr"`
Expected: All FAIL with 404 (route not registered yet)

- [ ] **Step 3: Implement ASR profile routes in app.py**

Find a logical location in `backend/app.py` (e.g., immediately after `@app.route('/api/profiles')`). Add:
```python
# ============================================================
# v4.0 Phase 1 — ASR profile REST endpoints
# ============================================================

@app.route('/api/asr_profiles', methods=['GET'])
@login_required
def list_asr_profiles():
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False))
    profiles = _asr_profile_manager.list_visible(user_id, is_admin)
    return jsonify({"asr_profiles": profiles}), 200


@app.route('/api/asr_profiles', methods=['POST'])
@login_required
def create_asr_profile():
    data = request.get_json(silent=True) or {}
    user_id = getattr(current_user, "id", None)
    try:
        profile = _asr_profile_manager.create(data, user_id=user_id)
    except ValueError as exc:
        return jsonify({"errors": str(exc).split("; ")}), 400
    return jsonify(profile), 201


@app.route('/api/asr_profiles/<profile_id>', methods=['GET'])
@login_required
@require_asr_profile_owner
def get_asr_profile(profile_id):
    profile = _asr_profile_manager.get(profile_id)
    if profile is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(profile), 200


@app.route('/api/asr_profiles/<profile_id>', methods=['PATCH'])
@login_required
@require_asr_profile_owner
def patch_asr_profile(profile_id):
    patch = request.get_json(silent=True) or {}
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False))
    ok, errors = _asr_profile_manager.update_if_owned(
        profile_id, user_id, is_admin, patch
    )
    if not ok:
        if "permission denied" in errors:
            return jsonify({"errors": errors}), 403
        return jsonify({"errors": errors}), 400
    return jsonify(_asr_profile_manager.get(profile_id)), 200


@app.route('/api/asr_profiles/<profile_id>', methods=['DELETE'])
@login_required
@require_asr_profile_owner
def delete_asr_profile(profile_id):
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False))
    if not _asr_profile_manager.delete_if_owned(profile_id, user_id, is_admin):
        return jsonify({"error": "forbidden"}), 403
    return "", 204
```

Also at the top of `app.py`, ensure `require_asr_profile_owner` is imported:
```python
from auth.decorators import (
    login_required,
    require_file_owner,
    admin_required,
    require_asr_profile_owner,
    require_mt_profile_owner,
    require_pipeline_owner,
)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_v4_entity_endpoints.py -v -k "asr"`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_v4_entity_endpoints.py
git commit -m "feat(v4): ASR profile CRUD endpoints (/api/asr_profiles)"
```

---

### Task 11: REST endpoints — MT profile CRUD

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/tests/test_v4_entity_endpoints.py`

- [ ] **Step 1: Append failing MT endpoint tests**

```python
VALID_MT = {
    "name": "test-mt",
    "engine": "qwen3.5-35b-a3b",
    "input_lang": "zh",
    "output_lang": "zh",
    "system_prompt": "test",
    "user_message_template": "polish: {text}",
}


def test_create_mt_profile_201(client):
    resp = client.post("/api/mt_profiles",
                       data=json.dumps(VALID_MT),
                       content_type="application/json")
    assert resp.status_code == 201
    assert len(resp.get_json()["id"]) == 36


def test_create_mt_profile_400_cross_lang(client):
    bad = {**VALID_MT, "input_lang": "en", "output_lang": "zh"}
    resp = client.post("/api/mt_profiles",
                       data=json.dumps(bad),
                       content_type="application/json")
    assert resp.status_code == 400


def test_create_mt_profile_400_missing_text_placeholder(client):
    bad = {**VALID_MT, "user_message_template": "just text"}
    resp = client.post("/api/mt_profiles",
                       data=json.dumps(bad),
                       content_type="application/json")
    assert resp.status_code == 400


def test_list_mt_profiles(client):
    client.post("/api/mt_profiles",
                data=json.dumps(VALID_MT),
                content_type="application/json")
    resp = client.get("/api/mt_profiles")
    assert resp.status_code == 200
    assert isinstance(resp.get_json()["mt_profiles"], list)


def test_patch_mt_profile(client):
    create = client.post("/api/mt_profiles",
                         data=json.dumps(VALID_MT),
                         content_type="application/json")
    pid = create.get_json()["id"]
    resp = client.patch(f"/api/mt_profiles/{pid}",
                        data=json.dumps({"name": "renamed"}),
                        content_type="application/json")
    assert resp.status_code == 200


def test_delete_mt_profile(client):
    create = client.post("/api/mt_profiles",
                         data=json.dumps(VALID_MT),
                         content_type="application/json")
    pid = create.get_json()["id"]
    resp = client.delete(f"/api/mt_profiles/{pid}")
    assert resp.status_code == 204
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_v4_entity_endpoints.py -v -k "mt"`
Expected: All FAIL with 404

- [ ] **Step 3: Implement MT profile routes**

Add to `backend/app.py` immediately after the ASR profile block:
```python
# ============================================================
# v4.0 Phase 1 — MT profile REST endpoints
# ============================================================

@app.route('/api/mt_profiles', methods=['GET'])
@login_required
def list_mt_profiles():
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False))
    profiles = _mt_profile_manager.list_visible(user_id, is_admin)
    return jsonify({"mt_profiles": profiles}), 200


@app.route('/api/mt_profiles', methods=['POST'])
@login_required
def create_mt_profile():
    data = request.get_json(silent=True) or {}
    user_id = getattr(current_user, "id", None)
    try:
        profile = _mt_profile_manager.create(data, user_id=user_id)
    except ValueError as exc:
        return jsonify({"errors": str(exc).split("; ")}), 400
    return jsonify(profile), 201


@app.route('/api/mt_profiles/<profile_id>', methods=['GET'])
@login_required
@require_mt_profile_owner
def get_mt_profile(profile_id):
    profile = _mt_profile_manager.get(profile_id)
    if profile is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(profile), 200


@app.route('/api/mt_profiles/<profile_id>', methods=['PATCH'])
@login_required
@require_mt_profile_owner
def patch_mt_profile(profile_id):
    patch = request.get_json(silent=True) or {}
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False))
    ok, errors = _mt_profile_manager.update_if_owned(
        profile_id, user_id, is_admin, patch
    )
    if not ok:
        if "permission denied" in errors:
            return jsonify({"errors": errors}), 403
        return jsonify({"errors": errors}), 400
    return jsonify(_mt_profile_manager.get(profile_id)), 200


@app.route('/api/mt_profiles/<profile_id>', methods=['DELETE'])
@login_required
@require_mt_profile_owner
def delete_mt_profile(profile_id):
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False))
    if not _mt_profile_manager.delete_if_owned(profile_id, user_id, is_admin):
        return jsonify({"error": "forbidden"}), 403
    return "", 204
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_v4_entity_endpoints.py -v -k "mt"`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_v4_entity_endpoints.py
git commit -m "feat(v4): MT profile CRUD endpoints (/api/mt_profiles)"
```

---

### Task 12: REST endpoints — Pipeline CRUD

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/tests/test_v4_entity_endpoints.py`

- [ ] **Step 1: Append failing Pipeline endpoint tests**

```python
def _create_asr_and_mt(client):
    asr = client.post("/api/asr_profiles",
                      data=json.dumps(VALID_ASR),
                      content_type="application/json").get_json()
    mt = client.post("/api/mt_profiles",
                     data=json.dumps(VALID_MT),
                     content_type="application/json").get_json()
    return asr["id"], mt["id"]


VALID_FONT_CONFIG = {
    "family": "Noto Sans TC", "size": 35, "color": "#ffffff",
    "outline_color": "#000000", "outline_width": 2, "margin_bottom": 40,
    "subtitle_source": "auto", "bilingual_order": "target_top",
}


def test_create_pipeline_201(client):
    asr_id, mt_id = _create_asr_and_mt(client)
    data = {
        "name": "test-pipeline",
        "asr_profile_id": asr_id,
        "mt_stages": [mt_id],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT_CONFIG,
    }
    resp = client.post("/api/pipelines",
                       data=json.dumps(data),
                       content_type="application/json")
    assert resp.status_code == 201


def test_create_pipeline_400_unknown_asr(client):
    asr_id, mt_id = _create_asr_and_mt(client)
    data = {
        "name": "p", "asr_profile_id": "ghost", "mt_stages": [mt_id],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT_CONFIG,
    }
    resp = client.post("/api/pipelines",
                       data=json.dumps(data),
                       content_type="application/json")
    assert resp.status_code == 400


def test_list_pipelines(client):
    asr_id, mt_id = _create_asr_and_mt(client)
    client.post("/api/pipelines",
                data=json.dumps({"name": "p",
                                 "asr_profile_id": asr_id,
                                 "mt_stages": [mt_id],
                                 "glossary_stage": {"enabled": False, "glossary_ids": [],
                                                    "apply_order": "explicit",
                                                    "apply_method": "string-match-then-llm"},
                                 "font_config": VALID_FONT_CONFIG}),
                content_type="application/json")
    resp = client.get("/api/pipelines")
    assert resp.status_code == 200
    assert isinstance(resp.get_json()["pipelines"], list)


def test_get_pipeline_includes_broken_refs_annotation(client):
    asr_id, mt_id = _create_asr_and_mt(client)
    create = client.post("/api/pipelines",
                         data=json.dumps({"name": "p",
                                          "asr_profile_id": asr_id,
                                          "mt_stages": [mt_id],
                                          "glossary_stage": {"enabled": False, "glossary_ids": [],
                                                             "apply_order": "explicit",
                                                             "apply_method": "string-match-then-llm"},
                                          "font_config": VALID_FONT_CONFIG}),
                         content_type="application/json")
    pid = create.get_json()["id"]
    resp = client.get(f"/api/pipelines/{pid}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "broken_refs" in body
    # under R5_AUTH_BYPASS the request is admin-equivalent so broken_refs is {}
    assert body["broken_refs"] == {}


def test_patch_pipeline_validates_refs(client):
    asr_id, mt_id = _create_asr_and_mt(client)
    create = client.post("/api/pipelines",
                         data=json.dumps({"name": "p",
                                          "asr_profile_id": asr_id,
                                          "mt_stages": [mt_id],
                                          "glossary_stage": {"enabled": False, "glossary_ids": [],
                                                             "apply_order": "explicit",
                                                             "apply_method": "string-match-then-llm"},
                                          "font_config": VALID_FONT_CONFIG}),
                         content_type="application/json")
    pid = create.get_json()["id"]
    resp = client.patch(f"/api/pipelines/{pid}",
                        data=json.dumps({"mt_stages": ["ghost-id"]}),
                        content_type="application/json")
    assert resp.status_code == 400


def test_delete_pipeline(client):
    asr_id, mt_id = _create_asr_and_mt(client)
    create = client.post("/api/pipelines",
                         data=json.dumps({"name": "p",
                                          "asr_profile_id": asr_id,
                                          "mt_stages": [mt_id],
                                          "glossary_stage": {"enabled": False, "glossary_ids": [],
                                                             "apply_order": "explicit",
                                                             "apply_method": "string-match-then-llm"},
                                          "font_config": VALID_FONT_CONFIG}),
                         content_type="application/json")
    pid = create.get_json()["id"]
    resp = client.delete(f"/api/pipelines/{pid}")
    assert resp.status_code == 204
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_v4_entity_endpoints.py -v -k "pipeline"`
Expected: All FAIL with 404

- [ ] **Step 3: Implement Pipeline routes**

Add to `backend/app.py`:
```python
# ============================================================
# v4.0 Phase 1 — Pipeline REST endpoints
# ============================================================

@app.route('/api/pipelines', methods=['GET'])
@login_required
def list_pipelines():
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False))
    pipelines = _pipeline_manager.list_visible(user_id, is_admin)
    annotated = [
        _pipeline_manager.annotate_broken_refs(p, user_id, is_admin)
        for p in pipelines
    ]
    return jsonify({"pipelines": annotated}), 200


@app.route('/api/pipelines', methods=['POST'])
@login_required
def create_pipeline():
    data = request.get_json(silent=True) or {}
    user_id = getattr(current_user, "id", None)
    try:
        pipeline = _pipeline_manager.create(data, user_id=user_id)
    except ValueError as exc:
        return jsonify({"errors": str(exc).split("; ")}), 400
    return jsonify(pipeline), 201


@app.route('/api/pipelines/<pipeline_id>', methods=['GET'])
@login_required
@require_pipeline_owner
def get_pipeline(pipeline_id):
    pipeline = _pipeline_manager.get(pipeline_id)
    if pipeline is None:
        return jsonify({"error": "not found"}), 404
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False))
    annotated = _pipeline_manager.annotate_broken_refs(pipeline, user_id, is_admin)
    return jsonify(annotated), 200


@app.route('/api/pipelines/<pipeline_id>', methods=['PATCH'])
@login_required
@require_pipeline_owner
def patch_pipeline(pipeline_id):
    patch = request.get_json(silent=True) or {}
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False))
    ok, errors = _pipeline_manager.update_if_owned(
        pipeline_id, user_id, is_admin, patch
    )
    if not ok:
        if "permission denied" in errors:
            return jsonify({"errors": errors}), 403
        return jsonify({"errors": errors}), 400
    return jsonify(_pipeline_manager.get(pipeline_id)), 200


@app.route('/api/pipelines/<pipeline_id>', methods=['DELETE'])
@login_required
@require_pipeline_owner
def delete_pipeline(pipeline_id):
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False))
    if not _pipeline_manager.delete_if_owned(pipeline_id, user_id, is_admin):
        return jsonify({"error": "forbidden"}), 403
    return "", 204
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_v4_entity_endpoints.py -v`
Expected: 18 passed (6 ASR + 6 MT + 6 Pipeline)

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_v4_entity_endpoints.py
git commit -m "feat(v4): Pipeline CRUD endpoints with cascade ref validation + broken_refs annotation"
```

---

### Task 13: Cross-manager cascade ownership integration test

**Files:**
- Test: `backend/tests/test_v4_cascade_visibility.py` (new)

This test goes through real auth flow (no R5_AUTH_BYPASS) so we exercise the actual decorator + ownership cascade.

- [ ] **Step 1: Write failing cascade integration test**

```python
# backend/tests/test_v4_cascade_visibility.py
"""End-to-end test: User A creates ASR profile (private). User B creates
Pipeline (shared) that references it. User C lists pipelines — sees the
pipeline with broken_refs annotation."""

import json
import pytest
from auth.users import create_user, delete_user, init_db


@pytest.fixture
def app_with_real_auth(tmp_path):
    """Reset auth DB to a known state for this test, then yield app."""
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["LOGIN_DISABLED"] = False
    app_module.app.config["R5_AUTH_BYPASS"] = False
    # Cleanup helper users from any prior test run
    for username in ("alice", "bob", "carol"):
        try:
            delete_user(username)
        except Exception:
            pass
    init_db()
    yield app_module.app
    for username in ("alice", "bob", "carol"):
        try:
            delete_user(username)
        except Exception:
            pass


def _login(client, username, password):
    resp = client.post("/login",
                       data=json.dumps({"username": username, "password": password}),
                       content_type="application/json")
    assert resp.status_code == 200


def test_broken_refs_annotated_when_subresource_invisible(app_with_real_auth):
    app = app_with_real_auth
    alice = create_user("alice", "AlicePass1!", is_admin=False)
    bob = create_user("bob", "BobPass1!", is_admin=False)
    carol = create_user("carol", "CarolPass1!", is_admin=False)

    # Alice creates private ASR + shared MT
    with app.test_client() as client_a:
        _login(client_a, "alice", "AlicePass1!")
        asr = client_a.post("/api/asr_profiles",
                            data=json.dumps({"name": "alice-private",
                                             "engine": "mlx-whisper",
                                             "model_size": "large-v3",
                                             "mode": "same-lang",
                                             "language": "en"}),
                            content_type="application/json").get_json()
        # Alice can also create the MT, then mark it shared (user_id=None)
        # but for the test, easier: have Bob create the MT
    with app.test_client() as client_b:
        _login(client_b, "bob", "BobPass1!")
        # First, Bob can't create with shared user_id (decorator doesn't allow that)
        # so we directly use the manager — for this test we have admin create the shared MT
        pass

    # Carol attempts to view a pipeline that uses Alice's private ASR
    # — but Carol can't even create the pipeline if the ref is invalid for her.
    # So setup: admin creates the pipeline (shared) so anyone can view it.
    from app import _pipeline_manager, _mt_profile_manager
    shared_mt = _mt_profile_manager.create({
        "name": "shared-mt",
        "engine": "qwen3.5-35b-a3b",
        "input_lang": "zh", "output_lang": "zh",
        "system_prompt": "test",
        "user_message_template": "polish: {text}",
    }, user_id=None)
    shared_pipe = _pipeline_manager.create({
        "name": "shared-pipe",
        "asr_profile_id": asr["id"],   # alice-private
        "mt_stages": [shared_mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit",
                           "apply_method": "string-match-then-llm"},
        "font_config": {"family": "Noto Sans TC", "size": 35, "color": "#ffffff",
                        "outline_color": "#000000", "outline_width": 2,
                        "margin_bottom": 40, "subtitle_source": "auto",
                        "bilingual_order": "target_top"},
    }, user_id=None)

    with app.test_client() as client_c:
        _login(client_c, "carol", "CarolPass1!")
        resp = client_c.get(f"/api/pipelines/{shared_pipe['id']}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["broken_refs"] == {"asr_profile_id": asr["id"]}

    # Cleanup
    _pipeline_manager.delete_if_owned(shared_pipe["id"], None, is_admin=True)
    _mt_profile_manager.delete_if_owned(shared_mt["id"], None, is_admin=True)
    # alice's asr cleaned via test fixture
```

- [ ] **Step 2: Run test to verify it fails (probably permissions mismatch first)**

Run: `cd backend && pytest tests/test_v4_cascade_visibility.py -v`
Expected: depending on initial state — may pass first try if all earlier tasks correct. If FAIL, address whatever Flask gives back (most likely 403 from `@require_pipeline_owner` if pipeline.user_id=None semantics not quite right).

- [ ] **Step 3: Resolve any failure by adjusting `can_view` semantics**

Already designed: `can_view` returns True when `user_id is None` (shared). Should work first try. If 403 happens, audit `auth/decorators.py::_make_owner_decorator` — the `can_view` should be called and pass when pipeline is shared.

- [ ] **Step 4: Re-run test**

Run: `cd backend && pytest tests/test_v4_cascade_visibility.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_v4_cascade_visibility.py
git commit -m "test(v4): cross-user cascade ownership integration — broken_refs annotation"
```

---

### Task 14: Smoke baseline pytest

Confirm no existing test broken by the new managers / endpoints.

**Files:**
- (None — verification only)

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && pytest tests/ --tb=short -q 2>&1 | tail -20`

- [ ] **Step 2: Compare pass count vs pre-P1 baseline**

Pre-P1 baseline (current `dev` branch): ~780 pass + small handful of pre-existing failures (1 v3.3 macOS tmpdir baseline + Playwright E2E tests that need browser). Post-P1: should be ~780 + ~50 new (P1 tests) = ~830 pass, same pre-existing failures, **no new failures**.

If you see new failures, audit:
1. Did `app.py` boot order break anything? (`set_v4_managers` must be called after managers exist; managers must be imported)
2. Did decorator import break existing routes? (Check `auth/decorators.py` exports still include `login_required` / `require_file_owner` / `admin_required`)

- [ ] **Step 3: Commit baseline confirmation (no file change — just a marker commit)**

```bash
# nothing to add unless you found and fixed an issue
# if all green, skip this commit — proceed to Task 15
```

---

### Task 15: Update CLAUDE.md REST endpoints table

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Locate the REST endpoints table in CLAUDE.md**

Search for the line: `### Backend (`app.py`)` → scroll down to `**REST endpoints**` table.

- [ ] **Step 2: Add 15 new endpoint rows at the bottom of the table**

```markdown
| GET | `/api/asr_profiles` | List ASR profiles visible to user (v4.0 P1) |
| POST | `/api/asr_profiles` | Create ASR profile |
| GET | `/api/asr_profiles/<id>` | Get single ASR profile |
| PATCH | `/api/asr_profiles/<id>` | Update ASR profile (owner only) |
| DELETE | `/api/asr_profiles/<id>` | Delete ASR profile (owner only) |
| GET | `/api/mt_profiles` | List MT profiles visible to user (v4.0 P1) |
| POST | `/api/mt_profiles` | Create MT profile |
| GET | `/api/mt_profiles/<id>` | Get single MT profile |
| PATCH | `/api/mt_profiles/<id>` | Update MT profile (owner only) |
| DELETE | `/api/mt_profiles/<id>` | Delete MT profile (owner only) |
| GET | `/api/pipelines` | List pipelines, includes `broken_refs` annotation (v4.0 P1) |
| POST | `/api/pipelines` | Create pipeline (cascade ref check vs ASR/MT/Glossary) |
| GET | `/api/pipelines/<id>` | Get single pipeline + broken_refs |
| PATCH | `/api/pipelines/<id>` | Update pipeline (owner only, re-validates cascade refs) |
| DELETE | `/api/pipelines/<id>` | Delete pipeline (owner only) |
```

- [ ] **Step 3: Add a "v4.0 Phase 1 — Entity Foundation" entry under Completed Features**

Insert immediately before the v3.18 entry:
```markdown
### v4.0 Phase 1 — Entity Foundation (in progress on `chore/asr-mt-rearchitecture-research`)
- 3 new manager modules (`backend/asr_profiles.py` / `backend/mt_profiles.py` / `backend/pipelines.py`), mirror v3.13 `ProfileManager` Phase 5 T2.8 TOCTOU lock pattern + per-resource ownership
- 15 new REST endpoints (5 per entity × 3 entities, all gated by `@login_required` + per-entity `@require_*_owner` decorator)
- Pipeline validator does **cascade ref check** at create/update — references unknown ASR/MT profile or glossary → 400 with explicit error
- Pipeline GET response includes **`broken_refs` annotation** listing sub-resources the requesting user can't view (per design doc §7)
- ~50 new backend tests (validator + manager + endpoint + cross-user cascade)
- **Out of P1 scope**: stage executor, pipeline_runner, migration script, frontend changes — see [docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md](docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md) for full v4.0 plan
- Legacy `/api/profiles` (bundled ASR + MT) **unchanged** in P1 — keeps running until P3 migration
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(v4 P1): add 15 new REST endpoints + Completed Features entry"
```

---

### Task 16: Update design doc Phase status

**Files:**
- Modify: `docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md`

- [ ] **Step 1: Update Section 13 Approval Status**

Find `## 13. Approval Status` and update checkboxes:
```markdown
## 13. Approval Status

- [x] §1-12 vision lock, 6 个 design choice + 4 个 dimension 確認
- [x] User review 過設計 doc
- [x] **P1 implementation plan written** ([2026-05-16-v4-phase1-entity-foundation-plan.md](../plans/2026-05-16-v4-phase1-entity-foundation-plan.md))
- [ ] P1 implementation execution
- [ ] P2-P7 plans pending P1 ship
- [ ] (deferred) Each phase 落 implementation 前再 update vision-level doc
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md
git commit -m "docs(v4): update design doc approval status — P1 plan written"
```

---

### Task 17: Curl smoke verification (manual, optional)

**Files:**
- (None — manual verification)

- [ ] **Step 1: Start backend**

```bash
cd backend && python app.py
```

(Or via `./start.sh` from repo root.)

- [ ] **Step 2: In another terminal, run curl flow**

```bash
# Login first (use admin/AdminPass1! or any seeded user)
COOKIE_JAR=$(mktemp)
curl -s -c $COOKIE_JAR -X POST http://localhost:5001/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"AdminPass1!"}'

# Create ASR profile
ASR_ID=$(curl -s -b $COOKIE_JAR -X POST http://localhost:5001/api/asr_profiles \
  -H "Content-Type: application/json" \
  -d '{"name":"yue-emergent","engine":"mlx-whisper","model_size":"large-v3","mode":"emergent-translate","language":"zh"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "ASR: $ASR_ID"

# Create MT profile
MT_ID=$(curl -s -b $COOKIE_JAR -X POST http://localhost:5001/api/mt_profiles \
  -H "Content-Type: application/json" \
  -d '{"name":"yue-polish","engine":"qwen3.5-35b-a3b","input_lang":"zh","output_lang":"zh","system_prompt":"你係粵語廣播編輯員。","user_message_template":"請將以下文字轉粵語廣播風格：\n{text}"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "MT: $MT_ID"

# Create Pipeline
PIPE_ID=$(curl -s -b $COOKIE_JAR -X POST http://localhost:5001/api/pipelines \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"test-broadcast\",\"asr_profile_id\":\"$ASR_ID\",\"mt_stages\":[\"$MT_ID\"],\"glossary_stage\":{\"enabled\":false,\"glossary_ids\":[],\"apply_order\":\"explicit\",\"apply_method\":\"string-match-then-llm\"},\"font_config\":{\"family\":\"Noto Sans TC\",\"size\":35,\"color\":\"#ffffff\",\"outline_color\":\"#000000\",\"outline_width\":2,\"margin_bottom\":40,\"subtitle_source\":\"auto\",\"bilingual_order\":\"target_top\"}}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "Pipeline: $PIPE_ID"

# List
curl -s -b $COOKIE_JAR http://localhost:5001/api/pipelines | python3 -m json.tool

# Cleanup
curl -s -b $COOKIE_JAR -X DELETE http://localhost:5001/api/pipelines/$PIPE_ID
curl -s -b $COOKIE_JAR -X DELETE http://localhost:5001/api/mt_profiles/$MT_ID
curl -s -b $COOKIE_JAR -X DELETE http://localhost:5001/api/asr_profiles/$ASR_ID

rm $COOKIE_JAR
```

- [ ] **Step 3: Confirm all calls return expected status codes**

| Call | Expected status |
|---|---|
| Login | 200 |
| Create ASR | 201 |
| Create MT | 201 |
| Create Pipeline | 201 |
| List Pipelines | 200 (includes 1 entry + `broken_refs: {}`) |
| Delete Pipeline | 204 |
| Delete MT | 204 |
| Delete ASR | 204 |

- [ ] **Step 4: No commit needed (manual verification only)**

---

### Task 18: Final P1 milestone check

**Files:**
- (None — checklist)

- [ ] **Step 1: Confirm all P1 acceptance criteria**

| Criterion | Met? |
|---|---|
| 3 new manager modules created with full CRUD | check |
| Per-resource ownership (admin / owner / shared) on all 3 | check |
| Cascade ref validation on Pipeline create + update | check |
| `broken_refs` annotation on Pipeline GET | check |
| 5 REST endpoints per entity × 3 = 15 routes registered | check |
| New tests pass (~50 new) | check |
| **No existing test regression** | check |
| Legacy `/api/profiles` bundle unchanged | check |
| Legacy file registry shape unchanged | check |
| CLAUDE.md REST table + Completed Features updated | check |
| Design doc approval status updated | check |

- [ ] **Step 2: Final commit (if anything stuck during checkpoint review)**

If any unfixed issue surfaced during checkpoint review, fix it now + commit. Otherwise no-op.

- [ ] **Step 3: Push branch + report to user**

```bash
git push -u origin chore/asr-mt-rearchitecture-research
```

Tell user: "P1 entity foundation complete. ~50 new backend tests pass. Ready for review + decide on P2 (stage executor + Whisper 3-mode + pipeline_runner)."

---

### Task 19: Manage P1 todo list cleanup

**Files:**
- (None — TodoWrite state)

- [ ] **Step 1: Mark P1 todo complete**

Use TodoWrite to mark "Brainstorm ASR+MT rearchitecture direction" + "User reviews design doc" as completed, and add new in_progress item "P1 entity foundation merged — decide on P2 scope".

This is a process step, not a code change. No commit.

---

## Self-Review

After completing all 19 tasks, audit the plan against the design doc:

### Spec coverage check

| Design doc § | Implemented by | Notes |
|---|---|---|
| §3.1 ASR Profile schema | T2, T3 | All fields covered |
| §3.1.2 三 mode picker | T2 (validator) | translate-to-en forces language=en check |
| §3.1.3 警告 UI | **Deferred to P4 (frontend)** | Schema captures `mode`; UI banner is frontend work |
| §3.2 MT Profile schema | T4 | qwen-locked, same-lang enforce, {text} required |
| §3.3 Glossary Stage | T5, T7 (can_view) | Stage config validated; runtime executor → P2 |
| §3.4 Pipeline schema | T5, T6 | Cascade ref check + broken_refs annotation |
| §6.1 New backend modules | T2 (asr_profiles.py), T4 (mt_profiles.py), T5+T6 (pipelines.py) | 3 new manager files |
| §6.4 New REST endpoints | T10, T11, T12 | 15 of design doc's 24 endpoints covered (others → P2+) |
| §7 Ownership model | T2-T6 + T7 + T8 | Cascade visibility via `broken_refs` |
| §8 Migration plan | **Deferred to P3** | Legacy profiles unchanged in P1 |
| §6.5 字幕設定 generalize | T5 (`subtitle_source` enum) | `auto/source/target/bilingual` lock validated |
| §6.6 Segment schema rename | **Deferred to P3** | File registry untouched |
| §9 CLAUDE.md changes | T15 | REST table + Completed Features (full rewrite → P6) |

### Placeholder scan: pass

- No "TBD" / "TODO" / "implement later" in plan
- Every code step has actual code (no `...` ellipsis)
- All test bodies are complete

### Type consistency check: pass

- `ASRProfileManager` / `MTProfileManager` / `PipelineManager` named consistently across all tasks
- Method names consistent: `list_all` / `list_visible` / `get` / `create` / `update_if_owned` / `delete_if_owned` / `can_view` / `can_edit` / `annotate_broken_refs`
- URL parameter naming consistent: `profile_id` (ASR / MT) + `pipeline_id`
- Decorator naming consistent: `require_asr_profile_owner` / `require_mt_profile_owner` / `require_pipeline_owner`
- Lock helper naming consistent: `_get_asr_lock` / `_get_mt_lock` / `_get_pipe_lock` (each module)
- Master lock naming consistent: `_ASR_MASTER_LOCK` / `_MT_MASTER_LOCK` / `_PIPE_MASTER_LOCK`

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-16-v4-phase1-entity-foundation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for keeping main context clean across 19 tasks.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Faster if you want to be more hands-on but consumes main context faster.

**Which approach?**
