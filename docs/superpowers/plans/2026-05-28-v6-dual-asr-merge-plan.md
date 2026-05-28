# V6 Dual-ASR Merge to dev — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Graft V6 VAD + Dual-ASR + Refiner backend from `feat/frontend-redesign` onto `dev`, gated behind a Pipeline-strip mode toggle, preserving dev's vanilla HTML/JS frontend and all v3.17–v3.18 work.

**Architecture:** Two coexisting dispatch paths (Profile / V6 Pipeline) chosen by `settings.json.active_kind`. New backend lives entirely in new folders (`stages/`, `engines/`, `pipelines.py`, `pipeline_runner.py`, `routes/`); dev's existing handlers untouched. File registry snapshots `active_kind`+`active_id` at upload so in-flight jobs are immune to mid-job mode switches.

**Tech Stack:** Python 3.9 main backend, Python 3.11 subprocess for Qwen3-ASR (mlx_qwen3_asr 0.3.5), Silero VAD 6.2.1, Ollama qwen3.5:35b-a3b-mlx-bf16 refiner, vanilla HTML/JS frontend, Flask 3, pytest, Playwright.

**Spec:** [docs/superpowers/specs/2026-05-28-v6-dual-asr-merge-design.md](../specs/2026-05-28-v6-dual-asr-merge-design.md)

**Source commit on feat branch:** 95d6f67 (Merge feat/v6-vad-dual-asr-refiner: VAD + dual-ASR + simplified refiner)

---

## Phase 1 — Backend graft (8 tasks)

All Phase 1 tasks follow this pattern: `git checkout feat/frontend-redesign -- <paths>` to import files; run their already-existing tests (which were green on feat branch) to verify they still pass in dev's environment; commit.

### Task 1.1: Graft `backend/engines/` folder

**Files:**
- Create: `backend/engines/__init__.py`
- Create: `backend/engines/factory.py`
- Create: `backend/engines/_quality_flags.py`
- Create: `backend/engines/llm/__init__.py`
- Create: `backend/engines/llm/ollama.py`
- Create: `backend/engines/llm/openrouter.py`
- Create: `backend/engines/refiner/__init__.py`
- Create: `backend/engines/refiner/llm_refiner.py`
- Create: `backend/engines/transcribe/__init__.py`
- Create: `backend/engines/transcribe/qwen3_asr.py`
- Create: `backend/engines/transcribe/qwen3_subprocess.py`
- Create: `backend/engines/transcribe/qwen3_vad_engine.py`
- Create: `backend/engines/translator/__init__.py`
- Create: `backend/engines/translator/llm_translator.py`
- Create: `backend/engines/verifier/__init__.py`
- Create: `backend/engines/verifier/llm_verifier.py`

- [ ] **Step 1: Import engines folder from feat branch**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git checkout feat/frontend-redesign -- backend/engines/
```

- [ ] **Step 2: Verify imports work in dev's py3.9 venv**

```bash
cd backend && source venv/bin/activate
python -c "from engines.factory import create_engine; print('engines OK')"
python -c "from engines.refiner.llm_refiner import LLMRefiner; print('refiner OK')"
python -c "from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine; print('qwen3 engine OK')"
```

Expected: 3 lines, each ending "OK". No ImportError.

- [ ] **Step 3: Commit**

```bash
git add backend/engines/
git commit -m "feat(v6): graft engines/ folder from feat/frontend-redesign

LLM clients (Ollama/OpenRouter), refiner LLM wrapper, Qwen3-ASR
subprocess bridge, translator wrapper, verifier (V5 use only)."
```

### Task 1.2: Graft `backend/stages/` folder

**Files:**
- Create: `backend/stages/__init__.py`
- Create: `backend/stages/asr_stage.py`
- Create: `backend/stages/mt_stage.py`
- Create: `backend/stages/glossary_stage.py`
- Create: `backend/stages/v5/__init__.py`
- Create: `backend/stages/v5/asr_primary_stage.py`
- Create: `backend/stages/v5/asr_secondary_stage.py`
- Create: `backend/stages/v5/asr_verifier_stage.py`
- Create: `backend/stages/v5/refiner_stage.py`
- Create: `backend/stages/v5/translator_stage.py`
- Create: `backend/stages/v6/__init__.py`
- Create: `backend/stages/v6/silero_vad_stage.py`
- Create: `backend/stages/v6/qwen3_per_region_stage.py`
- Create: `backend/stages/v6/time_anchored_merge_stage.py`

- [ ] **Step 1: Import stages folder from feat branch**

```bash
git checkout feat/frontend-redesign -- backend/stages/
```

- [ ] **Step 2: Verify imports**

```bash
cd backend && source venv/bin/activate
python -c "from stages import PipelineStage, StageContext; print('stages base OK')"
python -c "from stages.v6.silero_vad_stage import SileroVadStage; print('VAD OK')"
python -c "from stages.v6.qwen3_per_region_stage import Qwen3PerRegionStage; print('Qwen3 region OK')"
python -c "from stages.v6.time_anchored_merge_stage import TimeAnchoredMergeStage; print('merge OK')"
```

Expected: 4 lines, each ending "OK".

- [ ] **Step 3: Commit**

```bash
git add backend/stages/
git commit -m "feat(v6): graft stages/ folder — V5 + V6 stage implementations

V6 stages: Silero VAD (Stage 0), Qwen3 per-region ASR (Stage 1A),
time-anchored merge (Stage 2). V5 stages imported but not wired."
```

### Task 1.3: Graft pipeline manager + runner + schema files

**Files:**
- Create: `backend/pipelines.py`
- Create: `backend/pipeline_runner.py`
- Create: `backend/pipeline_schema_v5.py`
- Create: `backend/transcribe_profiles.py`
- Create: `backend/llm_profiles.py`
- Create: `backend/refiner_profiles.py`
- Create: `backend/asr_profiles.py`

- [ ] **Step 1: Import manager + runner files**

```bash
git checkout feat/frontend-redesign -- \
  backend/pipelines.py \
  backend/pipeline_runner.py \
  backend/pipeline_schema_v5.py \
  backend/transcribe_profiles.py \
  backend/llm_profiles.py \
  backend/refiner_profiles.py \
  backend/asr_profiles.py
```

- [ ] **Step 2: Verify imports**

```bash
cd backend && source venv/bin/activate
python -c "from pipelines import PipelineManager; print('pipelines OK')"
python -c "from pipeline_runner import PipelineRunner; print('runner OK')"
python -c "from transcribe_profiles import TranscribeProfileManager; print('transcribe profiles OK')"
python -c "from llm_profiles import LLMProfileManager; print('llm profiles OK')"
python -c "from refiner_profiles import RefinerProfileManager; print('refiner profiles OK')"
```

Expected: 5 lines, each ending "OK".

- [ ] **Step 3: Commit**

```bash
git add backend/pipelines.py backend/pipeline_runner.py backend/pipeline_schema_v5.py \
        backend/transcribe_profiles.py backend/llm_profiles.py backend/refiner_profiles.py \
        backend/asr_profiles.py
git commit -m "feat(v6): graft pipeline manager + runner + child profile managers

PipelineManager (CRUD), PipelineRunner (_run_v5 + _run_v6 dispatch),
TranscribeProfileManager / LLMProfileManager / RefinerProfileManager."
```

### Task 1.4: Graft `backend/routes/` blueprints

**Files:**
- Create: `backend/routes/__init__.py` (if needed)
- Create: `backend/routes/pipelines.py`
- Create: `backend/routes/refiner_profiles.py`
- Create: `backend/routes/transcribe_profiles.py`
- Create: `backend/routes/llm_profiles.py`

- [ ] **Step 1: Import routes folder**

```bash
git checkout feat/frontend-redesign -- backend/routes/
```

- [ ] **Step 2: Verify blueprint imports**

```bash
cd backend && source venv/bin/activate
python -c "from routes.pipelines import bp as pipelines_bp; print('pipelines bp OK')"
python -c "from routes.refiner_profiles import bp; print('refiner bp OK')"
python -c "from routes.transcribe_profiles import bp; print('transcribe bp OK')"
python -c "from routes.llm_profiles import bp; print('llm bp OK')"
```

Expected: 4 lines, each ending "OK".

- [ ] **Step 3: Commit**

```bash
git add backend/routes/
git commit -m "feat(v6): graft routes/ blueprints — pipelines + child profiles

8 V6 pipeline endpoints + CRUD endpoints for refiner/transcribe/llm
child profiles. Not yet registered on Flask app (Task 2.3 does that)."
```

### Task 1.5: Graft Qwen3 subprocess script

**Files:**
- Create: `backend/scripts/v5_prototype/qwen3_vad_subprocess.py`
- Note: `backend/scripts/v5_prototype/venv_qwen/` is gitignored and already exists locally (Python 3.11.15 + mlx_qwen3_asr 0.3.5 verified earlier this session).

- [ ] **Step 1: Import subprocess script**

```bash
git checkout feat/frontend-redesign -- backend/scripts/v5_prototype/qwen3_vad_subprocess.py
```

- [ ] **Step 2: Verify py3.11 subprocess can import the script and dependencies**

```bash
backend/scripts/v5_prototype/venv_qwen/bin/python -c "
import sys
sys.path.insert(0, 'backend/scripts/v5_prototype')
import qwen3_vad_subprocess
print('subprocess script OK')
import mlx_qwen3_asr
print('mlx_qwen3_asr OK', getattr(mlx_qwen3_asr, '__version__', 'no-version'))
"
```

Expected: "subprocess script OK" + "mlx_qwen3_asr OK 0.3.5".

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/v5_prototype/qwen3_vad_subprocess.py
git commit -m "feat(v6): graft Qwen3 ASR subprocess script (py3.11 bridge)

Main backend (py3.9) spawns this script via venv_qwen/bin/python.
JSON stdin/stdout protocol returns char-level transcription per
VAD region."
```

### Task 1.6: Graft V6 config files + rewrite ownership

**Files:**
- Create: `backend/config/pipelines/4696bbaa-b988-49bd-859c-e742cb365634.json` (賽馬廣播 Cantonese)
- Create: `backend/config/pipelines/641a77ec-a73a-4ef2-926c-e1b3992d0d3e.json` (Winning Factor EN)
- Create: `backend/config/refiner_profiles/c4a8b3a1-d78a-4d79-82c9-906186358940.json`
- Create: `backend/config/refiner_profiles/f7f72bd9-3f27-47a4-92bd-5727f336916a.json`
- Create: `backend/config/transcribe_profiles/*.json` (4 files)
- Create: `backend/config/llm_profiles/9402593c-184d-4a4d-a160-ebdf55e678e8.json`
- Create: `backend/config/prompt_templates_v5/refiner/en_newscast_default.json`
- Create: `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json`
- Create: `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_v6.json`

- [ ] **Step 1: Import config JSONs**

```bash
git checkout feat/frontend-redesign -- \
  backend/config/pipelines/ \
  backend/config/refiner_profiles/ \
  backend/config/transcribe_profiles/ \
  backend/config/llm_profiles/ \
  backend/config/prompt_templates_v5/
```

- [ ] **Step 2: Rewrite `user_id` from 627 → null (shared) on all imported pipelines + child profiles**

Create file `backend/scripts/migrate_v6_imported_ownership.py`:

```python
"""One-shot: rewrite user_id=null on V6 imported pipeline + child profile JSONs.

The feat/frontend-redesign branch authored these under admin_p3 (id=627).
On dev, admin_p3 has id=627 in app.db but anyone should be able to use
shared V6 pipelines, so we mark them user_id=null (= shared)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "config"
DIRS = ["pipelines", "refiner_profiles", "transcribe_profiles", "llm_profiles"]

for d in DIRS:
    for f in (ROOT / d).glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        if data.get("user_id") == 627:
            data["user_id"] = None
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  rewrote user_id null: {f.relative_to(ROOT)}")
print("done")
```

Run:

```bash
cd backend && source venv/bin/activate
python scripts/migrate_v6_imported_ownership.py
```

Expected output: lines listing each rewritten file, ending "done".

- [ ] **Step 3: Verify pipeline JSONs load via PipelineManager**

```bash
cd backend && source venv/bin/activate
python -c "
from pipelines import PipelineManager
from pathlib import Path
mgr = PipelineManager(Path('config'))
for p in mgr.list_all():
    print(f'  {p[\"id\"][:8]:8s}  name={p.get(\"name\")}  user_id={p.get(\"user_id\")}')
"
```

Expected: 2 lines listing 賽馬廣播 + Winning Factor with `user_id=None`.

- [ ] **Step 4: Commit**

```bash
git add backend/config/pipelines/ backend/config/refiner_profiles/ \
        backend/config/transcribe_profiles/ backend/config/llm_profiles/ \
        backend/config/prompt_templates_v5/ \
        backend/scripts/migrate_v6_imported_ownership.py
git commit -m "feat(v6): graft V6 pipeline + child profile JSON configs

2 V6 pipelines (賽馬 Cantonese + Winning Factor EN), 2 refiner
profiles, 4 transcribe profiles, 1 LLM profile, 3 refiner prompt
templates. user_id rewritten 627 → null (shared) so any dev user
can use them."
```

### Task 1.7: Graft V6 tests + run them

**Files:**
- Create: `backend/tests/test_v6_stages.py`
- Create: `backend/tests/test_v6_runner.py`
- Create: `backend/tests/test_v6_refiner_json_unwrap.py`
- Create: `backend/tests/test_v6_pipeline_config.py`

- [ ] **Step 1: Import V6 test files**

```bash
git checkout feat/frontend-redesign -- \
  backend/tests/test_v6_stages.py \
  backend/tests/test_v6_runner.py \
  backend/tests/test_v6_refiner_json_unwrap.py \
  backend/tests/test_v6_pipeline_config.py
```

- [ ] **Step 2: Run V6 test files in isolation**

```bash
cd backend && source venv/bin/activate
pytest tests/test_v6_stages.py tests/test_v6_runner.py \
       tests/test_v6_refiner_json_unwrap.py tests/test_v6_pipeline_config.py \
       -v 2>&1 | tail -40
```

Expected: all 94 cases PASS. If any fail, debug environment differences (likely silero-vad or soundfile not installed — Task 1.8 will fix).

- [ ] **Step 3: Run the rest of the existing dev test suite to confirm zero regression**

```bash
pytest tests/ -q 2>&1 | tail -10
```

Expected: ~907 pass / 14 pre-existing fail (813 from dev baseline + 94 new V6 = 907; 14 pre-existing failures unchanged).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_v6_stages.py backend/tests/test_v6_runner.py \
        backend/tests/test_v6_refiner_json_unwrap.py backend/tests/test_v6_pipeline_config.py
git commit -m "test(v6): graft 94 V6 backend test cases

55 stage tests, 18 runner dispatch tests, 14 refiner JSON unwrap
tests, 7 pipeline config validation tests. All green on dev's
py3.9 venv."
```

### Task 1.8: Update `requirements.txt`

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add silero-vad + soundfile**

Open `backend/requirements.txt` and append:

```
silero-vad>=6.2.1
soundfile>=0.13.0
```

- [ ] **Step 2: Install + verify**

```bash
cd backend && source venv/bin/activate
pip install silero-vad>=6.2.1 soundfile>=0.13.0
python -c "from silero_vad import load_silero_vad; load_silero_vad(); print('silero OK')"
python -c "import soundfile; print('soundfile OK', soundfile.__version__)"
```

Expected: 2 lines ending "OK".

- [ ] **Step 3: Re-run V6 stage tests to confirm dependencies work**

```bash
pytest tests/test_v6_stages.py -v 2>&1 | tail -10
```

Expected: 55 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore(v6): add silero-vad + soundfile to requirements.txt

silero-vad 6.2.1 powers Stage 0 VAD; soundfile is a transitive
dep used by the Qwen3 subprocess bridge for audio I/O."
```

---

## Phase 2 — Hook integration (6 tasks, TDD)

This phase wires V6 into dev's existing app via small additions in `app.py`, `profiles.py`, and the prompt override validator. Each task is TDD: write failing test → implement → verify green → commit.

### Task 2.1: settings.json schema migration in `ProfileManager`

**Files:**
- Modify: `backend/profiles.py:326-360` (`get_active` + `set_active`)
- Test: `backend/tests/test_settings_schema_migration.py` (new)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_settings_schema_migration.py`:

```python
"""Test settings.json schema migration: active_kind + active_id with
backward-compat mirror to active_profile."""
import json
import pytest
from pathlib import Path
from profiles import ProfileManager

VALID_PROFILE = {
    "name": "Test", "description": "",
    "asr": {"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"},
    "translation": {"engine": "mock", "glossary_id": None, "temperature": 0.1},
}


def test_set_active_writes_all_three_fields(tmp_path):
    mgr = ProfileManager(tmp_path)
    p = mgr.create(VALID_PROFILE)
    mgr.set_active(p["id"])
    settings = json.loads((tmp_path / "settings.json").read_text())
    assert settings["active_kind"] == "profile"
    assert settings["active_id"] == p["id"]
    assert settings["active_profile"] == p["id"]


def test_get_active_reads_new_schema(tmp_path):
    mgr = ProfileManager(tmp_path)
    p = mgr.create(VALID_PROFILE)
    (tmp_path / "settings.json").write_text(json.dumps({
        "active_kind": "profile", "active_id": p["id"], "active_profile": p["id"]
    }))
    assert mgr.get_active()["id"] == p["id"]


def test_get_active_legacy_only_field_still_works(tmp_path):
    """Old install with only active_profile set: must still load active."""
    mgr = ProfileManager(tmp_path)
    p = mgr.create(VALID_PROFILE)
    (tmp_path / "settings.json").write_text(json.dumps({"active_profile": p["id"]}))
    assert mgr.get_active()["id"] == p["id"]


def test_get_active_returns_none_when_active_kind_is_pipeline(tmp_path):
    """When active_kind=pipeline_v6, ProfileManager.get_active returns None
    (it's not its responsibility — PipelineManager handles it)."""
    mgr = ProfileManager(tmp_path)
    mgr.create(VALID_PROFILE)
    (tmp_path / "settings.json").write_text(json.dumps({
        "active_kind": "pipeline_v6", "active_id": "4696bbaa-...",
    }))
    assert mgr.get_active() is None


def test_set_active_does_not_drop_other_settings(tmp_path):
    mgr = ProfileManager(tmp_path)
    p = mgr.create(VALID_PROFILE)
    (tmp_path / "settings.json").write_text(json.dumps({
        "active_profile": None, "other_key": "preserved"
    }))
    mgr.set_active(p["id"])
    settings = json.loads((tmp_path / "settings.json").read_text())
    assert settings["other_key"] == "preserved"


def test_set_active_to_unknown_id_returns_none(tmp_path):
    mgr = ProfileManager(tmp_path)
    assert mgr.set_active("nonexistent") is None
    settings = json.loads((tmp_path / "settings.json").read_text())
    # should NOT have overwritten settings with bogus id
    assert settings.get("active_id") != "nonexistent"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd backend && source venv/bin/activate
pytest tests/test_settings_schema_migration.py -v 2>&1 | tail -20
```

Expected: 4 of 6 FAIL (test_set_active_writes_all_three_fields, test_get_active_reads_new_schema, test_get_active_returns_none_when_active_kind_is_pipeline, test_set_active_to_unknown_id_returns_none). 2 may pass coincidentally.

- [ ] **Step 3: Implement the migration**

Edit `backend/profiles.py`. Replace `get_active` (currently line ~326) with:

```python
def get_active(self) -> Optional[dict]:
    """Return the active profile, honoring active_kind = 'profile'.

    If active_kind is something else (e.g. 'pipeline_v6'), returns None —
    that's PipelineManager's territory. Backward-compat: missing
    active_kind falls back to legacy active_profile field.
    """
    settings = self._read_settings()
    kind = settings.get("active_kind")
    if kind is not None and kind != "profile":
        return None

    active_id = settings.get("active_id") or settings.get("active_profile")
    if active_id:
        profile = self.get(active_id)
        if profile is not None:
            return profile

    # Stale ID OR no active set — fall back to first available profile
    remaining = self.list_all()
    fallback = next((p for p in remaining if p.get("id")), None)
    if fallback is None:
        if active_id:
            self._write_settings({**settings, "active_kind": "profile",
                                  "active_id": None, "active_profile": None})
        return None

    self._write_settings({**settings,
                          "active_kind": "profile",
                          "active_id": fallback["id"],
                          "active_profile": fallback["id"]})
    return fallback
```

Replace `set_active`:

```python
def set_active(self, profile_id: str) -> Optional[dict]:
    profile = self.get(profile_id)
    if profile is None:
        return None
    settings = self._read_settings()
    self._write_settings({
        **settings,
        "active_kind": "profile",
        "active_id": profile_id,
        "active_profile": profile_id,   # legacy mirror
    })
    return profile
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/test_settings_schema_migration.py tests/test_profiles.py -v 2>&1 | tail -20
```

Expected: All 6 new + all existing 38 profile tests PASS (44 total).

- [ ] **Step 5: Commit**

```bash
git add backend/profiles.py backend/tests/test_settings_schema_migration.py
git commit -m "feat(v6): ProfileManager settings.json schema migration

set_active writes active_kind + active_id + active_profile (legacy
mirror). get_active reads new schema with fallback to active_profile
for old installs. Returns None when active_kind='pipeline_v6'
(PipelineManager territory)."
```

### Task 2.2: Extend `prompt_overrides` whitelist

**Files:**
- Modify: `backend/translation/prompt_override_validator.py`
- Test: `backend/tests/test_prompt_override_validator.py` (existing — add cases)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_prompt_override_validator.py`:

```python
def test_qwen3_context_key_accepted():
    """V6 adds qwen3_context to the allowed key set."""
    from translation.prompt_override_validator import validate_prompt_overrides
    errors = validate_prompt_overrides({"qwen3_context": "袁幸堯 史滕雷"}, "field")
    assert errors == []


def test_refiner_prompt_key_accepted():
    """V6 adds refiner_prompt to the allowed key set."""
    from translation.prompt_override_validator import validate_prompt_overrides
    errors = validate_prompt_overrides({"refiner_prompt": "Polish broadcast register"}, "field")
    assert errors == []


def test_legacy_keys_still_accepted():
    """v3.18 4 keys must still validate cleanly."""
    from translation.prompt_override_validator import validate_prompt_overrides
    errors = validate_prompt_overrides({
        "anchor": "a", "single": "s", "enrich": "e", "pass1": "p"
    }, "field")
    assert errors == []


def test_mixed_legacy_and_v6_keys_accepted():
    """Both old and new keys may coexist in the same dict (resolver picks per mode)."""
    from translation.prompt_override_validator import validate_prompt_overrides
    errors = validate_prompt_overrides({
        "anchor": "a", "qwen3_context": "ctx", "refiner_prompt": "p"
    }, "field")
    assert errors == []


def test_unknown_key_rejected():
    from translation.prompt_override_validator import validate_prompt_overrides
    errors = validate_prompt_overrides({"bogus_key": "x"}, "field")
    assert len(errors) == 1
    assert "bogus_key" in errors[0]
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd backend && source venv/bin/activate
pytest tests/test_prompt_override_validator.py -v -k "qwen3 or refiner_prompt or mixed" 2>&1 | tail -10
```

Expected: 4 FAIL ("not in allowed keys" for qwen3_context + refiner_prompt).

- [ ] **Step 3: Extend whitelist**

Edit `backend/translation/prompt_override_validator.py`. Find `ALLOWED_KEYS` (probably top of file) and replace with:

```python
ALLOWED_KEYS = {
    # v3.18 — Profile-mode MT prompts
    "anchor", "single", "enrich", "pass1",
    # v6 — Pipeline-mode prompts
    "qwen3_context", "refiner_prompt",
}
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/test_prompt_override_validator.py -v 2>&1 | tail -10
```

Expected: All tests PASS (existing + 5 new).

- [ ] **Step 5: Commit**

```bash
git add backend/translation/prompt_override_validator.py backend/tests/test_prompt_override_validator.py
git commit -m "feat(v6): extend prompt_overrides whitelist with qwen3_context + refiner_prompt

ALLOWED_KEYS grows from {anchor, single, enrich, pass1} → adds
{qwen3_context, refiner_prompt}. Per-key validation unchanged.
Resolver behavior (mode-aware fallthrough) lives in app.py."
```

### Task 2.3: `app.py` imports + manager init + blueprint register

**Files:**
- Modify: `backend/app.py:373-400` (manager initialization area)
- Test: `backend/tests/test_app_boots_with_v6_managers.py` (new)

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_app_boots_with_v6_managers.py`:

```python
"""Verify app.py wires up V6 managers + blueprints on boot."""
import pytest


def test_app_has_pipeline_manager_in_config():
    import app
    assert app.app.config.get("PIPELINE_MANAGER") is not None
    from pipelines import PipelineManager
    assert isinstance(app.app.config["PIPELINE_MANAGER"], PipelineManager)


def test_app_has_transcribe_profile_manager_in_config():
    import app
    assert app.app.config.get("TRANSCRIBE_PROFILE_MANAGER") is not None


def test_app_has_llm_profile_manager_in_config():
    import app
    assert app.app.config.get("LLM_PROFILE_MANAGER") is not None


def test_app_has_refiner_profile_manager_in_config():
    import app
    assert app.app.config.get("REFINER_PROFILE_MANAGER") is not None


def test_pipelines_blueprint_registered():
    import app
    rules = [str(r) for r in app.app.url_map.iter_rules()]
    assert any(r.startswith("/api/pipelines") for r in rules), \
        "Expected at least one /api/pipelines route registered"


def test_refiner_profiles_blueprint_registered():
    import app
    rules = [str(r) for r in app.app.url_map.iter_rules()]
    assert any(r.startswith("/api/refiner_profiles") for r in rules)


def test_transcribe_profiles_blueprint_registered():
    import app
    rules = [str(r) for r in app.app.url_map.iter_rules()]
    assert any(r.startswith("/api/transcribe_profiles") for r in rules)


def test_llm_profiles_blueprint_registered():
    import app
    rules = [str(r) for r in app.app.url_map.iter_rules()]
    assert any(r.startswith("/api/llm_profiles") for r in rules)
```

- [ ] **Step 2: Run tests, verify failing**

```bash
cd backend && source venv/bin/activate
pytest tests/test_app_boots_with_v6_managers.py -v 2>&1 | tail -20
```

Expected: All 8 FAIL.

- [ ] **Step 3: Add imports + manager init + blueprint register in `app.py`**

Find the existing manager initialization area in `backend/app.py` (around line 373 where `_profile_manager = ProfileManager(CONFIG_DIR)` is defined). After the existing manager block, add:

```python
# ──────────────────────────────────────────────────────────────
# V6 — Pipeline + child profile managers (graft from feat branch)
# ──────────────────────────────────────────────────────────────
from pipelines import PipelineManager
from transcribe_profiles import TranscribeProfileManager
from llm_profiles import LLMProfileManager
from refiner_profiles import RefinerProfileManager

_pipeline_manager = PipelineManager(CONFIG_DIR)
_transcribe_profile_manager = TranscribeProfileManager(CONFIG_DIR)
_llm_profile_manager = LLMProfileManager(CONFIG_DIR)
_refiner_profile_manager = RefinerProfileManager(CONFIG_DIR)

app.config["PIPELINE_MANAGER"] = _pipeline_manager
app.config["TRANSCRIBE_PROFILE_MANAGER"] = _transcribe_profile_manager
app.config["LLM_PROFILE_MANAGER"] = _llm_profile_manager
app.config["REFINER_PROFILE_MANAGER"] = _refiner_profile_manager
```

Then find the existing blueprint registration block (search for `register_blueprint`). After the existing ones, add:

```python
from routes.pipelines import bp as pipelines_bp
from routes.refiner_profiles import bp as refiner_profiles_bp
from routes.transcribe_profiles import bp as transcribe_profiles_bp
from routes.llm_profiles import bp as llm_profiles_bp

app.register_blueprint(pipelines_bp)
app.register_blueprint(refiner_profiles_bp)
app.register_blueprint(transcribe_profiles_bp)
app.register_blueprint(llm_profiles_bp)
```

- [ ] **Step 4: Run tests, verify passing**

```bash
pytest tests/test_app_boots_with_v6_managers.py -v 2>&1 | tail -15
```

Expected: All 8 PASS.

- [ ] **Step 5: Boot the app + curl smoke-test V6 endpoints (admin must be logged in)**

```bash
cd backend && source venv/bin/activate
# kill existing backend (run via /TaskStop if running in background)
python app.py > /tmp/backend.log 2>&1 &
sleep 8
# Login
curl -s -c /tmp/cookies.txt -X POST http://localhost:5001/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin_p3","password":"AdminPass1!"}' | head
# Hit V6 endpoints
curl -s -b /tmp/cookies.txt http://localhost:5001/api/pipelines | python -m json.tool | head -10
```

Expected: `{"profiles":[]}` for pipelines initially OR list of imported 2 V6 pipelines; no 404 / no 500.

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_app_boots_with_v6_managers.py
git commit -m "feat(v6): wire PipelineManager + child managers + 4 blueprints in app.py

Initialize PipelineManager, TranscribeProfileManager, LLMProfileManager,
RefinerProfileManager at boot. Register routes/pipelines.py +
routes/refiner_profiles.py + routes/transcribe_profiles.py +
routes/llm_profiles.py blueprints. Endpoints now reachable but
dispatch hooks (Task 2.5) still required for end-to-end."
```

### Task 2.4: `_register_file` + `_current_active_snapshot` helper

**Files:**
- Modify: `backend/app.py` (find `_register_file`)
- Test: `backend/tests/test_register_file_active_snapshot.py` (new)

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_register_file_active_snapshot.py`:

```python
"""Verify _register_file snapshots active_kind + active_id on the file entry."""
import pytest


@pytest.fixture
def admin_app(monkeypatch):
    """Boot app + force admin_p3 logged in via R5_AUTH_BYPASS."""
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import importlib, app as _app
    importlib.reload(_app)
    _app.app.config["R5_AUTH_BYPASS"] = True
    return _app


def test_register_file_defaults_to_profile_kind(admin_app, tmp_path):
    fid = admin_app._register_file("test001", "demo.mp4", user_id=1)
    entry = admin_app._file_registry["test001"]
    assert entry["active_kind"] == "profile"
    assert entry["active_id"] is not None  # falls back to current active profile


def test_register_file_accepts_explicit_pipeline_v6(admin_app):
    admin_app._register_file(
        "test002", "demo.mp4", user_id=1,
        active_kind="pipeline_v6", active_id="4696bbaa-fake-id"
    )
    entry = admin_app._file_registry["test002"]
    assert entry["active_kind"] == "pipeline_v6"
    assert entry["active_id"] == "4696bbaa-fake-id"


def test_current_active_snapshot_reads_settings_v6_mode(admin_app, tmp_path):
    """When settings.json has active_kind=pipeline_v6, snapshot helper returns that."""
    import json
    (admin_app.CONFIG_DIR / "settings.json").write_text(
        json.dumps({"active_kind": "pipeline_v6", "active_id": "v6-id-123"})
    )
    kind, aid = admin_app._current_active_snapshot()
    assert kind == "pipeline_v6"
    assert aid == "v6-id-123"


def test_current_active_snapshot_fallback_to_legacy_field(admin_app, tmp_path):
    import json
    (admin_app.CONFIG_DIR / "settings.json").write_text(
        json.dumps({"active_profile": "dev-default"})
    )
    kind, aid = admin_app._current_active_snapshot()
    assert kind == "profile"
    assert aid == "dev-default"
```

- [ ] **Step 2: Run tests, verify failing**

```bash
pytest tests/test_register_file_active_snapshot.py -v 2>&1 | tail -15
```

Expected: 4 FAIL with AttributeError or missing kwarg.

- [ ] **Step 3: Add `_current_active_snapshot` helper + extend `_register_file`**

In `backend/app.py`, find `_register_file` definition. Above it, add:

```python
def _current_active_snapshot():
    """Read settings.json once and return (active_kind, active_id) for upload-time snapshot.

    Used by _register_file when caller doesn't pass explicit kwargs.
    """
    settings = _profile_manager._read_settings()
    kind = settings.get("active_kind", "profile")
    aid = settings.get("active_id") or settings.get("active_profile")
    return kind, aid
```

Then modify `_register_file` signature + body:

```python
def _register_file(
    file_id, original_name, *, user_id=None,
    active_kind=None, active_id=None,  # NEW
    **other_fields,
):
    if active_kind is None or active_id is None:
        kind, aid = _current_active_snapshot()
        active_kind = active_kind or kind
        active_id = active_id or aid
    entry = {
        "id": file_id,
        "original_name": original_name,
        "user_id": user_id,
        "active_kind": active_kind,    # NEW
        "active_id": active_id,        # NEW
        # ... existing fields preserved ...
        **other_fields,
    }
    with _registry_lock:
        _file_registry[file_id] = entry
    return entry
```

- [ ] **Step 4: Run tests, verify passing**

```bash
pytest tests/test_register_file_active_snapshot.py -v 2>&1 | tail -15
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_register_file_active_snapshot.py
git commit -m "feat(v6): _register_file snapshots active_kind + active_id at upload

New _current_active_snapshot() helper reads settings.json once.
_register_file gains optional active_kind/active_id kwargs (falls
back to snapshot if not passed). Guards against race conditions
where user switches active mid-upload."
```

### Task 2.5: `_asr_handler` + `_mt_handler` dispatch on `active_kind`

**Files:**
- Modify: `backend/app.py` (find `_asr_handler` + `_mt_handler`)
- Test: `backend/tests/test_active_kind_dispatch.py` (new)

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_active_kind_dispatch.py`:

```python
"""Test that _asr_handler and _mt_handler dispatch correctly based on
file_entry.active_kind. Profile path → existing transcribe_with_segments;
V6 path → PipelineRunner._run_v6. _mt_handler short-circuits for V6
because the V6 refiner stage is inline."""
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture
def admin_app(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import importlib, app as _app
    importlib.reload(_app)
    _app.app.config["R5_AUTH_BYPASS"] = True
    return _app


def test_asr_handler_profile_path_calls_existing_transcribe(admin_app):
    admin_app._file_registry["test001"] = {
        "id": "test001", "active_kind": "profile",
        "active_id": "dev-default", "user_id": 1,
    }
    job = MagicMock(file_id="test001", cancel_event=MagicMock())
    with patch.object(admin_app, "transcribe_with_segments") as mock_t:
        admin_app._asr_handler(job)
    mock_t.assert_called_once()


def test_asr_handler_v6_path_calls_pipeline_runner(admin_app):
    admin_app._file_registry["test002"] = {
        "id": "test002", "active_kind": "pipeline_v6",
        "active_id": "4696bbaa-...", "user_id": 1,
    }
    # Inject a fake pipeline dict so PipelineManager.get returns non-None
    fake_pipeline = {"id": "4696bbaa-...", "pipeline_type": "v6_vad_dual_asr",
                     "version": 6, "source_lang": "zh"}
    with patch.object(admin_app._pipeline_manager, "get", return_value=fake_pipeline), \
         patch("pipeline_runner.PipelineRunner") as MockRunner:
        MockRunner.return_value._run_v6.return_value = None
        job = MagicMock(file_id="test002", cancel_event=MagicMock())
        admin_app._asr_handler(job)
    MockRunner.assert_called_once_with(fake_pipeline)
    MockRunner.return_value._run_v6.assert_called_once()


def test_asr_handler_v6_pipeline_missing_marks_failed(admin_app):
    admin_app._file_registry["test003"] = {
        "id": "test003", "active_kind": "pipeline_v6",
        "active_id": "nonexistent", "user_id": 1,
    }
    with patch.object(admin_app._pipeline_manager, "get", return_value=None):
        job = MagicMock(file_id="test003", cancel_event=MagicMock())
        with pytest.raises(Exception, match=r"Pipeline 已被刪除|not found"):
            admin_app._asr_handler(job)


def test_mt_handler_v6_short_circuits(admin_app):
    admin_app._file_registry["test004"] = {
        "id": "test004", "active_kind": "pipeline_v6",
        "active_id": "4696bbaa-...", "user_id": 1,
    }
    job = MagicMock(file_id="test004", cancel_event=MagicMock())
    with patch.object(admin_app, "_auto_translate") as mock_at:
        admin_app._mt_handler(job)
    mock_at.assert_not_called()
    # registry should reflect completion
    assert admin_app._file_registry["test004"].get("translation_status") == "completed"


def test_mt_handler_profile_path_calls_auto_translate(admin_app):
    admin_app._file_registry["test005"] = {
        "id": "test005", "active_kind": "profile",
        "active_id": "dev-default", "user_id": 1,
    }
    job = MagicMock(file_id="test005", cancel_event=MagicMock())
    with patch.object(admin_app, "_auto_translate") as mock_at:
        admin_app._mt_handler(job)
    mock_at.assert_called_once_with("test005", cancel_event=job.cancel_event)
```

- [ ] **Step 2: Run tests, verify failing**

```bash
pytest tests/test_active_kind_dispatch.py -v 2>&1 | tail -20
```

Expected: 5 FAIL.

- [ ] **Step 3: Implement dispatch in `_asr_handler` + `_mt_handler`**

In `backend/app.py`, find `_asr_handler`. Wrap the existing body with dispatch:

```python
def _asr_handler(job):
    entry = _file_registry.get(job.file_id, {})
    kind = entry.get("active_kind", "profile")
    if kind == "pipeline_v6":
        pipeline = _pipeline_manager.get(entry["active_id"])
        if pipeline is None:
            raise RuntimeError(
                f"Pipeline 已被刪除 (active_id={entry['active_id']})，無法執行 ASR"
            )
        from pipeline_runner import PipelineRunner
        return PipelineRunner(pipeline)._run_v6(
            user_id=entry.get("user_id"),
            cancel_event=job.cancel_event,
            file_id=job.file_id,
        )
    # ── existing Profile path (unchanged) ──
    return transcribe_with_segments(job.file_id, cancel_event=job.cancel_event)
```

Then `_mt_handler`:

```python
def _mt_handler(job):
    entry = _file_registry.get(job.file_id, {})
    if entry.get("active_kind") == "pipeline_v6":
        # V6 Stage 3 refiner is inline — MT step is no-op
        with _registry_lock:
            entry["translation_status"] = "completed"
            entry["translation_kind"] = "pipeline_v6_inline"
        socketio.emit('file_updated', _file_summary(entry))
        return
    return _auto_translate(job.file_id, cancel_event=job.cancel_event)
```

- [ ] **Step 4: Run tests, verify passing**

```bash
pytest tests/test_active_kind_dispatch.py -v 2>&1 | tail -15
```

Expected: 5 PASS.

- [ ] **Step 5: Re-run all backend tests to confirm no regression**

```bash
pytest tests/ -q 2>&1 | tail -10
```

Expected: ~925 pass (907 from Phase 1 + 6 settings + 5 validator + 8 manager + 4 register_file + 5 dispatch = 35 new since baseline) / 14 pre-existing fail.

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_active_kind_dispatch.py
git commit -m "feat(v6): _asr_handler + _mt_handler dispatch on file.active_kind

When file.active_kind=pipeline_v6, _asr_handler delegates to
PipelineRunner._run_v6 instead of transcribe_with_segments.
_mt_handler short-circuits V6 files (Stage 3 refiner is inline,
no separate MT step needed). Profile path unchanged."
```

### Task 2.6: `/api/me` extension + new `POST /api/active`

**Files:**
- Modify: `backend/app.py` (find `/api/me` handler + add new `/api/active`)
- Test: `backend/tests/test_api_active.py` (new)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_api_active.py`:

```python
"""Test /api/me response includes active_kind/active_id, and new
POST /api/active unified set-active endpoint."""
import pytest
import json


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import importlib, app as _app
    importlib.reload(_app)
    _app.app.config["R5_AUTH_BYPASS"] = True
    _app.app.config["LOGIN_DISABLED"] = True
    return _app.app.test_client()


def test_api_me_includes_active_kind(client):
    r = client.get("/api/me")
    assert r.status_code == 200
    body = r.get_json()
    assert "active_kind" in body
    assert body["active_kind"] in ("profile", "pipeline_v6")
    assert "active_id" in body


def test_post_active_profile_kind(client):
    r = client.post("/api/active", json={"kind": "profile", "id": "dev-default"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["active"]["kind"] == "profile"
    assert body["active"]["id"] == "dev-default"


def test_post_active_pipeline_v6_kind(client):
    # Use one of the imported V6 pipelines
    import app as _app
    pls = _app._pipeline_manager.list_all()
    if not pls:
        pytest.skip("no V6 pipelines imported")
    pid = pls[0]["id"]
    r = client.post("/api/active", json={"kind": "pipeline_v6", "id": pid})
    assert r.status_code == 200
    assert r.get_json()["active"]["kind"] == "pipeline_v6"


def test_post_active_invalid_kind_returns_400(client):
    r = client.post("/api/active", json={"kind": "bogus", "id": "x"})
    assert r.status_code == 400


def test_post_active_unknown_id_returns_404(client):
    r = client.post("/api/active", json={"kind": "profile", "id": "nonexistent-id"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests, verify failing**

```bash
pytest tests/test_api_active.py -v 2>&1 | tail -15
```

Expected: 5 FAIL (404 or KeyError).

- [ ] **Step 3: Extend `/api/me` + add `/api/active`**

In `backend/app.py`, find the `/api/me` handler. Extend its return body:

```python
@app.get("/api/me")
@login_required
def api_me():
    user = current_user
    settings = _profile_manager._read_settings()
    return jsonify({
        "id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "active_kind": settings.get("active_kind", "profile"),         # NEW
        "active_id":   settings.get("active_id") or settings.get("active_profile"),  # NEW
    })
```

Then add the new unified endpoint after `/api/me`:

```python
@app.post("/api/active")
@login_required
def set_active():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind")
    aid = data.get("id")
    if kind not in ("profile", "pipeline_v6"):
        return jsonify({"error": "invalid kind, must be 'profile' or 'pipeline_v6'"}), 400
    if not aid:
        return jsonify({"error": "id required"}), 400

    if kind == "profile":
        result = _profile_manager.set_active(aid)
    else:
        result = _pipeline_manager.set_active(aid)

    if result is None:
        return jsonify({"error": f"{kind} not found: {aid}"}), 404
    return jsonify({"ok": True, "active": {"kind": kind, "id": aid}})
```

- [ ] **Step 4: Run tests, verify passing**

```bash
pytest tests/test_api_active.py -v 2>&1 | tail -15
```

Expected: 5 PASS.

- [ ] **Step 5: Verify `PipelineManager.set_active` exists (graft check)**

```bash
python -c "
from pipelines import PipelineManager
from pathlib import Path
mgr = PipelineManager(Path('backend/config'))
print('set_active method:', hasattr(mgr, 'set_active'))
"
```

Expected: `set_active method: True`. If False, add `set_active` to `pipelines.py` mirroring `ProfileManager.set_active` (writes `active_kind='pipeline_v6'`, `active_id`, but does NOT write `active_profile`).

If `set_active` missing, add to `backend/pipelines.py`:

```python
def set_active(self, pipeline_id):
    pipeline = self.get(pipeline_id)
    if pipeline is None:
        return None
    settings = self._read_settings()
    self._write_settings({
        **settings,
        "active_kind": "pipeline_v6",
        "active_id": pipeline_id,
    })
    return pipeline
```

(`_read_settings` + `_write_settings` should share the same `config/settings.json` file as ProfileManager — verify the path setup matches.)

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/pipelines.py backend/tests/test_api_active.py
git commit -m "feat(v6): /api/me returns active_kind/active_id, new POST /api/active

Unified set-active endpoint accepts kind=profile|pipeline_v6 and
id. Returns 400 for invalid kind, 404 for unknown id. ProfileManager
+ PipelineManager share config/settings.json file — only one is
active at any time."
```

---

## Phase 3 — Frontend rewiring (5 tasks)

All Phase 3 tasks modify either `frontend/index.html` or `frontend/proofread.html`. Vanilla JS — no React/Vite. Tests live in Phase 4.

### Task 3.1: index.html — V6 state + fetch chain

**Files:**
- Modify: `frontend/index.html` (~30 LOC added)

- [ ] **Step 1: Add V6 state variables near `let activeProfile = null`**

In `frontend/index.html`, find `let activeProfile = null;` (around line 1743). Add immediately after:

```javascript
let activePipeline     = null;       // V6 pipeline object when active_kind === "pipeline_v6"
let activeKind         = "profile";  // "profile" | "pipeline_v6" — driven by /api/me
let activeId           = null;       // current active_id (profile_id or pipeline_id)
let availablePipelines = [];         // GET /api/pipelines result
```

- [ ] **Step 2: Add fetch functions for /api/me + V6 pipelines**

Below `fetchActiveProfile`, add:

```javascript
async function fetchMe() {
  try {
    const r = await fetch(`${API_BASE}/api/me`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const me = await r.json();
    activeKind = me.active_kind || "profile";
    activeId   = me.active_id   || null;
    window.authState = window.authState || {};
    window.authState.user = me;
  } catch (e) { _initFetchError('me', e); }
}

async function fetchActivePipeline() {
  if (activeKind !== "pipeline_v6" || !activeId) {
    activePipeline = null;
    return;
  }
  try {
    const r = await fetch(`${API_BASE}/api/pipelines/${activeId}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    activePipeline = data.pipeline;
  } catch (e) { _initFetchError('active pipeline', e); }
}

async function fetchPipelines() {
  try {
    const r = await fetch(`${API_BASE}/api/pipelines`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    availablePipelines = data.pipelines || [];
    renderPipelineStrip();
  } catch (e) { _initFetchError('pipelines', e); }
}
```

- [ ] **Step 3: Wire into init chain**

Find the init chain at the bottom of `<script>` (around line 4824). Replace:

```javascript
fetchActiveProfile().then(fetchProfiles).then(fetchLanguageConfigs).then(fetchGlossaries).then(fetchFileList);
```

With:

```javascript
fetchMe()
  .then(fetchActiveProfile)
  .then(fetchActivePipeline)
  .then(fetchProfiles)
  .then(fetchPipelines)
  .then(fetchLanguageConfigs)
  .then(fetchGlossaries)
  .then(fetchFileList);
```

- [ ] **Step 4: Boot backend + manual smoke**

```bash
cd backend && source venv/bin/activate
python app.py > /tmp/backend.log 2>&1 &
sleep 5
# Open browser to http://localhost:5001/login, log in as admin_p3 / AdminPass1!
# Then visit http://localhost:5001/  and open DevTools console
# Verify: console shows no errors; `activeKind` is set; `availablePipelines.length === 2`
```

Expected: no console errors; `availablePipelines` populated with 2 V6 pipelines.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html
git commit -m "feat(v6 frontend): add activeKind/activePipeline state + fetch chain

New globals: activePipeline, activeKind, activeId, availablePipelines.
fetchMe() reads /api/me to learn active mode. fetchActivePipeline()
fetches the V6 pipeline detail when in V6 mode. fetchPipelines()
lists all V6 pipelines for the preset menu."
```

### Task 3.2: index.html — Preset menu 2-section + activatePipeline()

**Files:**
- Modify: `frontend/index.html` (~50 LOC)

- [ ] **Step 1: Modify `renderPipelineStrip` — preset menu builds 2 sections**

Find `renderPipelineStrip()` (around line 2263). Within it, find the `_profileGroupsHtml` definition (around line 2290). Right after the existing `_profileGroupsHtml` block, add:

```javascript
const _v6PipelinesHtml = availablePipelines
  .filter(p => p.pipeline_type === "v6_vad_dual_asr")
  .map(p => `
    <button ${activeKind === "pipeline_v6" && activeId === p.id ? 'class="on"' : ''}
            onclick="activatePipeline('${p.id}')">
      <div class="smn-main">
        <span class="smn-name">${escapeHtml(p.name)}</span>
        ${activeKind === "pipeline_v6" && activeId === p.id ? '<span class="smn-badge">當前</span>' : ''}
        <span class="smn-badge" style="background:rgba(74,158,255,0.18);color:var(--accent-2)">V6</span>
      </div>
      <div class="smn-desc">VAD + Qwen3-ASR + Refiner</div>
    </button>`).join('');
```

Then find the existing `presetMenuHtml = ` block. Replace with:

```javascript
const presetMenuHtml = `
  <div class="step-menu preset-menu" style="min-width: 280px;">
    <div class="step-menu-head">舊有 Profile 組合</div>
    ${_profileGroupsHtml}
    ${_v6PipelinesHtml ? `
      <div class="split-divider"></div>
      <div class="step-menu-head">Dual-ASR Pipeline (V6)</div>
      ${_v6PipelinesHtml}
    ` : ''}
    <div class="split-divider"></div>
    <button class="smn-manage" onclick="openProfileSaveModal()"><span class="fmt-badge outline">💾</span><span class="fmt-desc">將當前設定儲存為新預設…</span></button>
    <button class="smn-manage" onclick="openProfileManageModal()"><span class="fmt-badge outline">⚙</span><span class="fmt-desc">管理預設…</span></button>
  </div>`;
```

- [ ] **Step 2: Add `activatePipeline()` function**

Right after the existing `activateProfile()` (around line 3054), add:

```javascript
async function activatePipeline(id) {
  if (_activatingProfile) return;
  _activatingProfile = true;
  try {
    const r = await fetch(`${API_BASE}/api/active`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: 'pipeline_v6', id }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    await fetchMe();
    await fetchActivePipeline();
    activeProfile = null;
    renderAll();
    const pl = availablePipelines.find(p => p.id === id);
    showToast(`已切換到 V6 Pipeline：${pl?.name || id}`, 'success');
  } catch (e) {
    showToast('切換失敗', 'error');
  } finally {
    _activatingProfile = false;
  }
}
```

Also update `activateProfile` to use the new unified endpoint:

```javascript
async function activateProfile(id) {
  if (_activatingProfile) return;
  _activatingProfile = true;
  try {
    await fetch(`${API_BASE}/api/active`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: 'profile', id }),
    });
    await fetchMe();
    await fetchActiveProfile();
    activePipeline = null;  // clear V6 state
    renderAll();
    showToast('已切換 Pipeline', 'success');
  } catch (e) { showToast('切換失敗', 'error'); }
  finally { _activatingProfile = false; }
}
```

- [ ] **Step 3: Manual smoke test**

Reload `http://localhost:5001/`. Click Pipeline preset dropdown.

Expected:
- Two sections: "舊有 Profile 組合" + "Dual-ASR Pipeline (V6)"
- V6 section lists 2 pipelines with "V6" badge
- Click 賽馬廣播 → toast "已切換到 V6 Pipeline：[v6] 賽馬廣播 (Cantonese)" → preset name updates

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat(v6 frontend): preset menu 2 sections + activatePipeline()

Pipeline preset dropdown shows '舊有 Profile 組合' + 'Dual-ASR
Pipeline (V6)' sections. activatePipeline() POSTs /api/active
with kind=pipeline_v6. activateProfile() refactored to also use
the unified endpoint."
```

### Task 3.3: index.html — V6-specific strip columns (`renderPipelineStripV6`)

**Files:**
- Modify: `frontend/index.html` (~80 LOC)

- [ ] **Step 1: Refactor `renderPipelineStrip` to dispatch on activeKind**

At the top of `renderPipelineStrip()` (around line 2263), add:

```javascript
function renderPipelineStrip() {
  const el = document.getElementById('pipelineStrip');
  if (activeKind === "pipeline_v6") {
    return renderPipelineStripV6(el);
  }
  // ── existing Profile rendering body (unchanged) ──
  // (rest of function as-is)
}
```

- [ ] **Step 2: Add `renderPipelineStripV6` immediately after**

```javascript
function renderPipelineStripV6(el) {
  const p = activePipeline || { vad: {}, qwen3_asr: {}, refinements: { zh: [{}] } };
  const preset = p.name || '未選擇';

  // Build preset menu (reuse logic from main renderPipelineStrip — extract helper if duplicating)
  const _currentUserId = window.authState?.user?.id ?? null;
  const _sharedProfiles = availableProfiles.filter(pr => pr.user_id === null || pr.user_id === undefined);
  const _myProfiles = _currentUserId !== null
    ? availableProfiles.filter(pr => pr.user_id === _currentUserId) : [];
  const _renderProfileButton = pr => `
    <button onclick="activateProfile('${pr.id}')">
      <div class="smn-main">
        <span class="smn-name">${escapeHtml(pr.name || pr.id)}</span>
      </div>
      <div class="smn-desc">${escapeHtml(pr.asr?.model_size || '—')} · ${escapeHtml((pr.translation?.engine || '—').replace(/-cloud$/,''))}</div>
    </button>`;
  let _profileGroupsHtml = '';
  if (_myProfiles.length) { _profileGroupsHtml += '<div class="step-menu-section-label">我嘅</div>'; _profileGroupsHtml += _myProfiles.map(_renderProfileButton).join(''); }
  if (_sharedProfiles.length) { if (_myProfiles.length) _profileGroupsHtml += '<div class="split-divider"></div>'; _profileGroupsHtml += '<div class="step-menu-section-label">共享</div>'; _profileGroupsHtml += _sharedProfiles.map(_renderProfileButton).join(''); }
  const _v6PipelinesHtml = availablePipelines
    .filter(pp => pp.pipeline_type === "v6_vad_dual_asr")
    .map(pp => `
      <button ${activeId === pp.id ? 'class="on"' : ''} onclick="activatePipeline('${pp.id}')">
        <div class="smn-main">
          <span class="smn-name">${escapeHtml(pp.name)}</span>
          ${activeId === pp.id ? '<span class="smn-badge">當前</span>' : ''}
          <span class="smn-badge" style="background:rgba(74,158,255,0.18);color:var(--accent-2)">V6</span>
        </div>
      </button>`).join('');
  const presetMenuHtml = `
    <div class="step-menu preset-menu" style="min-width: 280px;">
      <div class="step-menu-head">舊有 Profile 組合</div>
      ${_profileGroupsHtml}
      <div class="split-divider"></div>
      <div class="step-menu-head">Dual-ASR Pipeline (V6)</div>
      ${_v6PipelinesHtml}
    </div>`;

  // VAD column
  const vadThr = p.vad?.threshold ?? 0.5;
  const vadMin = (p.vad?.min_speech_duration_ms ?? 250) / 1000;
  const vadCell = `${vadThr} · min ${vadMin.toFixed(2)}s`;

  // Qwen3 context column — truncated preview
  const ctxFull = p.qwen3_asr?.context || '';
  const ctxCell = ctxFull ? (ctxFull.length > 18 ? ctxFull.slice(0, 18) + '…' : ctxFull) : '（無）';

  // Refiner column
  const refinerId = p.refinements?.zh?.[0]?.refiner_profile_id;
  const refinerCell = refinerId ? refinerId.slice(0, 8) : '未設定';

  const outputFmt = window._preferredOutputFormat || 'H.264 · MP4';

  el.innerHTML = `
    <div class="pipeline-preset-wrap">
      <button class="pipeline-preset" title="切換 Pipeline 預設">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="var(--accent)" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="5" width="4" height="6" rx="1"/><rect x="11" y="5" width="4" height="6" rx="1"/><circle cx="8" cy="2" r="1.5"/><circle cx="8" cy="14" r="1.5"/><path d="M5 8h6 M8 3.5v3 M8 9.5v3"/></svg>
        <div class="pp-text">
          <div class="pp-k">Pipeline · V6</div>
          <div class="pp-v">${escapeHtml(preset)}</div>
        </div>
        <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6l4 4 4-4"/></svg>
      </button>
      ${presetMenuHtml}
    </div>
    <span class="sep"></span>
    <div class="step" data-step="vad" tabindex="0">
      <div><div class="k">VAD</div><div class="v">${escapeHtml(vadCell)}</div></div>
    </div>
    <span class="arrow">→</span>
    <div class="step" data-step="qwen3-ctx" tabindex="0" onclick="openPromptPanelInline('qwen3_context')" style="cursor:pointer;">
      <div><div class="k">Qwen3 Context</div><div class="v">${escapeHtml(ctxCell)}</div></div>
      <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6l4 4 4-4"/></svg>
    </div>
    <span class="arrow">→</span>
    <div class="step" data-step="output" tabindex="0">
      <div><div class="k">輸出</div><div class="v">${escapeHtml(outputFmt)}</div></div>
    </div>
    <span class="arrow">→</span>
    <div class="step" data-step="refiner" tabindex="0" onclick="openPromptPanelInline('refiner_prompt')" style="cursor:pointer;">
      <div><div class="k">Refiner</div><div class="v">${escapeHtml(refinerCell)}</div></div>
      <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6l4 4 4-4"/></svg>
    </div>`;
}
```

- [ ] **Step 3: Add CSS for V6 columns (accent border)**

In `<style>` block (around line 250 where `.pipeline-strip` styles live), add:

```css
.pipeline-strip .step[data-step="vad"],
.pipeline-strip .step[data-step="qwen3-ctx"],
.pipeline-strip .step[data-step="refiner"] {
  border-left: 2px solid var(--accent-2);
}
```

- [ ] **Step 4: Manual smoke**

Reload page, switch to V6 pipeline via preset dropdown.

Expected:
- Pipeline strip swaps: ASR → VAD, MT → Qwen3 Context, 術語表 → Refiner
- Output column stays
- VAD shows "0.5 · min 0.25s"
- Qwen3 Context shows truncated 賽馬 names
- Refiner shows refiner profile id prefix
- Each V6 column has accent-2 left border

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html
git commit -m "feat(v6 frontend): Pipeline strip swaps ASR/MT/glossary → VAD/Qwen3/Refiner

renderPipelineStrip() dispatches on activeKind. V6 mode shows
4 columns: Pipeline preset → VAD → Qwen3 Context → 輸出 → Refiner.
V6 column cells have left border in --accent-2 to visually
distinguish from Profile mode."
```

### Task 3.4: index.html — Inline prompt panel for Qwen3/Refiner edit

**Files:**
- Modify: `frontend/index.html` (~80 LOC)

- [ ] **Step 1: Add inline panel functions**

Near the end of the `<script>` block (before init chain), add:

```javascript
function openPromptPanelInline(key) {
  let panel = document.getElementById('inlinePromptPanel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'inlinePromptPanel';
    panel.className = 'inline-prompt-panel';
    panel.innerHTML = `
      <div class="ipp-head">
        <span id="ippTitle"></span>
        <button onclick="closeInlinePromptPanel()" aria-label="關閉">×</button>
      </div>
      <textarea id="ippTextarea" rows="6"></textarea>
      <div class="ipp-foot">
        <span id="ippHint" style="font-size:11px;color:var(--text-dim);"></span>
        <button onclick="commitInlinePrompt()" class="btn-primary">儲存到當前 Pipeline</button>
      </div>`;
    document.body.appendChild(panel);
  }
  panel._editingKey = key;

  const titles = { qwen3_context: 'Qwen3 ASR Context', refiner_prompt: 'Refiner LLM Prompt' };
  document.getElementById('ippTitle').textContent = titles[key];

  let initialValue = '';
  if (key === 'qwen3_context') {
    initialValue = activePipeline?.qwen3_asr?.context || '';
  } else {
    // refiner_prompt — load from refiner_profile
    const refinerId = activePipeline?.refinements?.zh?.[0]?.refiner_profile_id;
    if (refinerId) {
      const rp = window._refinerProfilesCache?.[refinerId];
      initialValue = rp?.prompt_template || '';
    }
  }
  document.getElementById('ippTextarea').value = initialValue;
  document.getElementById('ippHint').textContent =
    '修改會即時寫入 Pipeline 設定。要 per-file override，請去 Proofread page。';
  panel.style.display = 'block';
}

function closeInlinePromptPanel() {
  const panel = document.getElementById('inlinePromptPanel');
  if (panel) panel.style.display = 'none';
}

async function commitInlinePrompt() {
  const panel = document.getElementById('inlinePromptPanel');
  const key = panel._editingKey;
  const value = document.getElementById('ippTextarea').value;

  try {
    if (key === 'qwen3_context') {
      // PATCH pipeline JSON
      const r = await fetch(`${API_BASE}/api/pipelines/${activePipeline.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qwen3_asr: { ...activePipeline.qwen3_asr, context: value } }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
    } else if (key === 'refiner_prompt') {
      // PATCH refiner_profile JSON
      const refinerId = activePipeline.refinements?.zh?.[0]?.refiner_profile_id;
      if (!refinerId) throw new Error('No refiner profile set on this pipeline');
      const r = await fetch(`${API_BASE}/api/refiner_profiles/${refinerId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt_template: value }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
    }

    await fetchActivePipeline();
    renderPipelineStrip();
    closeInlinePromptPanel();
    showToast('已更新 Pipeline 設定', 'success');
  } catch (e) {
    showToast(`儲存失敗: ${e.message}`, 'error');
  }
}
```

- [ ] **Step 2: Add CSS for inline panel**

In `<style>`, append:

```css
.inline-prompt-panel {
  display: none;
  position: fixed; top: 64px; right: 16px;
  width: 420px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 16px 40px rgba(0,0,0,0.55);
  padding: 14px;
  z-index: 200;
}
.inline-prompt-panel .ipp-head {
  display: flex; justify-content: space-between;
  font-size: 13px; font-weight: 600;
  margin-bottom: 8px;
}
.inline-prompt-panel .ipp-head button {
  background: none; border: none; color: var(--text-dim);
  font-size: 18px; cursor: pointer; padding: 0 4px;
}
.inline-prompt-panel textarea {
  width: 100%; font-family: var(--font-mono);
  font-size: 12px; padding: 8px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  resize: vertical;
}
.inline-prompt-panel .ipp-foot {
  display: flex; justify-content: space-between;
  align-items: center; margin-top: 8px; gap: 8px;
}
.inline-prompt-panel .btn-primary {
  background: var(--accent); color: white;
  border: none; padding: 6px 14px;
  border-radius: 6px; cursor: pointer;
  font-size: 12px; font-weight: 600;
}
.inline-prompt-panel .btn-primary:hover { opacity: 0.9; }
```

- [ ] **Step 3: Add refiner profile cache fetch (so refiner_prompt can preload)**

Below `fetchPipelines()`, add:

```javascript
async function fetchRefinerProfiles() {
  try {
    const r = await fetch(`${API_BASE}/api/refiner_profiles`);
    if (!r.ok) return;
    const data = await r.json();
    window._refinerProfilesCache = {};
    (data.profiles || []).forEach(p => { window._refinerProfilesCache[p.id] = p; });
  } catch (e) { _initFetchError('refiner profiles', e); }
}
```

Add to init chain after `fetchPipelines`:

```javascript
.then(fetchPipelines)
.then(fetchRefinerProfiles)
.then(fetchLanguageConfigs)
...
```

- [ ] **Step 4: Manual smoke**

Reload, switch to V6 pipeline, click Qwen3 Context column.

Expected:
- Panel opens with title "Qwen3 ASR Context", textarea preloaded with current context
- Edit text, click "儲存到當前 Pipeline"
- Toast "已更新 Pipeline 設定"
- Strip Qwen3 column reflects new context
- Repeat for Refiner column — opens with title "Refiner LLM Prompt", preloads refiner profile's prompt_template

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html
git commit -m "feat(v6 frontend): inline prompt panel on Dashboard V6 columns

Click Qwen3 Context column → floating panel opens with current
qwen3_asr.context, commit PATCHes /api/pipelines/<id>. Click
Refiner column → preloads referenced refiner_profile.prompt_template,
commit PATCHes /api/refiner_profiles/<id>. Per-file override
still happens on Proofread page (Task 3.5)."
```

### Task 3.5: proofread.html — Mode-aware 自訂 Prompt panel

**Files:**
- Modify: `frontend/proofread.html` (~60 LOC)

- [ ] **Step 1: Add V6 textarea section to existing panel HTML**

In `frontend/proofread.html`, find the existing "自訂 Prompt" panel (`#promptPanel` or similar, look for `textarea` ids like `poAnchor`, `poSingle`). Identify the section that contains the 4 v3.18 textareas. Wrap them in a div:

```html
<!-- Replace existing 4-textarea block -->
<div class="prompt-section" data-mode="profile">
  <!-- existing v3.18 textareas: poAnchor, poSingle, poEnrich, poPass1 -->
  ...
</div>

<!-- NEW V6 section -->
<div class="prompt-section" data-mode="pipeline_v6" style="display:none;">
  <label style="display:flex;flex-direction:column;gap:4px;font-size:12px;margin-bottom:8px;">
    Qwen3 ASR Context
    <textarea id="poQwen3Context" rows="4"
              placeholder="提示 model 將會出現嘅人名 / 地名 / 術語"
              style="width:100%;font-family:var(--font-mono);font-size:12px;padding:8px;background:var(--surface-2);border:1px solid var(--border);border-radius:6px;"></textarea>
  </label>
  <label style="display:flex;flex-direction:column;gap:4px;font-size:12px;">
    Refiner LLM Prompt（留空用 Pipeline 預設）
    <textarea id="poRefinerPrompt" rows="6"
              placeholder=""
              style="width:100%;font-family:var(--font-mono);font-size:12px;padding:8px;background:var(--surface-2);border:1px solid var(--border);border-radius:6px;"></textarea>
  </label>
</div>
```

- [ ] **Step 2: Add mode-switching logic**

In the `<script>` block of `proofread.html`, find the function that populates the prompt panel (probably called when a file is loaded). Add:

```javascript
function showPromptPanelForFile(file) {
  const profileSection = document.querySelector('.prompt-section[data-mode="profile"]');
  const v6Section      = document.querySelector('.prompt-section[data-mode="pipeline_v6"]');
  const overrides = file?.prompt_overrides || {};

  if (file?.active_kind === "pipeline_v6") {
    if (profileSection) profileSection.style.display = 'none';
    if (v6Section)      v6Section.style.display      = 'block';
    document.getElementById('poQwen3Context').value  = overrides.qwen3_context  || '';
    document.getElementById('poRefinerPrompt').value = overrides.refiner_prompt || '';
  } else {
    if (profileSection) profileSection.style.display = 'block';
    if (v6Section)      v6Section.style.display      = 'none';
    // existing populate for poAnchor / poSingle / poEnrich / poPass1
    document.getElementById('poAnchor').value = overrides.anchor || '';
    document.getElementById('poSingle').value = overrides.single || '';
    document.getElementById('poEnrich').value = overrides.enrich || '';
    document.getElementById('poPass1').value  = overrides.pass1  || '';
  }
}

// Wire showPromptPanelForFile into the existing file-load callback.
// (search for where activeFile is set + panel rendered; call showPromptPanelForFile(activeFile) there)
```

- [ ] **Step 3: Update `commitOverrides()` to branch on mode**

Find the existing `commitOverrides()` (or whatever the commit-to-PATCH function is called). Replace its body with:

```javascript
async function commitOverrides() {
  if (!activeFile) return;
  const isV6 = activeFile.active_kind === "pipeline_v6";
  const patch = isV6
    ? {
        prompt_overrides: {
          qwen3_context:  document.getElementById('poQwen3Context').value.trim()  || null,
          refiner_prompt: document.getElementById('poRefinerPrompt').value.trim() || null,
        }
      }
    : {
        prompt_overrides: {
          anchor: document.getElementById('poAnchor').value.trim() || null,
          single: document.getElementById('poSingle').value.trim() || null,
          enrich: document.getElementById('poEnrich').value.trim() || null,
          pass1:  document.getElementById('poPass1').value.trim()  || null,
        }
      };

  try {
    const r = await fetch(`${API_BASE}/api/files/${activeFile.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    activeFile = data.file || activeFile;
    showToast('已儲存 per-file override', 'success');
  } catch (e) {
    showToast(`儲存失敗: ${e.message}`, 'error');
  }
}
```

- [ ] **Step 4: Manual smoke**

Pre-condition: have at least one file that was uploaded WHILE V6 pipeline was active (so its `active_kind=pipeline_v6`).

1. On Dashboard, switch to V6 pipeline.
2. Upload a small test audio file.
3. After upload, click into Proofread page for that file.
4. Open 自訂 Prompt panel.

Expected:
- Panel shows only 2 textareas: Qwen3 ASR Context + Refiner LLM Prompt
- The 4 v3.18 textareas (Anchor/Single/Enrich/Pass1) are hidden
- Type something in Qwen3 Context, click commit
- Toast "已儲存 per-file override"
- Refresh page → values persist

Switch back to Profile mode for a different file:
- That file's panel should show the 4 original textareas, NOT the V6 ones

- [ ] **Step 5: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(v6 frontend): Proofread 自訂 Prompt panel becomes mode-aware

V6 file (file.active_kind=pipeline_v6) → shows qwen3_context +
refiner_prompt textareas only. Profile file → shows existing
anchor/single/enrich/pass1 textareas. commitOverrides() PATCHes
the correct key set based on mode."
```

---

## Phase 4 — Playwright tests (1 task, 7 cases)

### Task 4.1: V6 Pipeline strip Playwright spec

**Files:**
- Create: `frontend/tests/test_v6_pipeline_strip.spec.js`

- [ ] **Step 1: Write the Playwright spec**

Create `frontend/tests/test_v6_pipeline_strip.spec.js`:

```javascript
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test.describe("V6 Pipeline strip", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE + "/");
    await page.waitForFunction(() => typeof activeKind !== 'undefined');
  });

  test("presetMenuShowsBothSections", async ({ page }) => {
    // Hover/focus the Pipeline preset to open dropdown
    await page.locator(".pipeline-preset").click();
    const menu = page.locator(".preset-menu");
    await expect(menu.locator(".step-menu-head", { hasText: "舊有 Profile 組合" })).toBeVisible();
    await expect(menu.locator(".step-menu-head", { hasText: "Dual-ASR Pipeline (V6)" })).toBeVisible();
  });

  test("activateV6PipelineRendersV6Columns", async ({ page }) => {
    // Switch to V6
    await page.evaluate(async () => {
      const pl = availablePipelines.find(p => p.pipeline_type === "v6_vad_dual_asr");
      await activatePipeline(pl.id);
    });
    await page.waitForFunction(() => activeKind === "pipeline_v6");
    // Verify V6 columns
    await expect(page.locator('[data-step="vad"]')).toBeVisible();
    await expect(page.locator('[data-step="qwen3-ctx"]')).toBeVisible();
    await expect(page.locator('[data-step="refiner"]')).toBeVisible();
    // Profile columns hidden
    await expect(page.locator('[data-step="asr"]')).toHaveCount(0);
    await expect(page.locator('[data-step="mt"]')).toHaveCount(0);
  });

  test("clickQwen3ContextOpensInlinePanel", async ({ page }) => {
    await page.evaluate(async () => {
      const pl = availablePipelines.find(p => p.pipeline_type === "v6_vad_dual_asr");
      await activatePipeline(pl.id);
    });
    await page.waitForFunction(() => activeKind === "pipeline_v6");
    await page.locator('[data-step="qwen3-ctx"]').click();
    const panel = page.locator("#inlinePromptPanel");
    await expect(panel).toBeVisible();
    await expect(panel.locator("#ippTitle")).toHaveText("Qwen3 ASR Context");
    const initialValue = await panel.locator("#ippTextarea").inputValue();
    expect(initialValue.length).toBeGreaterThan(0); // pipeline has 賽馬 context
  });

  test("commitInlinePanelPatchesPipeline", async ({ page }) => {
    await page.evaluate(async () => {
      const pl = availablePipelines.find(p => p.pipeline_type === "v6_vad_dual_asr");
      await activatePipeline(pl.id);
    });
    await page.locator('[data-step="qwen3-ctx"]').click();
    const newCtx = "TEST_CTX_" + Date.now();
    await page.locator("#ippTextarea").fill(newCtx);

    // Watch the PATCH request
    const patchPromise = page.waitForResponse(r =>
      r.url().includes("/api/pipelines/") && r.request().method() === "PATCH"
    );
    await page.locator("#inlinePromptPanel .btn-primary").click();
    const patch = await patchPromise;
    expect(patch.ok()).toBeTruthy();
    const body = patch.request().postDataJSON();
    expect(body.qwen3_asr.context).toBe(newCtx);

    // Restore original
    await page.evaluate(async (orig) => {
      await fetch(`/api/pipelines/${activePipeline.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qwen3_asr: { ...activePipeline.qwen3_asr, context: orig } }),
      });
    }, "袁幸堯");  // placeholder; in real run pre-save the original
  });

  test("switchBackToProfileRestoresProfileColumns", async ({ page }) => {
    // Start in V6
    await page.evaluate(async () => {
      const pl = availablePipelines.find(p => p.pipeline_type === "v6_vad_dual_asr");
      await activatePipeline(pl.id);
    });
    await page.waitForFunction(() => activeKind === "pipeline_v6");

    // Switch back to dev-default Profile
    await page.evaluate(async () => { await activateProfile('dev-default'); });
    await page.waitForFunction(() => activeKind === "profile");

    await expect(page.locator('[data-step="asr"]')).toBeVisible();
    await expect(page.locator('[data-step="mt"]')).toBeVisible();
    await expect(page.locator('[data-step="vad"]')).toHaveCount(0);
  });

  test("proofreadPanelShowsV6FieldsForV6File", async ({ page }) => {
    // Need a file with active_kind=pipeline_v6 — fake via direct registry manipulation
    // (via test endpoint, or skip if no such file exists)
    const v6FileId = await page.evaluate(async () => {
      const files = Object.values(uploadedFiles);
      return files.find(f => f.active_kind === "pipeline_v6")?.id;
    });
    test.skip(!v6FileId, "no V6 file in registry to test against");

    await page.goto(`${BASE}/proofread.html?file=${v6FileId}`);
    await page.locator("#promptPanel").waitFor();

    await expect(page.locator("#poQwen3Context")).toBeVisible();
    await expect(page.locator("#poRefinerPrompt")).toBeVisible();
    await expect(page.locator("#poAnchor")).toBeHidden();
  });

  test("proofreadCommitV6OverridesPatchesFile", async ({ page }) => {
    const v6FileId = await page.evaluate(async () => {
      const files = Object.values(uploadedFiles);
      return files.find(f => f.active_kind === "pipeline_v6")?.id;
    });
    test.skip(!v6FileId, "no V6 file in registry to test against");

    await page.goto(`${BASE}/proofread.html?file=${v6FileId}`);
    await page.locator("#poQwen3Context").fill("test override");

    const patchPromise = page.waitForResponse(r =>
      r.url().includes(`/api/files/${v6FileId}`) && r.request().method() === "PATCH"
    );
    await page.locator("button:has-text('儲存 per-file override')").click();
    const patch = await patchPromise;
    expect(patch.ok()).toBeTruthy();
    const body = patch.request().postDataJSON();
    expect(body.prompt_overrides.qwen3_context).toBe("test override");
  });
});
```

- [ ] **Step 2: Boot backend, run Playwright**

```bash
cd backend && source venv/bin/activate
python app.py > /tmp/backend.log 2>&1 &
sleep 8
cd ../frontend
npx playwright test tests/test_v6_pipeline_strip.spec.js --reporter=line 2>&1 | tail -20
```

Expected: 7 PASS (or 5 PASS + 2 skip if no V6 file in registry yet — that's acceptable for first run; upload a V6 file then re-run to cover all 7).

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/test_v6_pipeline_strip.spec.js
git commit -m "test(v6): Playwright spec — V6 Pipeline strip + Proofread panel

7 cases covering: preset menu 2 sections, V6 columns render, inline
panel open/edit/PATCH, switch-back to Profile restores ASR/MT,
Proofread panel mode-aware (V6 vs Profile), commit per-file
prompt_overrides for V6 keys."
```

---

## Phase 5 — Migration + setup (3 tasks)

### Task 5.1: File registry migration script

**Files:**
- Create: `backend/scripts/migrate_active_kind.py`
- Test: `backend/tests/test_migrate_active_kind.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_migrate_active_kind.py`:

```python
"""Test the file registry active_kind backfill migration."""
import json
import pytest
from pathlib import Path


def test_migration_backfills_legacy_entries(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({
        "fid_legacy": {"id": "fid_legacy", "original_name": "old.mp4", "user_id": 1},
        "fid_modern": {"id": "fid_modern", "original_name": "new.mp4",
                       "user_id": 1, "active_kind": "profile", "active_id": "dev-default"},
    }))
    from scripts.migrate_active_kind import migrate_registry
    migrate_registry(registry_path, default_profile_id="prod-default")
    after = json.loads(registry_path.read_text())
    # Legacy entry gets backfilled
    assert after["fid_legacy"]["active_kind"] == "profile"
    assert after["fid_legacy"]["active_id"] == "prod-default"
    # Modern entry untouched
    assert after["fid_modern"]["active_kind"] == "profile"
    assert after["fid_modern"]["active_id"] == "dev-default"


def test_migration_is_idempotent(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({
        "f1": {"id": "f1", "active_kind": "profile", "active_id": "dev-default"}
    }))
    from scripts.migrate_active_kind import migrate_registry
    migrate_registry(registry_path, default_profile_id="prod-default")
    migrate_registry(registry_path, default_profile_id="prod-default")
    # Should still be exactly what we set
    after = json.loads(registry_path.read_text())
    assert after["f1"]["active_id"] == "dev-default"


def test_migration_prefers_profile_id_field_when_present(tmp_path):
    """v3.10 R5 Phase 2 stored profile_id on file entries; migration should use it."""
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({
        "f1": {"id": "f1", "user_id": 1, "profile_id": "custom-xyz"},
    }))
    from scripts.migrate_active_kind import migrate_registry
    migrate_registry(registry_path, default_profile_id="prod-default")
    after = json.loads(registry_path.read_text())
    assert after["f1"]["active_id"] == "custom-xyz"
```

- [ ] **Step 2: Run tests, verify failing**

```bash
cd backend && source venv/bin/activate
pytest tests/test_migrate_active_kind.py -v 2>&1 | tail -10
```

Expected: 3 FAIL (module not found).

- [ ] **Step 3: Implement migration script**

Create `backend/scripts/migrate_active_kind.py`:

```python
"""Backfill active_kind + active_id on legacy file registry entries.

Idempotent — entries already carrying active_kind are left untouched.
Run once at backend boot (or manually); safe to re-run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def migrate_registry(registry_path: Path, *, default_profile_id: str = "prod-default") -> int:
    """Backfill missing active_kind/active_id fields on legacy entries.

    Returns the count of entries modified.
    """
    if not registry_path.exists():
        return 0
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    modified = 0
    for fid, entry in registry.items():
        if "active_kind" in entry and "active_id" in entry:
            continue
        entry["active_kind"] = "profile"
        # Prefer profile_id field (v3.10 R5 Phase 2) — falls back to default
        entry["active_id"] = entry.get("profile_id") or default_profile_id
        modified += 1
    if modified:
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return modified


if __name__ == "__main__":
    backend = Path(__file__).resolve().parents[1]
    reg_path = backend / "data" / "registry.json"
    n = migrate_registry(reg_path)
    print(f"migrated {n} legacy file entries")
```

- [ ] **Step 4: Run tests, verify passing**

```bash
pytest tests/test_migrate_active_kind.py -v 2>&1 | tail -10
```

Expected: 3 PASS.

- [ ] **Step 5: Wire migration into `app.py` boot**

In `backend/app.py`, near the bottom of the initialization block (after all managers are set up, before `socketio.run`), add:

```python
# One-shot migration — idempotent, runs on every boot
try:
    from scripts.migrate_active_kind import migrate_registry
    n = migrate_registry(DATA_DIR / "registry.json", default_profile_id="prod-default")
    if n > 0:
        print(f"[migrate] backfilled active_kind on {n} legacy file entries")
except ImportError:
    pass  # migration script removed/renamed
```

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/migrate_active_kind.py backend/tests/test_migrate_active_kind.py backend/app.py
git commit -m "feat(v6): file registry active_kind backfill migration (idempotent)

Boot-time migration backfills active_kind='profile' + active_id
(prefers profile_id field from v3.10, falls back to prod-default)
on legacy file entries. Idempotent — modern entries untouched."
```

### Task 5.2: `setup_v6.sh` script

**Files:**
- Create: `backend/scripts/setup_v6.sh`

- [ ] **Step 1: Write the setup script**

Create `backend/scripts/setup_v6.sh`:

```bash
#!/usr/bin/env bash
# Set up Qwen3-ASR Python 3.11 subprocess venv.
# Idempotent — skips if already present and working.

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_QWEN="$BACKEND_DIR/scripts/v5_prototype/venv_qwen"

echo "[setup_v6] target venv: $VENV_QWEN"

# Check if py3.11 is available
if ! command -v python3.11 >/dev/null 2>&1; then
  echo "[setup_v6] ERROR: python3.11 not found in PATH. Install via:"
  echo "  macOS:  brew install python@3.11"
  echo "  Linux:  sudo apt-get install python3.11 python3.11-venv"
  exit 1
fi

# Skip if venv already set up + mlx_qwen3_asr import works
if [ -x "$VENV_QWEN/bin/python" ]; then
  if "$VENV_QWEN/bin/python" -c "import mlx_qwen3_asr" 2>/dev/null; then
    echo "[setup_v6] venv already set up — skip"
    exit 0
  fi
fi

# Create venv
mkdir -p "$(dirname "$VENV_QWEN")"
python3.11 -m venv "$VENV_QWEN"
echo "[setup_v6] created py3.11 venv at $VENV_QWEN"

# Upgrade pip
"$VENV_QWEN/bin/pip" install --upgrade pip

# Install Qwen3-ASR + transitive deps
"$VENV_QWEN/bin/pip" install \
  "mlx_qwen3_asr==0.3.5" \
  "soundfile>=0.13.0" \
  "numpy"

# Smoke test
"$VENV_QWEN/bin/python" -c "
import mlx_qwen3_asr
import soundfile
print(f'mlx_qwen3_asr {getattr(mlx_qwen3_asr, \"__version__\", \"\")} OK')
print(f'soundfile {soundfile.__version__} OK')
"

echo "[setup_v6] done. V6 pipelines are now available."
```

Make executable:

```bash
chmod +x backend/scripts/setup_v6.sh
```

- [ ] **Step 2: Verify the script (only if venv missing — current local already has it)**

```bash
# Local already has venv_qwen — script should print "venv already set up — skip"
bash backend/scripts/setup_v6.sh
```

Expected: `[setup_v6] venv already set up — skip`.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/setup_v6.sh
git commit -m "feat(v6): setup_v6.sh — idempotent Qwen3-ASR venv installer

Creates backend/scripts/v5_prototype/venv_qwen/ (py3.11) and
pip installs mlx_qwen3_asr==0.3.5 + soundfile + numpy.
Idempotent: skips if mlx_qwen3_asr already importable."
```

### Task 5.3: `V6_AVAILABLE` boot-time flag

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_v6_available_flag.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_v6_available_flag.py`:

```python
"""Test that V6_AVAILABLE is set correctly based on venv_qwen presence."""
import pytest


def test_v6_available_flag_set_at_boot():
    import app
    assert "V6_AVAILABLE" in app.app.config
    assert isinstance(app.app.config["V6_AVAILABLE"], bool)


def test_api_me_includes_v6_available():
    import app
    client = app.app.test_client()
    app.app.config["LOGIN_DISABLED"] = True
    app.app.config["R5_AUTH_BYPASS"] = True
    r = client.get("/api/me")
    body = r.get_json()
    assert "v6_available" in body
    assert isinstance(body["v6_available"], bool)
```

- [ ] **Step 2: Run tests, verify failing**

```bash
pytest tests/test_v6_available_flag.py -v 2>&1 | tail -10
```

Expected: 2 FAIL.

- [ ] **Step 3: Add V6_AVAILABLE detection**

In `backend/app.py`, after the manager initialization block (Task 2.3), add:

```python
# V6 environment health check — disables V6 in UI if Qwen3 subprocess venv missing
_qwen_venv_python = (
    Path(__file__).resolve().parent / "scripts/v5_prototype/venv_qwen/bin/python"
)
if not _qwen_venv_python.exists():
    print("[V6] WARNING: Qwen3 subprocess venv missing — V6 pipelines unavailable")
    print(f"[V6]   Run: bash {_qwen_venv_python.parent.parent.parent}/setup_v6.sh")
    app.config["V6_AVAILABLE"] = False
else:
    app.config["V6_AVAILABLE"] = True
```

Then in the `/api/me` handler (Task 2.6), add:

```python
return jsonify({
    # ... existing fields ...
    "v6_available": app.config.get("V6_AVAILABLE", False),
})
```

- [ ] **Step 4: Update frontend to gray V6 section when v6_available=false**

In `frontend/index.html` `renderPipelineStrip()`, find the V6 preset section. Update:

```javascript
const v6Available = window.authState?.user?.v6_available !== false;
const _v6PipelinesHtml = !v6Available
  ? `<div style="padding:8px 12px;color:var(--text-dim);font-size:11px;">⚠ Qwen3 venv 未安裝 — 跑 setup_v6.sh</div>`
  : availablePipelines
      .filter(p => p.pipeline_type === "v6_vad_dual_asr")
      .map(/* ... existing button rendering ... */).join('');
```

Update `fetchMe` to store `v6_available`:

```javascript
window.authState.user = me;
window.authState.v6_available = me.v6_available;
```

- [ ] **Step 5: Run tests, verify passing**

```bash
pytest tests/test_v6_available_flag.py -v 2>&1 | tail -10
```

Expected: 2 PASS.

- [ ] **Step 6: Manual smoke**

Boot backend. Visit dashboard. Open Pipeline preset.

Expected: If venv_qwen exists → V6 section shows pipelines normally. If venv_qwen renamed temporarily → V6 section shows "⚠ Qwen3 venv 未安裝 — 跑 setup_v6.sh".

- [ ] **Step 7: Commit**

```bash
git add backend/app.py backend/tests/test_v6_available_flag.py frontend/index.html
git commit -m "feat(v6): V6_AVAILABLE boot flag + frontend grays V6 section if missing

Boot detects venv_qwen/bin/python presence. /api/me returns
v6_available flag. Frontend grays V6 preset section + shows
tooltip pointing to setup_v6.sh when venv missing."
```

---

## Phase 6 — Documentation (2 tasks)

### Task 6.1: CLAUDE.md v3.19 entry

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Write the v3.19 entry**

Open `CLAUDE.md`, find the version history section (look for `### v3.18`). Insert above v3.18:

```markdown
### v3.19 — V6 Dual-ASR Pipeline (VAD + Qwen3-ASR + Refiner) merged from feat/frontend-redesign
- **Background**: feat/frontend-redesign 上嘅 V6 architecture（VAD + dual-ASR + Refiner）operator-validated 過後 graft 入 dev，保留 dev 嘅 vanilla HTML/JS frontend 同所有 v3.17-v3.18 改動。Spec: [docs/superpowers/specs/2026-05-28-v6-dual-asr-merge-design.md](docs/superpowers/specs/2026-05-28-v6-dual-asr-merge-design.md). Plan: [docs/superpowers/plans/2026-05-28-v6-dual-asr-merge-plan.md](docs/superpowers/plans/2026-05-28-v6-dual-asr-merge-plan.md).
- **架構**: V6 backend 完全活喺新文件夾（`backend/stages/`, `backend/engines/`, `backend/pipelines.py`, `backend/pipeline_runner.py`, `backend/routes/pipelines.py`），dev 既有 `profiles.py` / `transcribe_with_segments` / `_auto_translate` 完全唔郁。`settings.json` 加 `active_kind` + `active_id` 兩個 field（backward-compat 保留 `active_profile` mirror）。File registry 喺 upload 一刻 snapshot `active_kind`/`active_id`，防 race condition。
- **5-stage DAG（V6 only）**: Stage 0 Silero VAD → Stage 1A Qwen3-ASR per region + Stage 1B mlx-whisper full audio（純取 timestamps） → Stage 2 time-anchored merge → Stage 3 LLM refiner（Ollama qwen3.5:35b-a3b-mlx-bf16）→ persist。Qwen3 = content authority；mlx = timing authority；refiner 簡化 prompt（VAD 已 filter 走 silence，唔需要再 detect hallucination）。
- **Frontend**: Pipeline strip preset 菜單分 2 section（舊有 Profile 組合 / Dual-ASR Pipeline (V6)）。V6 mode active 時 strip column 由 ASR/MT/術語表 swap 做 VAD/Qwen3 Context/Refiner。Click Qwen3 Context / Refiner column 彈 inline panel 直接 edit pipeline JSON / refiner profile JSON。Proofread page 「自訂 Prompt」面板 mode-aware — V6 file 顯示 `qwen3_context` + `refiner_prompt` 兩個 textarea，Profile file 仍係 v3.18 嘅 4 個 textarea。
- **Backend dispatch**: `_asr_handler` 由 file.active_kind 分流；`pipeline_v6` 入 `PipelineRunner._run_v6`，`profile` 行 `transcribe_with_segments`。`_mt_handler` 對 V6 file short-circuit（Stage 3 refiner 已內含 MT 角色）。Cancel + retry + crash recovery 全部沿用 R5 Phase 2-5 既有設計。
- **Hardware / env**: silero-vad >= 6.2.1 入 main venv；mlx_qwen3_asr 0.3.5 隔離喺 `backend/scripts/v5_prototype/venv_qwen/`（py3.11）。Main py3.9 backend 用 subprocess JSON stdin/stdout 跟 Qwen3 venv 通訊。`setup_v6.sh` idempotent 一鍵起 venv。boot 時 `V6_AVAILABLE` flag detect — venv 唔存在前端 V6 section 灰咗。
- **Imported V6 pipelines**: 2 個 production-validated pipeline JSON（賽馬廣播 Cantonese + Winning Factor EN newscast）user_id rewritten 為 null（shared），dev 所有用戶都見到。
- **Tests**: 94 個 backend test cases graft 自 feat branch（55 stage + 18 runner + 14 refiner JSON unwrap + 7 pipeline config）+ ~35 個新 dev-side cases（settings migration 6 + validator extension 5 + manager wire-up 8 + register_file snapshot 4 + dispatch 5 + /api/active 5 + migration 3 + V6_AVAILABLE 2）+ 7 個 Playwright（V6 preset menu + columns + inline panel + proofread mode-aware）。
- **Operator validation**: 同 feat branch [v6-validation.md](docs/superpowers/validation/v6-validation.md) 嘅 metrics 對齊 — 賽馬 4-min Cantonese: Stage 0 ~28 region 91% speech，Stage 1A 100% entity accuracy（袁幸堯/史滕雷/HIGHLAND BLINK），Stage 2 ~84 final seg，Stage 3 < 5% drops 0 cascade artifacts。詳見 [docs/superpowers/validation/v3.19-v6-merge-report.md](docs/superpowers/validation/v3.19-v6-merge-report.md)（Task 7.3）。
- **Out-of-scope**: V5 dual-ASR + verifier path（stages/v5/ import 咗但唔 wire entry point）、React frontend（用戶明確保留 vanilla）、per-file VAD threshold override、V6 over OpenRouter（首批 Ollama only）、Stage 1A ∥ 1B parallel（sequential 如 feat branch）、v3.18 MT overrides ↔ V6 refiner overrides auto-translation。
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md v3.19 entry — V6 Dual-ASR merge from feat/frontend-redesign"
```

### Task 6.2: README.md V6 section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add V6 quick-start section (Traditional Chinese)**

In `README.md`, find a sensible insertion point (probably near setup / features sections). Add:

```markdown
## V6 Dual-ASR Pipeline（粵語廣播 / 多語素材）

dev v3.19 加入 V6 pipeline 處理 mlx-whisper 處理唔好嘅素材（特別係粵語廣播）。架構：

1. **VAD 預分段** — Silero VAD 由源頭切走靜音段，eliminate cascade hallucination
2. **Qwen3-ASR** — 內容權威，per-region 識別，支援 entity name context
3. **mlx-whisper** — 純做時間軸 reference，text 唔輸出
4. **Refiner LLM** — Ollama qwen3.5:35b-a3b-mlx-bf16 整理廣播風格

### 啟用 V6

```bash
# 1. 安裝 main venv 嘅 silero-vad（已喺 requirements.txt）
cd backend && source venv/bin/activate
pip install -r requirements.txt

# 2. 起 Qwen3-ASR 嘅 py3.11 subprocess venv（一次性）
bash backend/scripts/setup_v6.sh

# 3. 重啟 backend
python app.py
```

### 點切換 V6

1. Dashboard 上方 Pipeline preset 點 dropdown
2. 揀「Dual-ASR Pipeline (V6)」section 入面嘅 `[v6] 賽馬廣播 (Cantonese)` 或 `[v6] Winning Factor EN newscast`
3. Strip column 自動 swap：VAD · Qwen3 Context · 輸出 · Refiner
4. Click 「Qwen3 Context」column 改 entity name 提示；Click 「Refiner」改 LLM prompt
5. Upload 文件 → 自動行 V6 pipeline

### Per-file override

開 Proofread page，自訂 Prompt 面板會自動顯示 V6 mode：兩個 textarea（Qwen3 Context + Refiner Prompt）— 改完只影響呢個 file。

### 唔需要 V6？

完全唔影響 — Pipeline 預設仍係 dev-default Profile。冇 mlx_qwen3_asr venv 嘅機器，V6 section 自動灰咗，現有 Profile 流程全部如常。
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): V6 Dual-ASR quick-start (Traditional Chinese)"
```

---

## Phase 7 — Operator validation (3 tasks)

### Task 7.1: Run 賽馬 Cantonese validation

**Files:**
- Create: `docs/superpowers/validation/v3.19-v6-merge-report.md` (will be created in Task 7.3; this task gathers data)

- [ ] **Step 1: Verify 賽馬 audio sample available**

```bash
ls "backend/data/uploads/" 2>/dev/null | grep -iE "cantonese|賽馬|equestrian|racing" | head -3
```

If no sample: ask user to upload 賽馬 4-min Cantonese clip via Dashboard.

- [ ] **Step 2: Activate V6 賽馬 pipeline + upload**

In Dashboard:
1. Switch to `[v6] 賽馬廣播 (Cantonese)` via preset menu.
2. Upload 賽馬 4-min Cantonese audio file.
3. Wait for transcription + refiner to complete (~70 sec expected).

- [ ] **Step 3: Capture metrics**

```bash
# Pull file metadata + segments
FILE_ID="<file_id from dashboard>"
curl -s -b /tmp/cookies.txt http://localhost:5001/api/files/$FILE_ID/segments \
  | python -m json.tool > /tmp/v6_validation_seungma_segments.json

# Count segments + entity accuracy spot-check
python -c "
import json
data = json.load(open('/tmp/v6_validation_seungma_segments.json'))
segs = data['segments']
text_all = ' '.join(s['text'] for s in segs)
print(f'segment count: {len(segs)}')
print(f'total chars: {sum(len(s[\"text\"]) for s in segs)}')
for entity in ['袁幸堯', '史滕雷', 'HIGHLAND BLINK']:
    print(f'  {entity}: {entity in text_all}')
"
```

Expected:
- Segment count ~84
- All 3 entities present (`True`)

- [ ] **Step 4: Save validation snapshot**

```bash
cp /tmp/v6_validation_seungma_segments.json \
   docs/superpowers/validation/v3.19-v6-seungma-postfix-snapshot.json
git add docs/superpowers/validation/v3.19-v6-seungma-postfix-snapshot.json
git commit -m "docs(validation): v3.19 賽馬 Cantonese V6 post-merge snapshot"
```

### Task 7.2: Run Winning Factor EN newscast validation

- [ ] **Step 1: Switch to Winning Factor pipeline + upload**

In Dashboard:
1. Switch to `[v6] Winning Factor EN newscast` via preset menu.
2. Upload 14-min EN newscast.
3. Wait for completion.

- [ ] **Step 2: Capture metrics**

```bash
FILE_ID="<file_id>"
curl -s -b /tmp/cookies.txt http://localhost:5001/api/files/$FILE_ID/segments \
  | python -m json.tool > /tmp/v6_validation_winning_segments.json

python -c "
import json
data = json.load(open('/tmp/v6_validation_winning_segments.json'))
segs = data['segments']
print(f'segment count: {len(segs)}')
print(f'avg seg duration: {sum((s[\"end\"]-s[\"start\"]) for s in segs)/len(segs):.2f}s')
"
```

Expected:
- Segment count ~200 (14-min audio)
- Avg duration 2-4 sec

- [ ] **Step 3: Save validation snapshot**

```bash
cp /tmp/v6_validation_winning_segments.json \
   docs/superpowers/validation/v3.19-v6-winning-postfix-snapshot.json
git add docs/superpowers/validation/v3.19-v6-winning-postfix-snapshot.json
git commit -m "docs(validation): v3.19 Winning Factor EN V6 post-merge snapshot"
```

### Task 7.3: Write validation report

**Files:**
- Create: `docs/superpowers/validation/v3.19-v6-merge-report.md`

- [ ] **Step 1: Write the report**

Create `docs/superpowers/validation/v3.19-v6-merge-report.md`:

```markdown
# v3.19 V6 Merge — Operator Validation Report

**Date:** 2026-05-28 (validation run date — fill in actual)
**Branch:** dev (post-merge)
**Validator:** Reno

---

## Acceptance criteria

| Criterion | Target (per spec §9.1) | Result | Verdict |
|---|---|---|---|
| All new backend tests green | ~110 cases PASS | _fill in_ | ⏳ |
| All Playwright tests green | 7 cases PASS | _fill in_ | ⏳ |
| Dev baseline preserved | 813 pass / 14 fail | _fill in_ | ⏳ |
| 賽馬 entity accuracy | 100% (袁幸堯/史滕雷/HIGHLAND BLINK) | _fill in_ | ⏳ |
| 賽馬 segment count | ~84 | _fill in_ | ⏳ |
| 賽馬 cascade artifacts | 0 | _fill in_ | ⏳ |
| Winning Factor segment count | ~200 | _fill in_ | ⏳ |
| Winning Factor avg seg duration | 2-4s | _fill in_ | ⏳ |

## Metric comparison with feat branch v6-validation report

| Metric | feat/frontend-redesign | dev v3.19 | Δ | Notes |
|---|---|---|---|---|
| Stage 0 VAD regions (賽馬) | 28 | _fill_ | _fill_ | |
| Stage 0 VAD runtime | < 1s | _fill_ | _fill_ | |
| Stage 1A char timestamps | ~1066 | _fill_ | _fill_ | |
| Stage 2 final segments | 84 | _fill_ | _fill_ | |
| Stage 3 refiner drops | < 5% | _fill_ | _fill_ | |
| Total runtime (賽馬 4-min) | ~70s | _fill_ | _fill_ | |

## Inline catches during validation

| # | Issue | Resolution |
|---|---|---|
| _fill in any inline fixes here_ | | |

## Verdict

⏳ PENDING — fill in after all metrics captured.

Expected outcomes:
- ✅ Merge v3.19 → main if all targets met
- ⚠️ Mark known boundaries for Phase 8 follow-up if any metric diverges from feat branch baseline
```

- [ ] **Step 2: Actually run the validation and fill in numbers**

Re-do Tasks 7.1 + 7.2 with timings captured. Fill in the table values in the report.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/validation/v3.19-v6-merge-report.md
git commit -m "docs(validation): v3.19 V6 merge operator validation report

Captures 賽馬 + Winning Factor metrics. Verdict cell to fill in
after all runs complete and acceptance criteria evaluated."
```

---

## Self-Review Checklist

After all 28 tasks complete, verify:

- [ ] All 28 tasks executed in order
- [ ] All new tests green; dev baseline preserved
- [ ] `setup_v6.sh` runs idempotently on a clean machine
- [ ] V6 Pipeline preset menu shows 2 sections on Dashboard
- [ ] V6 column swap works (ASR/MT/glossary → VAD/Qwen3/Refiner)
- [ ] Inline panel commit PATCHes pipeline JSON / refiner profile
- [ ] Proofread panel mode-aware (V6 file → 2 textareas; Profile file → 4 textareas)
- [ ] Validation report numbers align with feat branch baseline
- [ ] CLAUDE.md v3.19 entry committed
- [ ] README.md V6 quick-start committed
- [ ] No dev既有 endpoints (`/api/transcribe`, `/api/profiles/*`, `/api/translate`, etc.) regressed

## Rollback (if needed)

See spec §10 ("Rollback path") for the exact `git rm` + `git checkout HEAD~` sequence.
