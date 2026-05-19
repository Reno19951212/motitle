# v5-A1 Schema + Engine ABCs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land v5 pipeline schema, 5 engine ABCs (LLMEngine / TranscribeEngine / TranslatorEngine / RefinerEngine / VerifierEngine), 5 profile manager classes, REST endpoints, and v4→v5 auto-promote — without touching pipeline_runner or frontend.

**Architecture:** Parallel module structure under `backend/engines/{llm,transcribe,translator,refiner,verifier}/` for v5 engine abstractions. Existing v4 `backend/asr/` + `backend/translation/` continue to serve v4 pipelines unchanged during A1. New `backend/{transcribe,translator,refiner,verifier,llm}_profiles.py` manager modules follow the v4 P1 pattern (per-resource lock + TOCTOU `update_if_owned` / `delete_if_owned`). Pipeline schema v5 adds `version: 5` field + new sections; v4 pipelines auto-promote at read time. No stage executor changes (deferred to A2).

**Tech Stack:** Python 3.9 (main backend venv) + Python 3.11 (Qwen3-ASR subprocess via `backend/scripts/v5_prototype/venv_qwen`); Flask Blueprint pattern; pytest + pytest-mock; OpenCC s2hk for Qwen3 simplified→traditional output; Ollama HTTP API (LLM backend); mlx-qwen3-asr 0.3.5 (subprocess invocation).

**Validation reference:** Default engine prompts seed from working prototype at `backend/scripts/v5_prototype/prompts.py` + `verifier_prompt.py`. Engine semantics validated empirically — see [spec §10](../specs/2026-05-19-v5-dual-asr-refiner-translator-design.md#10-validation-evidence-from-prototype).

---

## File Structure

### New files (created by this plan)

| Path | Responsibility |
|---|---|
| `backend/llm_profiles.py` | LLMProfile manager (backend config: model, base_url, api_key, defaults) |
| `backend/transcribe_profiles.py` | TranscribeProfile manager (wraps v4 ASR profile + adds qwen3-asr engine) |
| `backend/translator_profiles.py` | TranslatorProfile manager (cross-lingual prompt + glossary + LLM backend ref) |
| `backend/refiner_profiles.py` | RefinerProfile manager (same-lingual polish; narrows v4 MT profile) |
| `backend/verifier_profiles.py` | VerifierProfile manager (LLM-as-judge config) |
| `backend/pipeline_schema_v5.py` | v5 schema validator + `promote_v4_to_v5` + cascade ref check |
| `backend/routes/llm_profiles.py` | REST blueprint for `/api/llm_profiles` |
| `backend/routes/transcribe_profiles.py` | REST blueprint for `/api/transcribe_profiles` |
| `backend/routes/translator_profiles.py` | REST blueprint for `/api/translator_profiles` (NEW) |
| `backend/routes/refiner_profiles.py` | REST blueprint for `/api/refiner_profiles` |
| `backend/routes/verifier_profiles.py` | REST blueprint for `/api/verifier_profiles` (NEW) |
| `backend/engines/__init__.py` | Re-export of all engine ABCs |
| `backend/engines/llm/__init__.py` | LLMEngine ABC + factory |
| `backend/engines/llm/ollama.py` | OllamaLLM concrete |
| `backend/engines/llm/openrouter.py` | OpenRouterLLM concrete |
| `backend/engines/transcribe/__init__.py` | TranscribeEngine ABC + factory (delegates to existing `backend/asr/` for Whisper) |
| `backend/engines/transcribe/qwen3_asr.py` | Qwen3AsrTranscribeEngine — main process side (py3.9) |
| `backend/engines/transcribe/qwen3_subprocess.py` | Subprocess entry script (py3.11 venv) |
| `backend/engines/translator/__init__.py` | TranslatorEngine ABC + factory |
| `backend/engines/translator/llm_translator.py` | LLMTranslator concrete + prompt registry |
| `backend/engines/refiner/__init__.py` | RefinerEngine ABC + factory |
| `backend/engines/refiner/llm_refiner.py` | LLMRefiner concrete + prompt registry |
| `backend/engines/verifier/__init__.py` | VerifierEngine ABC + factory |
| `backend/engines/verifier/llm_verifier.py` | LLMVerifier concrete + alignment helper |
| `backend/config/prompt_templates_v5/translator/zh_to_en_default.json` | Default ZH→EN prompt (from prototype) |
| `backend/config/prompt_templates_v5/translator/en_to_zh_hk_default.json` | Default EN→ZH HK prompt |
| `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json` | Default ZH broadcast HK refiner |
| `backend/config/prompt_templates_v5/refiner/en_newscast_default.json` | Default EN newscast refiner |
| `backend/config/prompt_templates_v5/verifier/zh_default.json` | Default ZH verifier prompt |
| `backend/config/prompt_templates_v5/verifier/en_default.json` | Default EN verifier prompt |
| `backend/tests/test_v5_pipeline_schema.py` | Pipeline schema v5 + promote tests |
| `backend/tests/test_v5_profile_managers.py` | All 5 profile manager tests |
| `backend/tests/test_v5_profile_routes.py` | All 5 REST blueprint tests |
| `backend/tests/test_v5_llm_engine.py` | LLMEngine + OllamaLLM + OpenRouterLLM tests |
| `backend/tests/test_v5_transcribe_engine.py` | TranscribeEngine + Qwen3 wrapper tests |
| `backend/tests/test_v5_translator_engine.py` | TranslatorEngine + LLMTranslator tests |
| `backend/tests/test_v5_refiner_engine.py` | RefinerEngine + LLMRefiner tests |
| `backend/tests/test_v5_verifier_engine.py` | VerifierEngine + LLMVerifier + alignment tests |

### Modified files

| Path | Change |
|---|---|
| `backend/pipelines.py:1-end` | Import `pipeline_schema_v5`; read path branches by `version` field; add `version: 5` validator path |
| `backend/routes/pipelines.py` | Accept v5 pipeline JSON; reuse cascade ref check from `pipeline_schema_v5` |
| `backend/asr/__init__.py` | Add alias `TranscribeEngine = ASREngine` for v5 import path; keep ASREngine for v4 backward compat |
| `backend/asr_profiles.py:1` | Add `qwen3-asr` to `VALID_ENGINES` set (so v4 ASR profile can also reference Qwen3 if user wants) |
| `backend/routes/asr_profiles.py` | Add `Deprecation` header with `Sunset` date pointing at v5-A3 |
| `backend/routes/mt_profiles.py` | Add `Deprecation` header pointing at `/api/refiner_profiles` |
| `backend/bootstrap.py` | Register 5 new blueprints (llm_profiles, transcribe_profiles, translator_profiles, refiner_profiles, verifier_profiles) |
| `backend/managers.py` | Wire 5 new manager instances at boot |
| `CLAUDE.md` | Add v5-A1 progress entry to "Completed Features" |
| `backend/scripts/v5_prototype/.gitignore` | (No change — already committed) |

### Files NOT touched in A1 (deferred to A2 / A3)

- `backend/pipeline_runner.py` — A2
- `backend/stages/*.py` — A2
- `backend/translation/ollama_engine.py` etc. — A2 (v4 path stays untouched)
- `frontend/**` — A3

---

## Task index

| # | Task | Phase |
|---|---|---|
| T1 | v5 Pipeline schema validator + `promote_v4_to_v5` | 1 — Schema |
| T2 | Cascade ref check for v5 schema | 1 — Schema |
| T3 | LLMProfile manager + validator + tests | 2 — Profiles |
| T4 | LLMProfile REST blueprint | 2 — Profiles |
| T5 | TranscribeProfile manager (add qwen3-asr engine support) | 2 — Profiles |
| T6 | TranscribeProfile REST blueprint + backward-compat alias on `/api/asr_profiles` | 2 — Profiles |
| T7 | TranslatorProfile manager + validator + tests (NEW) | 2 — Profiles |
| T8 | TranslatorProfile REST blueprint | 2 — Profiles |
| T9 | RefinerProfile manager (rename of MT, narrow semantics) | 2 — Profiles |
| T10 | RefinerProfile REST blueprint + backward-compat alias on `/api/mt_profiles` | 2 — Profiles |
| T11 | VerifierProfile manager + validator (NEW) | 2 — Profiles |
| T12 | VerifierProfile REST blueprint | 2 — Profiles |
| T13 | LLMEngine ABC + OllamaLLM concrete + tests | 3 — LLM Layer |
| T14 | OpenRouterLLM concrete + tests | 3 — LLM Layer |
| T15 | TranscribeEngine ABC alias + factory | 4 — Transcribe |
| T16 | Qwen3-ASR subprocess runner (py3.11 entry script) | 4 — Transcribe |
| T17 | Qwen3AsrTranscribeEngine wrapper (py3.9) + tests | 4 — Transcribe |
| T18 | Default translator prompts (JSON templates) | 5 — Translator/Refiner/Verifier |
| T19 | TranslatorEngine ABC + LLMTranslator concrete + tests | 5 |
| T20 | Default refiner prompts (JSON templates) | 5 |
| T21 | RefinerEngine ABC + LLMRefiner concrete + tests | 5 |
| T22 | Default verifier prompts (JSON templates) | 5 |
| T23 | VerifierEngine ABC + LLMVerifier + alignment helper + tests | 5 |
| T24 | Pipeline manager loads v5 schema (no execution) | 6 — Pipeline Integration |
| T25 | `/api/pipelines` accepts v5 JSON + cascade refs validate against new profiles | 6 |
| T26 | Bootstrap wires 5 new blueprints + manager singletons | 6 |
| T27 | End-to-end schema load smoke test (v5 JSON → all stages instantiable) | 7 — Integration |
| T28 | Update CLAUDE.md v5-A1 progress entry | 7 — Docs |

---

## Phase 1 — Schema Foundation

### Task 1: v5 Pipeline schema validator + `promote_v4_to_v5`

**Files:**
- Create: `backend/pipeline_schema_v5.py`
- Test: `backend/tests/test_v5_pipeline_schema.py`

- [ ] **Step 1: Write failing test for v5 schema validation (valid case)**

Add to `backend/tests/test_v5_pipeline_schema.py`:
```python
import pytest
from backend.pipeline_schema_v5 import validate_v5_pipeline, promote_v4_to_v5


def test_validate_v5_minimal_valid():
    data = {
        "id": "p1",
        "name": "test",
        "version": 5,
        "user_id": 1,
        "shared": False,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "asr_secondary": None,
        "asr_verifier": None,
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "translators": {},
        "glossary_stages": {},
        "font_config": {"family": "Noto Sans TC", "color": "white", "outline_color": "black"},
    }
    errors = validate_v5_pipeline(data)
    assert errors == [], f"unexpected errors: {errors}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source venv/bin/activate
pytest tests/test_v5_pipeline_schema.py::test_validate_v5_minimal_valid -v
```
Expected: `ModuleNotFoundError: backend.pipeline_schema_v5`

- [ ] **Step 3: Create minimal `pipeline_schema_v5.py`**

```python
"""v5 pipeline schema validator + v4→v5 auto-promote."""
from typing import Any

VALID_LANGS = {"en", "zh", "ja", "ko", "yue", "fr", "de", "es", "th"}


def validate_v5_pipeline(data: Any) -> list[str]:
    """Return list of error strings; empty = valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["payload must be an object"]
    if data.get("version") != 5:
        errors.append("version must be 5")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        errors.append("name required (string)")
    primary = data.get("asr_primary")
    if not isinstance(primary, dict):
        errors.append("asr_primary required (object)")
    else:
        if not primary.get("transcribe_profile_id"):
            errors.append("asr_primary.transcribe_profile_id required")
        if primary.get("source_lang") not in VALID_LANGS:
            errors.append(f"asr_primary.source_lang must be in {sorted(VALID_LANGS)}")
    targets = data.get("target_languages")
    if not isinstance(targets, list) or not targets:
        errors.append("target_languages required (non-empty list)")
    else:
        for t in targets:
            if t not in VALID_LANGS:
                errors.append(f"target_languages contains invalid lang: {t}")
    refinements = data.get("refinements")
    if not isinstance(refinements, dict):
        errors.append("refinements required (object)")
    font = data.get("font_config")
    if not isinstance(font, dict):
        errors.append("font_config required (object)")
    elif not all(isinstance(font.get(k), str) and font.get(k) for k in ("family", "color", "outline_color")):
        errors.append("font_config.family / color / outline_color required (strings)")
    return errors


def promote_v4_to_v5(v4: dict) -> dict:
    """Map v4 pipeline JSON shape to v5 shape. Preserves semantics."""
    source_lang = (v4.get("asr_profile") or {}).get("language", "en")
    target_lang = source_lang  # v4 conflated source/target; assume same after promote
    refiner_entries = [
        {"refiner_profile_id": mt_id}
        for mt_id in v4.get("mt_stages", [])
    ]
    return {
        "id": v4["id"],
        "name": v4["name"],
        "version": 5,
        "user_id": v4.get("user_id"),
        "shared": v4.get("shared", False),
        "asr_primary": {
            "transcribe_profile_id": v4["asr_profile_id"],
            "source_lang": source_lang,
        },
        "asr_secondary": None,
        "asr_verifier": None,
        "target_languages": [target_lang],
        "refinements": {target_lang: refiner_entries},
        "translators": {},
        "glossary_stages": {
            target_lang: (v4.get("glossary_stage") or {}).get("glossary_ids", [])
        },
        "font_config": v4.get("font_config", {
            "family": "Noto Sans TC",
            "color": "white",
            "outline_color": "black",
        }),
    }
```

- [ ] **Step 4: Run test to verify pass**

```bash
pytest tests/test_v5_pipeline_schema.py::test_validate_v5_minimal_valid -v
```
Expected: PASS

- [ ] **Step 5: Add tests for invalid cases**

Append to `backend/tests/test_v5_pipeline_schema.py`:
```python
def test_validate_v5_missing_version():
    errors = validate_v5_pipeline({"name": "x"})
    assert "version must be 5" in errors

def test_validate_v5_invalid_source_lang():
    data = {"version": 5, "name": "x", "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "klingon"}}
    errors = validate_v5_pipeline(data)
    assert any("source_lang" in e for e in errors)

def test_validate_v5_empty_target_languages():
    data = {"version": 5, "name": "x", "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "zh"},
            "target_languages": [], "refinements": {}, "font_config": {"family": "f", "color": "w", "outline_color": "b"}}
    errors = validate_v5_pipeline(data)
    assert any("target_languages" in e for e in errors)

def test_validate_v5_missing_font():
    data = {"version": 5, "name": "x", "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "zh"},
            "target_languages": ["zh"], "refinements": {"zh": []}}
    errors = validate_v5_pipeline(data)
    assert any("font_config" in e for e in errors)
```

- [ ] **Step 6: Run all invalid-case tests**

```bash
pytest tests/test_v5_pipeline_schema.py -v -k validate
```
Expected: 5 PASS

- [ ] **Step 7: Add test for `promote_v4_to_v5`**

Append:
```python
def test_promote_v4_to_v5_minimal():
    v4 = {
        "id": "p4",
        "name": "v4 pipeline",
        "user_id": 1,
        "asr_profile_id": "asr1",
        "asr_profile": {"language": "zh"},
        "mt_stages": ["mt1", "mt2"],
        "glossary_stage": {"glossary_ids": ["g1"]},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    v5 = promote_v4_to_v5(v4)
    assert v5["version"] == 5
    assert v5["asr_primary"]["transcribe_profile_id"] == "asr1"
    assert v5["asr_primary"]["source_lang"] == "zh"
    assert v5["target_languages"] == ["zh"]
    assert len(v5["refinements"]["zh"]) == 2
    assert v5["refinements"]["zh"][0]["refiner_profile_id"] == "mt1"
    assert v5["glossary_stages"]["zh"] == ["g1"]
    # Validator must accept the promoted result
    assert validate_v5_pipeline(v5) == []
```

- [ ] **Step 8: Run promote test**

```bash
pytest tests/test_v5_pipeline_schema.py::test_promote_v4_to_v5_minimal -v
```
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/pipeline_schema_v5.py backend/tests/test_v5_pipeline_schema.py
git commit -m "feat(v5-a1): v5 pipeline schema validator + promote_v4_to_v5"
```

---

### Task 2: Cascade ref check for v5 schema

**Files:**
- Modify: `backend/pipeline_schema_v5.py`
- Test: `backend/tests/test_v5_pipeline_schema.py`

- [ ] **Step 1: Add failing test for cascade ref check**

Append to `test_v5_pipeline_schema.py`:
```python
def test_check_cascade_refs_unknown_transcribe_profile():
    from backend.pipeline_schema_v5 import check_cascade_refs
    pipeline = {
        "version": 5,
        "asr_primary": {"transcribe_profile_id": "missing", "source_lang": "zh"},
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "translators": {},
        "glossary_stages": {},
    }
    refs = {
        "transcribe": {"tp_existing"},
        "translator": set(),
        "refiner": set(),
        "verifier": set(),
        "glossary": set(),
        "llm": set(),
    }
    broken = check_cascade_refs(pipeline, refs)
    assert "asr_primary.transcribe_profile_id" in broken

def test_check_cascade_refs_all_present():
    from backend.pipeline_schema_v5 import check_cascade_refs
    pipeline = {
        "version": 5,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "asr_secondary": {"transcribe_profile_id": "tp2", "source_lang": "zh"},
        "asr_verifier": {"llm_profile_id": "llm1", "prompt_template_id": "v_zh_default"},
        "target_languages": ["zh", "en"],
        "refinements": {"zh": [{"refiner_profile_id": "rp1"}], "en": []},
        "translators": {"en": {"translator_profile_id": "tr1"}},
        "glossary_stages": {"zh": ["g1"], "zh_to_en": ["g2"]},
    }
    refs = {
        "transcribe": {"tp1", "tp2"},
        "translator": {"tr1"},
        "refiner": {"rp1"},
        "verifier": set(),  # verifier uses LLMProfile, not a verifier profile id
        "glossary": {"g1", "g2"},
        "llm": {"llm1"},
    }
    broken = check_cascade_refs(pipeline, refs)
    assert broken == [], f"unexpected broken refs: {broken}"
```

- [ ] **Step 2: Run test to verify fail**

```bash
pytest tests/test_v5_pipeline_schema.py -v -k check_cascade
```
Expected: FAIL (`check_cascade_refs` not defined)

- [ ] **Step 3: Implement `check_cascade_refs`**

Append to `backend/pipeline_schema_v5.py`:
```python
def check_cascade_refs(pipeline: dict, known_refs: dict[str, set[str]]) -> list[str]:
    """Return list of `field.path` strings whose ID isn't in the matching known_refs set.

    known_refs keys: 'transcribe', 'translator', 'refiner', 'verifier', 'glossary', 'llm'.
    """
    broken: list[str] = []

    primary = pipeline.get("asr_primary") or {}
    if primary.get("transcribe_profile_id") and primary["transcribe_profile_id"] not in known_refs.get("transcribe", set()):
        broken.append("asr_primary.transcribe_profile_id")

    secondary = pipeline.get("asr_secondary")
    if secondary and secondary.get("transcribe_profile_id") and secondary["transcribe_profile_id"] not in known_refs.get("transcribe", set()):
        broken.append("asr_secondary.transcribe_profile_id")

    verifier = pipeline.get("asr_verifier")
    if verifier and verifier.get("llm_profile_id") and verifier["llm_profile_id"] not in known_refs.get("llm", set()):
        broken.append("asr_verifier.llm_profile_id")

    for lang, refiner_list in (pipeline.get("refinements") or {}).items():
        for i, entry in enumerate(refiner_list):
            rp = entry.get("refiner_profile_id")
            if rp and rp not in known_refs.get("refiner", set()):
                broken.append(f"refinements.{lang}[{i}].refiner_profile_id")

    for lang, t in (pipeline.get("translators") or {}).items():
        tr = t.get("translator_profile_id")
        if tr and tr not in known_refs.get("translator", set()):
            broken.append(f"translators.{lang}.translator_profile_id")

    for key, glossaries in (pipeline.get("glossary_stages") or {}).items():
        for i, g in enumerate(glossaries):
            if g and g not in known_refs.get("glossary", set()):
                broken.append(f"glossary_stages.{key}[{i}]")

    return broken
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_pipeline_schema.py -v -k check_cascade
```
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline_schema_v5.py backend/tests/test_v5_pipeline_schema.py
git commit -m "feat(v5-a1): cascade ref check for v5 pipeline schema"
```

---

## Phase 2 — Profile Managers

### Task 3: LLMProfile manager + validator + tests

**Files:**
- Create: `backend/llm_profiles.py`
- Test: `backend/tests/test_v5_profile_managers.py`

- [ ] **Step 1: Write failing test for LLM profile creation**

Create `backend/tests/test_v5_profile_managers.py`:
```python
import pytest
import tempfile
from pathlib import Path
from backend.llm_profiles import LLMProfileManager, validate_llm_profile


def test_validate_llm_profile_minimal():
    data = {
        "name": "Ollama Qwen3.5",
        "backend": "ollama",
        "model": "qwen3.5:35b-a3b-mlx-bf16",
        "base_url": "http://localhost:11434",
        "temperature": 0.2,
    }
    assert validate_llm_profile(data) == []


def test_validate_llm_profile_missing_backend():
    data = {"name": "x", "model": "m", "base_url": "http://localhost"}
    errors = validate_llm_profile(data)
    assert any("backend" in e for e in errors)


def test_llm_profile_manager_create_then_get(tmp_path):
    mgr = LLMProfileManager(tmp_path)
    pid = mgr.create({
        "name": "Test Ollama",
        "backend": "ollama",
        "model": "qwen3.5:9b",
        "base_url": "http://localhost:11434",
    }, user_id=1)
    profile = mgr.get(pid)
    assert profile["name"] == "Test Ollama"
    assert profile["user_id"] == 1
```

- [ ] **Step 2: Run test to verify fail**

```bash
pytest tests/test_v5_profile_managers.py::test_validate_llm_profile_minimal -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Create `backend/llm_profiles.py`** (mirroring `backend/asr_profiles.py` structure)

```python
"""LLM Profile manager — v5-A1.

Stores LLM backend config (Ollama / OpenRouter / Claude) as standalone
profiles that Translator / Refiner / Verifier engines reference via
`llm_profile_id`.
"""
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

VALID_BACKENDS = {"ollama", "openrouter", "claude"}
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


def validate_llm_profile(data: Any) -> list:
    errors: list = []
    if not isinstance(data, dict):
        return ["payload must be object"]
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name required")
    elif len(name) > MAX_NAME_CHARS:
        errors.append(f"name max {MAX_NAME_CHARS} chars")
    if data.get("backend") not in VALID_BACKENDS:
        errors.append(f"backend must be in {sorted(VALID_BACKENDS)}")
    if not isinstance(data.get("model"), str) or not data["model"].strip():
        errors.append("model required (string)")
    if not isinstance(data.get("base_url"), str) or not data["base_url"].startswith(("http://", "https://")):
        errors.append("base_url required (must start with http:// or https://)")
    temp = data.get("temperature", 0.2)
    if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
        errors.append("temperature must be number 0..2")
    return errors


class LLMProfileManager:
    def __init__(self, config_dir: Path):
        self.dir = Path(config_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self, data: dict, *, user_id: int) -> str:
        errors = validate_llm_profile(data)
        if errors:
            raise ValueError("; ".join(errors))
        pid = str(uuid.uuid4())
        payload = {**data, "id": pid, "user_id": user_id, "created_at": time.time()}
        path = self.dir / f"{pid}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return pid

    def get(self, pid: str) -> Optional[dict]:
        path = self.dir / f"{pid}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_visible(self, user_id: int, is_admin: bool) -> list[dict]:
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

    def update_if_owned(self, pid: str, user_id: int, is_admin: bool, patch: dict) -> Optional[dict]:
        with _res_lock(pid):
            p = self.get(pid)
            if p is None or not (is_admin or p.get("user_id") == user_id):
                return None
            merged = {**p, **patch}
            errors = validate_llm_profile(merged)
            if errors:
                raise ValueError("; ".join(errors))
            (self.dir / f"{pid}.json").write_text(
                json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            return merged

    def delete_if_owned(self, pid: str, user_id: int, is_admin: bool) -> bool:
        with _res_lock(pid):
            p = self.get(pid)
            if p is None or not (is_admin or p.get("user_id") == user_id):
                return False
            (self.dir / f"{pid}.json").unlink()
            return True
```

- [ ] **Step 4: Run all LLMProfile tests**

```bash
pytest tests/test_v5_profile_managers.py -v -k llm
```
Expected: 3 PASS

- [ ] **Step 5: Add update + delete + visibility tests**

Append:
```python
def test_llm_profile_update_if_owned(tmp_path):
    mgr = LLMProfileManager(tmp_path)
    pid = mgr.create({
        "name": "n1", "backend": "ollama", "model": "m", "base_url": "http://x",
    }, user_id=1)
    updated = mgr.update_if_owned(pid, user_id=1, is_admin=False, patch={"name": "n2"})
    assert updated["name"] == "n2"
    # Non-owner cannot update
    blocked = mgr.update_if_owned(pid, user_id=2, is_admin=False, patch={"name": "x"})
    assert blocked is None


def test_llm_profile_delete_if_owned(tmp_path):
    mgr = LLMProfileManager(tmp_path)
    pid = mgr.create({
        "name": "n", "backend": "ollama", "model": "m", "base_url": "http://x",
    }, user_id=1)
    # Non-owner cannot delete
    assert mgr.delete_if_owned(pid, user_id=2, is_admin=False) is False
    # Owner can
    assert mgr.delete_if_owned(pid, user_id=1, is_admin=False) is True
    assert mgr.get(pid) is None
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_v5_profile_managers.py -v -k llm
```
Expected: 5 PASS

- [ ] **Step 7: Commit**

```bash
git add backend/llm_profiles.py backend/tests/test_v5_profile_managers.py
git commit -m "feat(v5-a1): LLMProfile manager + validator"
```

---

### Task 4: LLMProfile REST blueprint

**Files:**
- Create: `backend/routes/llm_profiles.py`
- Test: `backend/tests/test_v5_profile_routes.py`

- [ ] **Step 1: Write failing test for list endpoint**

Create `backend/tests/test_v5_profile_routes.py`:
```python
import pytest
from flask import Flask
from backend.routes.llm_profiles import bp as llm_bp


def test_llm_profiles_list_empty(monkeypatch, tmp_path):
    """List should return [] for new user."""
    import app as _app
    from backend.llm_profiles import LLMProfileManager
    mgr = LLMProfileManager(tmp_path)
    monkeypatch.setattr(_app, "_llm_profile_manager", mgr, raising=False)

    app = Flask(__name__)
    app.register_blueprint(llm_bp)
    # Stub login decorator for test
    monkeypatch.setattr("flask_login.current_user", type("U", (), {"id": 1, "is_admin": False})())

    client = app.test_client()
    with app.test_request_context():
        resp = client.get("/api/llm_profiles")
    assert resp.status_code == 200
    assert resp.json == {"profiles": []}
```

- [ ] **Step 2: Run test to verify fail**

```bash
pytest tests/test_v5_profile_routes.py::test_llm_profiles_list_empty -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Create `backend/routes/llm_profiles.py`** (mirror `backend/routes/asr_profiles.py`)

```python
"""LLM Profile REST blueprint — v5-A1."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

import app as _app
from backend.llm_profiles import validate_llm_profile

bp = Blueprint("llm_profiles", __name__)


@bp.get("/api/llm_profiles")
@login_required
def list_profiles():
    mgr = _app._llm_profile_manager
    profiles = mgr.list_visible(user_id=current_user.id, is_admin=getattr(current_user, "is_admin", False))
    return jsonify({"profiles": profiles}), 200


@bp.post("/api/llm_profiles")
@login_required
def create_profile():
    data = request.get_json(silent=True) or {}
    errors = validate_llm_profile(data)
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400
    mgr = _app._llm_profile_manager
    pid = mgr.create(data, user_id=current_user.id)
    return jsonify(mgr.get(pid)), 201


@bp.get("/api/llm_profiles/<pid>")
@login_required
def get_profile(pid):
    mgr = _app._llm_profile_manager
    p = mgr.get(pid)
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not (getattr(current_user, "is_admin", False) or p.get("user_id") == current_user.id or p.get("shared")):
        return jsonify({"error": "forbidden"}), 403
    return jsonify(p), 200


@bp.patch("/api/llm_profiles/<pid>")
@login_required
def update_profile(pid):
    patch = request.get_json(silent=True) or {}
    mgr = _app._llm_profile_manager
    try:
        result = mgr.update_if_owned(pid, current_user.id, getattr(current_user, "is_admin", False), patch)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if result is None:
        return jsonify({"error": "forbidden"}), 403
    return jsonify(result), 200


@bp.delete("/api/llm_profiles/<pid>")
@login_required
def delete_profile(pid):
    mgr = _app._llm_profile_manager
    ok = mgr.delete_if_owned(pid, current_user.id, getattr(current_user, "is_admin", False))
    if not ok:
        return jsonify({"error": "forbidden or missing"}), 403
    return jsonify({"deleted": pid}), 200
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_v5_profile_routes.py::test_llm_profiles_list_empty -v
```
Expected: PASS

- [ ] **Step 5: Add tests for create + get + 404 + 403**

Append:
```python
def test_llm_profiles_create_then_get(monkeypatch, tmp_path):
    import app as _app
    from backend.llm_profiles import LLMProfileManager
    mgr = LLMProfileManager(tmp_path)
    monkeypatch.setattr(_app, "_llm_profile_manager", mgr, raising=False)

    app = Flask(__name__)
    app.register_blueprint(llm_bp)
    monkeypatch.setattr("flask_login.current_user",
                        type("U", (), {"id": 1, "is_admin": False})())

    client = app.test_client()
    resp = client.post("/api/llm_profiles", json={
        "name": "test", "backend": "ollama", "model": "m", "base_url": "http://x",
    })
    assert resp.status_code == 201
    pid = resp.json["id"]
    resp2 = client.get(f"/api/llm_profiles/{pid}")
    assert resp2.status_code == 200
    assert resp2.json["name"] == "test"


def test_llm_profiles_404(monkeypatch, tmp_path):
    import app as _app
    from backend.llm_profiles import LLMProfileManager
    monkeypatch.setattr(_app, "_llm_profile_manager", LLMProfileManager(tmp_path), raising=False)
    app = Flask(__name__)
    app.register_blueprint(llm_bp)
    monkeypatch.setattr("flask_login.current_user",
                        type("U", (), {"id": 1, "is_admin": False})())
    client = app.test_client()
    resp = client.get("/api/llm_profiles/missing")
    assert resp.status_code == 404
```

- [ ] **Step 6: Run all LLM route tests**

```bash
pytest tests/test_v5_profile_routes.py -v -k llm
```
Expected: 3 PASS

- [ ] **Step 7: Commit**

```bash
git add backend/routes/llm_profiles.py backend/tests/test_v5_profile_routes.py
git commit -m "feat(v5-a1): LLMProfile REST blueprint"
```

---

### Task 5: TranscribeProfile manager (add qwen3-asr engine support)

**Files:**
- Create: `backend/transcribe_profiles.py`
- Modify: `backend/asr_profiles.py:VALID_ENGINES` set
- Test: `backend/tests/test_v5_profile_managers.py`

- [ ] **Step 1: Write failing test for `qwen3-asr` engine acceptance**

Append to `backend/tests/test_v5_profile_managers.py`:
```python
def test_transcribe_profile_accepts_qwen3_asr(tmp_path):
    from backend.transcribe_profiles import TranscribeProfileManager
    mgr = TranscribeProfileManager(tmp_path)
    pid = mgr.create({
        "name": "Qwen3-ASR 1.7B",
        "engine": "qwen3-asr",
        "model_size": "1.7B",
        "language": "zh",
    }, user_id=1)
    p = mgr.get(pid)
    assert p["engine"] == "qwen3-asr"
    assert p["model_size"] == "1.7B"


def test_transcribe_profile_accepts_whisper(tmp_path):
    from backend.transcribe_profiles import TranscribeProfileManager
    mgr = TranscribeProfileManager(tmp_path)
    pid = mgr.create({
        "name": "Whisper L3",
        "engine": "whisper",
        "model_size": "large-v3",
        "language": "en",
    }, user_id=1)
    assert mgr.get(pid)["engine"] == "whisper"
```

- [ ] **Step 2: Run test to verify fail**

```bash
pytest tests/test_v5_profile_managers.py::test_transcribe_profile_accepts_qwen3_asr -v
```
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Create `backend/transcribe_profiles.py`**

```python
"""TranscribeProfile manager — v5-A1.

Supersedes ASRProfile (backend/asr_profiles.py). Adds support for
`qwen3-asr` engine. Field shape is a superset of v4 ASR profile.
"""
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

VALID_ENGINES = {"whisper", "mlx-whisper", "qwen3-asr"}
VALID_LANGUAGES = {"en", "zh", "ja", "ko", "yue", "fr", "de", "es", "th", "auto"}
MAX_NAME_CHARS = 64
MAX_INITIAL_PROMPT_CHARS = 512

_LOCK = threading.Lock()
_RES_LOCKS: dict = {}


def _res_lock(rid: str) -> threading.Lock:
    with _LOCK:
        lock = _RES_LOCKS.get(rid)
        if lock is None:
            lock = threading.Lock()
            _RES_LOCKS[rid] = lock
        return lock


def validate_transcribe_profile(data: Any) -> list:
    errors: list = []
    if not isinstance(data, dict):
        return ["payload must be object"]
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name required")
    engine = data.get("engine")
    if engine not in VALID_ENGINES:
        errors.append(f"engine must be in {sorted(VALID_ENGINES)}")
    lang = data.get("language", "auto")
    if lang not in VALID_LANGUAGES:
        errors.append(f"language must be in {sorted(VALID_LANGUAGES)}")
    ip = data.get("initial_prompt", "")
    if ip and (not isinstance(ip, str) or len(ip) > MAX_INITIAL_PROMPT_CHARS):
        errors.append(f"initial_prompt max {MAX_INITIAL_PROMPT_CHARS} chars")
    return errors


class TranscribeProfileManager:
    def __init__(self, config_dir: Path):
        self.dir = Path(config_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self, data: dict, *, user_id: int) -> str:
        errors = validate_transcribe_profile(data)
        if errors:
            raise ValueError("; ".join(errors))
        pid = str(uuid.uuid4())
        payload = {**data, "id": pid, "user_id": user_id, "created_at": time.time()}
        (self.dir / f"{pid}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return pid

    def get(self, pid: str) -> Optional[dict]:
        path = self.dir / f"{pid}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_visible(self, user_id: int, is_admin: bool) -> list[dict]:
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

    def update_if_owned(self, pid: str, user_id: int, is_admin: bool, patch: dict) -> Optional[dict]:
        with _res_lock(pid):
            p = self.get(pid)
            if p is None or not (is_admin or p.get("user_id") == user_id):
                return None
            merged = {**p, **patch}
            errors = validate_transcribe_profile(merged)
            if errors:
                raise ValueError("; ".join(errors))
            (self.dir / f"{pid}.json").write_text(
                json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            return merged

    def delete_if_owned(self, pid: str, user_id: int, is_admin: bool) -> bool:
        with _res_lock(pid):
            p = self.get(pid)
            if p is None or not (is_admin or p.get("user_id") == user_id):
                return False
            (self.dir / f"{pid}.json").unlink()
            return True
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_profile_managers.py -v -k transcribe
```
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/transcribe_profiles.py backend/tests/test_v5_profile_managers.py
git commit -m "feat(v5-a1): TranscribeProfile manager with qwen3-asr engine"
```

---

### Task 6: TranscribeProfile REST blueprint + backward-compat alias

**Files:**
- Create: `backend/routes/transcribe_profiles.py`
- Modify: `backend/routes/asr_profiles.py` (add Deprecation header)
- Test: `backend/tests/test_v5_profile_routes.py`

- [ ] **Step 1: Write failing test for transcribe_profiles REST + alias**

Append to `backend/tests/test_v5_profile_routes.py`:
```python
def test_transcribe_profiles_create_get(monkeypatch, tmp_path):
    from flask import Flask
    from backend.routes.transcribe_profiles import bp as tr_bp
    from backend.transcribe_profiles import TranscribeProfileManager
    import app as _app
    mgr = TranscribeProfileManager(tmp_path)
    monkeypatch.setattr(_app, "_transcribe_profile_manager", mgr, raising=False)
    app = Flask(__name__)
    app.register_blueprint(tr_bp)
    monkeypatch.setattr("flask_login.current_user",
                        type("U", (), {"id": 1, "is_admin": False})())
    client = app.test_client()
    resp = client.post("/api/transcribe_profiles", json={
        "name": "qwen3", "engine": "qwen3-asr", "language": "zh"
    })
    assert resp.status_code == 201


def test_asr_profiles_returns_deprecation_header(monkeypatch, tmp_path):
    """Legacy /api/asr_profiles should still respond + set Deprecation header."""
    from flask import Flask
    from backend.routes.asr_profiles import bp as asr_bp
    import app as _app
    from backend.asr_profiles import ProfileManager
    mgr = ProfileManager(tmp_path)
    monkeypatch.setattr(_app, "_asr_profile_manager", mgr, raising=False)
    app = Flask(__name__)
    app.register_blueprint(asr_bp)
    monkeypatch.setattr("flask_login.current_user",
                        type("U", (), {"id": 1, "is_admin": False})())
    client = app.test_client()
    resp = client.get("/api/asr_profiles")
    assert resp.headers.get("Deprecation") == 'true'
    assert "/api/transcribe_profiles" in resp.headers.get("Link", "")
```

- [ ] **Step 2: Run test to verify fail**

```bash
pytest tests/test_v5_profile_routes.py::test_transcribe_profiles_create_get -v
```
Expected: FAIL

- [ ] **Step 3: Create `backend/routes/transcribe_profiles.py`** (5 endpoints, same shape as llm_profiles.py)

```python
"""TranscribeProfile REST blueprint — v5-A1."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

import app as _app
from backend.transcribe_profiles import validate_transcribe_profile

bp = Blueprint("transcribe_profiles", __name__)


@bp.get("/api/transcribe_profiles")
@login_required
def list_profiles():
    mgr = _app._transcribe_profile_manager
    profiles = mgr.list_visible(current_user.id, getattr(current_user, "is_admin", False))
    return jsonify({"profiles": profiles}), 200


@bp.post("/api/transcribe_profiles")
@login_required
def create_profile():
    data = request.get_json(silent=True) or {}
    errors = validate_transcribe_profile(data)
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400
    mgr = _app._transcribe_profile_manager
    pid = mgr.create(data, user_id=current_user.id)
    return jsonify(mgr.get(pid)), 201


@bp.get("/api/transcribe_profiles/<pid>")
@login_required
def get_profile(pid):
    mgr = _app._transcribe_profile_manager
    p = mgr.get(pid)
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not (getattr(current_user, "is_admin", False) or p.get("user_id") == current_user.id or p.get("shared")):
        return jsonify({"error": "forbidden"}), 403
    return jsonify(p), 200


@bp.patch("/api/transcribe_profiles/<pid>")
@login_required
def update_profile(pid):
    patch = request.get_json(silent=True) or {}
    mgr = _app._transcribe_profile_manager
    try:
        result = mgr.update_if_owned(pid, current_user.id, getattr(current_user, "is_admin", False), patch)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if result is None:
        return jsonify({"error": "forbidden"}), 403
    return jsonify(result), 200


@bp.delete("/api/transcribe_profiles/<pid>")
@login_required
def delete_profile(pid):
    mgr = _app._transcribe_profile_manager
    ok = mgr.delete_if_owned(pid, current_user.id, getattr(current_user, "is_admin", False))
    if not ok:
        return jsonify({"error": "forbidden or missing"}), 403
    return jsonify({"deleted": pid}), 200
```

- [ ] **Step 4: Patch `backend/routes/asr_profiles.py` to emit Deprecation header**

Open `backend/routes/asr_profiles.py` and add to every endpoint's response (or via `@bp.after_request`):
```python
# Append near end of file, after blueprint definition:
@bp.after_request
def add_deprecation_header(response):
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/transcribe_profiles>; rel="successor-version"'
    response.headers["Sunset"] = "Wed, 31 Dec 2026 00:00:00 GMT"  # post-v5-A3
    return response
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_v5_profile_routes.py -v -k "transcribe or asr_profiles_returns"
```
Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routes/transcribe_profiles.py backend/routes/asr_profiles.py backend/tests/test_v5_profile_routes.py
git commit -m "feat(v5-a1): TranscribeProfile blueprint + asr_profiles Deprecation header"
```

---

### Task 7: TranslatorProfile manager + validator + tests

**Files:**
- Create: `backend/translator_profiles.py`
- Test: `backend/tests/test_v5_profile_managers.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_v5_profile_managers.py`:
```python
def test_translator_profile_valid(tmp_path):
    from backend.translator_profiles import TranslatorProfileManager, validate_translator_profile
    data = {
        "name": "ZH→EN broadcast",
        "source_lang": "zh",
        "target_lang": "en",
        "llm_profile_id": "some-uuid",
        "prompt_template_id": "translator/zh_to_en_default",
    }
    assert validate_translator_profile(data) == []
    mgr = TranslatorProfileManager(tmp_path)
    pid = mgr.create(data, user_id=1)
    assert mgr.get(pid)["source_lang"] == "zh"


def test_translator_profile_rejects_same_source_target(tmp_path):
    from backend.translator_profiles import validate_translator_profile
    errors = validate_translator_profile({
        "name": "bad", "source_lang": "zh", "target_lang": "zh",
        "llm_profile_id": "x", "prompt_template_id": "y",
    })
    assert any("source_lang and target_lang must differ" in e for e in errors)
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_profile_managers.py -v -k translator
```
Expected: FAIL

- [ ] **Step 3: Create `backend/translator_profiles.py`**

```python
"""TranslatorProfile manager — v5-A1.

Cross-lingual conversion (lang_X → lang_Y). Refers to LLMProfile for
backend LLM config and a prompt template ID for the system prompt.
"""
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
    errors: list = []
    if not isinstance(data, dict):
        return ["payload must be object"]
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        errors.append("name required")
    src = data.get("source_lang")
    tgt = data.get("target_lang")
    if src not in VALID_LANGS:
        errors.append(f"source_lang must be in {sorted(VALID_LANGS)}")
    if tgt not in VALID_LANGS:
        errors.append(f"target_lang must be in {sorted(VALID_LANGS)}")
    if src and tgt and src == tgt:
        errors.append("source_lang and target_lang must differ (use Refiner for same-lang polish)")
    if not isinstance(data.get("llm_profile_id"), str) or not data["llm_profile_id"].strip():
        errors.append("llm_profile_id required")
    if not isinstance(data.get("prompt_template_id"), str) or not data["prompt_template_id"].strip():
        errors.append("prompt_template_id required")
    return errors


class TranslatorProfileManager:
    def __init__(self, config_dir: Path):
        self.dir = Path(config_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self, data: dict, *, user_id: int) -> str:
        errors = validate_translator_profile(data)
        if errors:
            raise ValueError("; ".join(errors))
        pid = str(uuid.uuid4())
        payload = {**data, "id": pid, "user_id": user_id, "created_at": time.time()}
        (self.dir / f"{pid}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return pid

    def get(self, pid: str) -> Optional[dict]:
        path = self.dir / f"{pid}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_visible(self, user_id: int, is_admin: bool) -> list[dict]:
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

    def update_if_owned(self, pid: str, user_id: int, is_admin: bool, patch: dict) -> Optional[dict]:
        with _res_lock(pid):
            p = self.get(pid)
            if p is None or not (is_admin or p.get("user_id") == user_id):
                return None
            merged = {**p, **patch}
            errors = validate_translator_profile(merged)
            if errors:
                raise ValueError("; ".join(errors))
            (self.dir / f"{pid}.json").write_text(
                json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            return merged

    def delete_if_owned(self, pid: str, user_id: int, is_admin: bool) -> bool:
        with _res_lock(pid):
            p = self.get(pid)
            if p is None or not (is_admin or p.get("user_id") == user_id):
                return False
            (self.dir / f"{pid}.json").unlink()
            return True
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_profile_managers.py -v -k translator
```
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/translator_profiles.py backend/tests/test_v5_profile_managers.py
git commit -m "feat(v5-a1): TranslatorProfile manager (NEW cross-lingual entity)"
```

---

### Task 8: TranslatorProfile REST blueprint

**Files:**
- Create: `backend/routes/translator_profiles.py`
- Test: `backend/tests/test_v5_profile_routes.py`

- [ ] **Step 1: Write failing test**

Append:
```python
def test_translator_profiles_create_get(monkeypatch, tmp_path):
    from flask import Flask
    from backend.routes.translator_profiles import bp as tr_bp
    from backend.translator_profiles import TranslatorProfileManager
    import app as _app
    mgr = TranslatorProfileManager(tmp_path)
    monkeypatch.setattr(_app, "_translator_profile_manager", mgr, raising=False)
    app = Flask(__name__)
    app.register_blueprint(tr_bp)
    monkeypatch.setattr("flask_login.current_user",
                        type("U", (), {"id": 1, "is_admin": False})())
    client = app.test_client()
    resp = client.post("/api/translator_profiles", json={
        "name": "zh->en", "source_lang": "zh", "target_lang": "en",
        "llm_profile_id": "llm1", "prompt_template_id": "tpl1",
    })
    assert resp.status_code == 201
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_profile_routes.py -v -k translator
```

- [ ] **Step 3: Create `backend/routes/translator_profiles.py`** (copy structure of llm_profiles.py, swap names)

```python
"""TranslatorProfile REST blueprint — v5-A1."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

import app as _app
from backend.translator_profiles import validate_translator_profile

bp = Blueprint("translator_profiles", __name__)


@bp.get("/api/translator_profiles")
@login_required
def list_profiles():
    mgr = _app._translator_profile_manager
    profiles = mgr.list_visible(current_user.id, getattr(current_user, "is_admin", False))
    return jsonify({"profiles": profiles}), 200


@bp.post("/api/translator_profiles")
@login_required
def create_profile():
    data = request.get_json(silent=True) or {}
    errors = validate_translator_profile(data)
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400
    mgr = _app._translator_profile_manager
    pid = mgr.create(data, user_id=current_user.id)
    return jsonify(mgr.get(pid)), 201


@bp.get("/api/translator_profiles/<pid>")
@login_required
def get_profile(pid):
    mgr = _app._translator_profile_manager
    p = mgr.get(pid)
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not (getattr(current_user, "is_admin", False) or p.get("user_id") == current_user.id or p.get("shared")):
        return jsonify({"error": "forbidden"}), 403
    return jsonify(p), 200


@bp.patch("/api/translator_profiles/<pid>")
@login_required
def update_profile(pid):
    patch = request.get_json(silent=True) or {}
    mgr = _app._translator_profile_manager
    try:
        result = mgr.update_if_owned(pid, current_user.id, getattr(current_user, "is_admin", False), patch)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if result is None:
        return jsonify({"error": "forbidden"}), 403
    return jsonify(result), 200


@bp.delete("/api/translator_profiles/<pid>")
@login_required
def delete_profile(pid):
    mgr = _app._translator_profile_manager
    ok = mgr.delete_if_owned(pid, current_user.id, getattr(current_user, "is_admin", False))
    if not ok:
        return jsonify({"error": "forbidden or missing"}), 403
    return jsonify({"deleted": pid}), 200
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_profile_routes.py -v -k translator
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/translator_profiles.py backend/tests/test_v5_profile_routes.py
git commit -m "feat(v5-a1): TranslatorProfile REST blueprint"
```

---

### Task 9: RefinerProfile manager (rename of MT, narrow semantics)

**Files:**
- Create: `backend/refiner_profiles.py`
- Test: `backend/tests/test_v5_profile_managers.py`

- [ ] **Step 1: Write failing test**

Append:
```python
def test_refiner_profile_valid(tmp_path):
    from backend.refiner_profiles import RefinerProfileManager, validate_refiner_profile
    data = {
        "name": "ZH broadcast HK",
        "lang": "zh",
        "style": "broadcast-hk",
        "llm_profile_id": "llm1",
        "prompt_template_id": "refiner/zh_broadcast_hk_default",
    }
    assert validate_refiner_profile(data) == []
    mgr = RefinerProfileManager(tmp_path)
    pid = mgr.create(data, user_id=1)
    assert mgr.get(pid)["style"] == "broadcast-hk"


def test_refiner_profile_rejects_missing_lang(tmp_path):
    from backend.refiner_profiles import validate_refiner_profile
    errors = validate_refiner_profile({"name": "x", "style": "broadcast"})
    assert any("lang" in e for e in errors)
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_profile_managers.py -v -k refiner
```

- [ ] **Step 3: Create `backend/refiner_profiles.py`**

```python
"""RefinerProfile manager — v5-A1.

Same-lingual polish (broadcast register, glossary, disfluency). Narrows
v4 MT profile semantics: NO translation, NO target_language field (lang
is both input and output).
"""
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


def validate_refiner_profile(data: Any) -> list:
    errors: list = []
    if not isinstance(data, dict):
        return ["payload must be object"]
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        errors.append("name required")
    lang = data.get("lang")
    if lang not in VALID_LANGS:
        errors.append(f"lang must be in {sorted(VALID_LANGS)}")
    style = data.get("style", "broadcast")
    if not isinstance(style, str) or not style.strip():
        errors.append("style required (string)")
    if not isinstance(data.get("llm_profile_id"), str) or not data["llm_profile_id"].strip():
        errors.append("llm_profile_id required")
    if not isinstance(data.get("prompt_template_id"), str) or not data["prompt_template_id"].strip():
        errors.append("prompt_template_id required")
    return errors


class RefinerProfileManager:
    def __init__(self, config_dir: Path):
        self.dir = Path(config_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self, data: dict, *, user_id: int) -> str:
        errors = validate_refiner_profile(data)
        if errors:
            raise ValueError("; ".join(errors))
        pid = str(uuid.uuid4())
        payload = {**data, "id": pid, "user_id": user_id, "created_at": time.time()}
        (self.dir / f"{pid}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return pid

    def get(self, pid: str) -> Optional[dict]:
        path = self.dir / f"{pid}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_visible(self, user_id: int, is_admin: bool) -> list[dict]:
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

    def update_if_owned(self, pid: str, user_id: int, is_admin: bool, patch: dict) -> Optional[dict]:
        with _res_lock(pid):
            p = self.get(pid)
            if p is None or not (is_admin or p.get("user_id") == user_id):
                return None
            merged = {**p, **patch}
            errors = validate_refiner_profile(merged)
            if errors:
                raise ValueError("; ".join(errors))
            (self.dir / f"{pid}.json").write_text(
                json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            return merged

    def delete_if_owned(self, pid: str, user_id: int, is_admin: bool) -> bool:
        with _res_lock(pid):
            p = self.get(pid)
            if p is None or not (is_admin or p.get("user_id") == user_id):
                return False
            (self.dir / f"{pid}.json").unlink()
            return True
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_profile_managers.py -v -k refiner
```
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/refiner_profiles.py backend/tests/test_v5_profile_managers.py
git commit -m "feat(v5-a1): RefinerProfile manager (rename of MT with narrowed semantics)"
```

---

### Task 10: RefinerProfile REST blueprint + backward-compat alias on `/api/mt_profiles`

**Files:**
- Create: `backend/routes/refiner_profiles.py`
- Modify: `backend/routes/mt_profiles.py` (add Deprecation header)
- Test: `backend/tests/test_v5_profile_routes.py`

- [ ] **Step 1: Write failing test**

Append:
```python
def test_refiner_profiles_create(monkeypatch, tmp_path):
    from flask import Flask
    from backend.routes.refiner_profiles import bp as ref_bp
    from backend.refiner_profiles import RefinerProfileManager
    import app as _app
    monkeypatch.setattr(_app, "_refiner_profile_manager", RefinerProfileManager(tmp_path), raising=False)
    app = Flask(__name__)
    app.register_blueprint(ref_bp)
    monkeypatch.setattr("flask_login.current_user",
                        type("U", (), {"id": 1, "is_admin": False})())
    client = app.test_client()
    resp = client.post("/api/refiner_profiles", json={
        "name": "zh-bc", "lang": "zh", "style": "broadcast-hk",
        "llm_profile_id": "x", "prompt_template_id": "y",
    })
    assert resp.status_code == 201


def test_mt_profiles_returns_deprecation_header(monkeypatch, tmp_path):
    from flask import Flask
    from backend.routes.mt_profiles import bp as mt_bp
    from backend.mt_profiles import MtProfileManager
    import app as _app
    monkeypatch.setattr(_app, "_mt_profile_manager", MtProfileManager(tmp_path), raising=False)
    app = Flask(__name__)
    app.register_blueprint(mt_bp)
    monkeypatch.setattr("flask_login.current_user",
                        type("U", (), {"id": 1, "is_admin": False})())
    client = app.test_client()
    resp = client.get("/api/mt_profiles")
    assert resp.headers.get("Deprecation") == "true"
    assert "/api/refiner_profiles" in resp.headers.get("Link", "")
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_profile_routes.py -v -k "refiner or mt_profiles_returns"
```

- [ ] **Step 3: Create `backend/routes/refiner_profiles.py`** (mirror structure of translator_profiles.py)

```python
"""RefinerProfile REST blueprint — v5-A1."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

import app as _app
from backend.refiner_profiles import validate_refiner_profile

bp = Blueprint("refiner_profiles", __name__)


@bp.get("/api/refiner_profiles")
@login_required
def list_profiles():
    mgr = _app._refiner_profile_manager
    profiles = mgr.list_visible(current_user.id, getattr(current_user, "is_admin", False))
    return jsonify({"profiles": profiles}), 200


@bp.post("/api/refiner_profiles")
@login_required
def create_profile():
    data = request.get_json(silent=True) or {}
    errors = validate_refiner_profile(data)
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400
    mgr = _app._refiner_profile_manager
    pid = mgr.create(data, user_id=current_user.id)
    return jsonify(mgr.get(pid)), 201


@bp.get("/api/refiner_profiles/<pid>")
@login_required
def get_profile(pid):
    mgr = _app._refiner_profile_manager
    p = mgr.get(pid)
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not (getattr(current_user, "is_admin", False) or p.get("user_id") == current_user.id or p.get("shared")):
        return jsonify({"error": "forbidden"}), 403
    return jsonify(p), 200


@bp.patch("/api/refiner_profiles/<pid>")
@login_required
def update_profile(pid):
    patch = request.get_json(silent=True) or {}
    mgr = _app._refiner_profile_manager
    try:
        result = mgr.update_if_owned(pid, current_user.id, getattr(current_user, "is_admin", False), patch)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if result is None:
        return jsonify({"error": "forbidden"}), 403
    return jsonify(result), 200


@bp.delete("/api/refiner_profiles/<pid>")
@login_required
def delete_profile(pid):
    mgr = _app._refiner_profile_manager
    ok = mgr.delete_if_owned(pid, current_user.id, getattr(current_user, "is_admin", False))
    if not ok:
        return jsonify({"error": "forbidden or missing"}), 403
    return jsonify({"deleted": pid}), 200
```

- [ ] **Step 4: Add Deprecation header to `backend/routes/mt_profiles.py`**

```python
# Append at end of file:
@bp.after_request
def add_deprecation_header(response):
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/refiner_profiles>; rel="successor-version"'
    response.headers["Sunset"] = "Wed, 31 Dec 2026 00:00:00 GMT"
    return response
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_v5_profile_routes.py -v -k "refiner or mt_profiles_returns"
```
Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routes/refiner_profiles.py backend/routes/mt_profiles.py backend/tests/test_v5_profile_routes.py
git commit -m "feat(v5-a1): RefinerProfile blueprint + mt_profiles Deprecation header"
```

---

### Task 11: VerifierProfile manager + validator (NEW)

**Files:**
- Create: `backend/verifier_profiles.py`
- Test: `backend/tests/test_v5_profile_managers.py`

- [ ] **Step 1: Write failing test**

Append:
```python
def test_verifier_profile_valid(tmp_path):
    from backend.verifier_profiles import VerifierProfileManager, validate_verifier_profile
    data = {
        "name": "ZH verifier (LLM judge)",
        "lang": "zh",
        "llm_profile_id": "llm1",
        "prompt_template_id": "verifier/zh_default",
    }
    assert validate_verifier_profile(data) == []
    mgr = VerifierProfileManager(tmp_path)
    pid = mgr.create(data, user_id=1)
    assert mgr.get(pid)["lang"] == "zh"


def test_verifier_profile_rejects_missing_llm(tmp_path):
    from backend.verifier_profiles import validate_verifier_profile
    errors = validate_verifier_profile({"name": "x", "lang": "zh", "prompt_template_id": "y"})
    assert any("llm_profile_id" in e for e in errors)
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_profile_managers.py -v -k verifier
```

- [ ] **Step 3: Create `backend/verifier_profiles.py`** (same structure as refiner_profiles.py but with `lang` field instead of `lang + style`)

```python
"""VerifierProfile manager — v5-A1.

LLM-as-judge config for ASR cross-validation. Each VerifierProfile is
language-specific (the language of the source audio) and references an
LLMProfile + a prompt template.
"""
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


def validate_verifier_profile(data: Any) -> list:
    errors: list = []
    if not isinstance(data, dict):
        return ["payload must be object"]
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        errors.append("name required")
    if data.get("lang") not in VALID_LANGS:
        errors.append(f"lang must be in {sorted(VALID_LANGS)}")
    if not isinstance(data.get("llm_profile_id"), str) or not data["llm_profile_id"].strip():
        errors.append("llm_profile_id required")
    if not isinstance(data.get("prompt_template_id"), str) or not data["prompt_template_id"].strip():
        errors.append("prompt_template_id required")
    return errors


class VerifierProfileManager:
    def __init__(self, config_dir: Path):
        self.dir = Path(config_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self, data: dict, *, user_id: int) -> str:
        errors = validate_verifier_profile(data)
        if errors:
            raise ValueError("; ".join(errors))
        pid = str(uuid.uuid4())
        payload = {**data, "id": pid, "user_id": user_id, "created_at": time.time()}
        (self.dir / f"{pid}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return pid

    def get(self, pid: str) -> Optional[dict]:
        path = self.dir / f"{pid}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_visible(self, user_id: int, is_admin: bool) -> list[dict]:
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

    def update_if_owned(self, pid: str, user_id: int, is_admin: bool, patch: dict) -> Optional[dict]:
        with _res_lock(pid):
            p = self.get(pid)
            if p is None or not (is_admin or p.get("user_id") == user_id):
                return None
            merged = {**p, **patch}
            errors = validate_verifier_profile(merged)
            if errors:
                raise ValueError("; ".join(errors))
            (self.dir / f"{pid}.json").write_text(
                json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            return merged

    def delete_if_owned(self, pid: str, user_id: int, is_admin: bool) -> bool:
        with _res_lock(pid):
            p = self.get(pid)
            if p is None or not (is_admin or p.get("user_id") == user_id):
                return False
            (self.dir / f"{pid}.json").unlink()
            return True
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_profile_managers.py -v -k verifier
```
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/verifier_profiles.py backend/tests/test_v5_profile_managers.py
git commit -m "feat(v5-a1): VerifierProfile manager (NEW LLM-as-judge entity)"
```

---

### Task 12: VerifierProfile REST blueprint

**Files:**
- Create: `backend/routes/verifier_profiles.py`
- Test: `backend/tests/test_v5_profile_routes.py`

- [ ] **Step 1: Write failing test**

Append:
```python
def test_verifier_profiles_create(monkeypatch, tmp_path):
    from flask import Flask
    from backend.routes.verifier_profiles import bp as v_bp
    from backend.verifier_profiles import VerifierProfileManager
    import app as _app
    monkeypatch.setattr(_app, "_verifier_profile_manager", VerifierProfileManager(tmp_path), raising=False)
    app = Flask(__name__)
    app.register_blueprint(v_bp)
    monkeypatch.setattr("flask_login.current_user",
                        type("U", (), {"id": 1, "is_admin": False})())
    client = app.test_client()
    resp = client.post("/api/verifier_profiles", json={
        "name": "v-zh", "lang": "zh", "llm_profile_id": "x", "prompt_template_id": "y",
    })
    assert resp.status_code == 201
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_profile_routes.py -v -k verifier
```

- [ ] **Step 3: Create `backend/routes/verifier_profiles.py`** (same structure as refiner_profiles.py)

```python
"""VerifierProfile REST blueprint — v5-A1."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

import app as _app
from backend.verifier_profiles import validate_verifier_profile

bp = Blueprint("verifier_profiles", __name__)


@bp.get("/api/verifier_profiles")
@login_required
def list_profiles():
    mgr = _app._verifier_profile_manager
    profiles = mgr.list_visible(current_user.id, getattr(current_user, "is_admin", False))
    return jsonify({"profiles": profiles}), 200


@bp.post("/api/verifier_profiles")
@login_required
def create_profile():
    data = request.get_json(silent=True) or {}
    errors = validate_verifier_profile(data)
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400
    mgr = _app._verifier_profile_manager
    pid = mgr.create(data, user_id=current_user.id)
    return jsonify(mgr.get(pid)), 201


@bp.get("/api/verifier_profiles/<pid>")
@login_required
def get_profile(pid):
    mgr = _app._verifier_profile_manager
    p = mgr.get(pid)
    if p is None:
        return jsonify({"error": "not found"}), 404
    if not (getattr(current_user, "is_admin", False) or p.get("user_id") == current_user.id or p.get("shared")):
        return jsonify({"error": "forbidden"}), 403
    return jsonify(p), 200


@bp.patch("/api/verifier_profiles/<pid>")
@login_required
def update_profile(pid):
    patch = request.get_json(silent=True) or {}
    mgr = _app._verifier_profile_manager
    try:
        result = mgr.update_if_owned(pid, current_user.id, getattr(current_user, "is_admin", False), patch)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if result is None:
        return jsonify({"error": "forbidden"}), 403
    return jsonify(result), 200


@bp.delete("/api/verifier_profiles/<pid>")
@login_required
def delete_profile(pid):
    mgr = _app._verifier_profile_manager
    ok = mgr.delete_if_owned(pid, current_user.id, getattr(current_user, "is_admin", False))
    if not ok:
        return jsonify({"error": "forbidden or missing"}), 403
    return jsonify({"deleted": pid}), 200
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_profile_routes.py -v -k verifier
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/verifier_profiles.py backend/tests/test_v5_profile_routes.py
git commit -m "feat(v5-a1): VerifierProfile REST blueprint"
```

---

## Phase 3 — LLM Engine Layer

### Task 13: LLMEngine ABC + OllamaLLM concrete + tests

**Files:**
- Create: `backend/engines/__init__.py`
- Create: `backend/engines/llm/__init__.py`
- Create: `backend/engines/llm/ollama.py`
- Test: `backend/tests/test_v5_llm_engine.py`

- [ ] **Step 1: Write failing test for LLMEngine ABC**

Create `backend/tests/test_v5_llm_engine.py`:
```python
import pytest
from unittest.mock import patch, Mock
from backend.engines.llm import LLMEngine


def test_llm_engine_abc_cannot_instantiate():
    with pytest.raises(TypeError):
        LLMEngine()


def test_ollama_llm_call_success(monkeypatch):
    from backend.engines.llm.ollama import OllamaLLM
    fake_resp = Mock()
    fake_resp.json.return_value = {"message": {"content": "  hello world  "}}
    fake_resp.raise_for_status = Mock()
    monkeypatch.setattr("requests.post", Mock(return_value=fake_resp))
    llm = OllamaLLM(model="m", base_url="http://localhost:11434")
    out = llm.call("sys", "user")
    assert out == "hello world"


def test_ollama_llm_call_empty_raises(monkeypatch):
    from backend.engines.llm.ollama import OllamaLLM
    fake_resp = Mock()
    fake_resp.json.return_value = {"message": {"content": ""}}
    fake_resp.raise_for_status = Mock()
    monkeypatch.setattr("requests.post", Mock(return_value=fake_resp))
    llm = OllamaLLM(model="m", base_url="http://localhost:11434", max_retries=0)
    with pytest.raises(RuntimeError, match="empty"):
        llm.call("sys", "user")
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_llm_engine.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `backend/engines/__init__.py`**

```python
"""v5 engines — central re-exports."""
from backend.engines.llm import LLMEngine
from backend.engines.llm.ollama import OllamaLLM

__all__ = ["LLMEngine", "OllamaLLM"]
```

- [ ] **Step 4: Create `backend/engines/llm/__init__.py`**

```python
"""LLMEngine ABC — low-level LLM HTTP wrapper."""
from abc import ABC, abstractmethod
from typing import Optional


class LLMEngine(ABC):
    """Stateless HTTP wrapper for any LLM backend."""

    @abstractmethod
    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        timeout_sec: float = 120.0,
        think: bool = False,
    ) -> str:
        """Single-turn completion. Returns trimmed content. Raises RuntimeError."""
```

- [ ] **Step 5: Create `backend/engines/llm/ollama.py`**

```python
"""OllamaLLM — concrete LLMEngine for Ollama backend."""
import time
from typing import Optional

import requests

from backend.engines.llm import LLMEngine


class OllamaLLM(LLMEngine):
    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        max_retries: int = 2,
    ):
        self.model = model
        self.base_url = base_url
        self.max_retries = max_retries

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        timeout_sec: float = 120.0,
        think: bool = False,
    ) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": think,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.post(url, json=payload, timeout=timeout_sec)
                r.raise_for_status()
                data = r.json()
                content = (data.get("message") or {}).get("content", "").strip()
                if not content:
                    raise RuntimeError("empty content from Ollama")
                return content
            except Exception as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Ollama call failed after {self.max_retries + 1} attempts: {last_err}") from last_err
        raise RuntimeError("unreachable")
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_v5_llm_engine.py -v
```
Expected: 3 PASS

- [ ] **Step 7: Commit**

```bash
git add backend/engines/__init__.py backend/engines/llm/ backend/tests/test_v5_llm_engine.py
git commit -m "feat(v5-a1): LLMEngine ABC + OllamaLLM concrete"
```

---

### Task 14: OpenRouterLLM concrete + tests

**Files:**
- Create: `backend/engines/llm/openrouter.py`
- Test: `backend/tests/test_v5_llm_engine.py`

- [ ] **Step 1: Write failing test**

Append:
```python
def test_openrouter_llm_call_success(monkeypatch):
    from backend.engines.llm.openrouter import OpenRouterLLM
    from unittest.mock import Mock
    fake_resp = Mock()
    fake_resp.json.return_value = {"choices": [{"message": {"content": "translated text"}}]}
    fake_resp.raise_for_status = Mock()
    monkeypatch.setattr("requests.post", Mock(return_value=fake_resp))
    llm = OpenRouterLLM(model="anthropic/claude-opus-4-7", api_key="sk-xxx")
    out = llm.call("sys", "user")
    assert out == "translated text"


def test_openrouter_llm_sends_bearer_header(monkeypatch):
    from backend.engines.llm.openrouter import OpenRouterLLM
    from unittest.mock import Mock
    captured = {}
    def fake_post(url, json=None, headers=None, timeout=None):
        captured["headers"] = headers
        r = Mock()
        r.json.return_value = {"choices": [{"message": {"content": "x"}}]}
        r.raise_for_status = Mock()
        return r
    monkeypatch.setattr("requests.post", fake_post)
    llm = OpenRouterLLM(model="m", api_key="sk-secret")
    llm.call("sys", "user")
    assert captured["headers"]["Authorization"] == "Bearer sk-secret"
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_llm_engine.py -v -k openrouter
```

- [ ] **Step 3: Create `backend/engines/llm/openrouter.py`**

```python
"""OpenRouterLLM — concrete LLMEngine for OpenAI-compatible OpenRouter API."""
import time
from typing import Optional

import requests

from backend.engines.llm import LLMEngine


class OpenRouterLLM(LLMEngine):
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        max_retries: int = 2,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.max_retries = max_retries

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        timeout_sec: float = 120.0,
        think: bool = False,  # OpenRouter doesn't expose think; ignored
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/whisper-subtitle-ai",
            "X-Title": "whisper-subtitle-ai v5",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.post(url, json=payload, headers=headers, timeout=timeout_sec)
                r.raise_for_status()
                data = r.json()
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
                if not content:
                    raise RuntimeError("empty content from OpenRouter")
                return content
            except Exception as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"OpenRouter call failed: {last_err}") from last_err
        raise RuntimeError("unreachable")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_llm_engine.py -v -k openrouter
```
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/engines/llm/openrouter.py backend/tests/test_v5_llm_engine.py
git commit -m "feat(v5-a1): OpenRouterLLM concrete with Bearer auth"
```

---

## Phase 4 — Transcribe Engine Layer

### Task 15: TranscribeEngine ABC alias + factory

**Files:**
- Create: `backend/engines/transcribe/__init__.py`
- Modify: `backend/asr/__init__.py` (add `TranscribeEngine = ASREngine` alias)
- Test: `backend/tests/test_v5_transcribe_engine.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_v5_transcribe_engine.py`:
```python
def test_transcribe_engine_alias_to_asr_engine():
    from backend.engines.transcribe import TranscribeEngine
    from backend.asr import ASREngine
    # Should be the same class for backward compat
    assert TranscribeEngine is ASREngine or issubclass(TranscribeEngine, ASREngine.__class__)


def test_transcribe_factory_whisper():
    from backend.engines.transcribe import create_transcribe_engine
    profile = {"engine": "whisper", "model_size": "large-v3", "language": "en"}
    engine = create_transcribe_engine(profile)
    assert engine is not None
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_transcribe_engine.py -v
```

- [ ] **Step 3: Create `backend/engines/transcribe/__init__.py`**

```python
"""TranscribeEngine ABC + factory — v5-A1.

Aliases the v4 ASREngine ABC under the v5 'TranscribeEngine' name. Factory
dispatches by `engine` field in profile.
"""
from backend.asr import ASREngine, create_engine as _create_asr_engine

TranscribeEngine = ASREngine


def create_transcribe_engine(profile: dict):
    """Create a TranscribeEngine instance from a TranscribeProfile dict."""
    engine = profile.get("engine")
    if engine == "qwen3-asr":
        from backend.engines.transcribe.qwen3_asr import Qwen3AsrTranscribeEngine
        return Qwen3AsrTranscribeEngine(profile)
    return _create_asr_engine(profile)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_transcribe_engine.py -v -k "alias or factory_whisper"
```
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/engines/transcribe/__init__.py backend/tests/test_v5_transcribe_engine.py
git commit -m "feat(v5-a1): TranscribeEngine ABC alias + factory dispatch"
```

---

### Task 16: Qwen3-ASR subprocess runner (py3.11 entry script)

**Files:**
- Create: `backend/engines/transcribe/qwen3_subprocess.py`
- Test: integration test in Task 17

- [ ] **Step 1: Create the subprocess entry script**

`backend/engines/transcribe/qwen3_subprocess.py`:
```python
#!/usr/bin/env python3.11
"""Qwen3-ASR subprocess entry — runs in py3.11 venv.

Reads JSON args from stdin, transcribes, writes JSON to stdout.

stdin example:
  {"audio_path": "/tmp/x.wav", "language": "Cantonese",
   "context": "Hong Kong racing", "return_timestamps": true}

stdout example:
  {"language": "Cantonese", "full_text": "...", "words": [...], "chunks": [...]}
"""
import json
import sys

try:
    import mlx_qwen3_asr
except ImportError:
    sys.stderr.write("mlx_qwen3_asr not available — check venv_qwen activation\n")
    sys.exit(2)


def main():
    args = json.load(sys.stdin)
    audio = args["audio_path"]
    model = args.get("model", "Qwen/Qwen3-ASR-1.7B")
    language = args.get("language", "Cantonese")
    context = args.get("context", "")
    return_timestamps = args.get("return_timestamps", True)
    return_chunks = args.get("return_chunks", True)

    result = mlx_qwen3_asr.transcribe(
        audio,
        model=model,
        language=language,
        return_timestamps=return_timestamps,
        return_chunks=return_chunks,
        verbose=False,
        context=context,
    )

    out = {
        "language": result.language,
        "full_text": result.text,
        "words": [],
        "chunks": [],
    }
    if hasattr(result, "segments") and result.segments:
        for s in result.segments:
            if isinstance(s, dict):
                out["words"].append({"start": s.get("start"), "end": s.get("end"), "text": s.get("text", "")})
            else:
                out["words"].append({
                    "start": getattr(s, "start", None),
                    "end": getattr(s, "end", None),
                    "text": getattr(s, "text", ""),
                })
    if hasattr(result, "chunks") and result.chunks:
        for c in result.chunks:
            if isinstance(c, dict):
                out["chunks"].append({"start": c.get("start"), "end": c.get("end"), "text": c.get("text", "")})
            else:
                out["chunks"].append({
                    "start": getattr(c, "start", None),
                    "end": getattr(c, "end", None),
                    "text": getattr(c, "text", ""),
                })

    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make executable**

```bash
chmod +x backend/engines/transcribe/qwen3_subprocess.py
```

- [ ] **Step 3: Smoke-test it manually (optional, will be auto-tested in T17)**

```bash
# Activate py3.11 venv where mlx_qwen3_asr is installed
source backend/scripts/v5_prototype/venv_qwen/bin/activate
echo '{"audio_path": "/tmp/hk_60s.wav", "language": "Cantonese"}' | \
  python backend/engines/transcribe/qwen3_subprocess.py | head -100
```
Expected: JSON output with `language`, `full_text`, `words`, `chunks`.

- [ ] **Step 4: Commit**

```bash
git add backend/engines/transcribe/qwen3_subprocess.py
git commit -m "feat(v5-a1): Qwen3-ASR subprocess entry script (py3.11)"
```

---

### Task 17: Qwen3AsrTranscribeEngine wrapper (py3.9) + tests

**Files:**
- Create: `backend/engines/transcribe/qwen3_asr.py`
- Test: `backend/tests/test_v5_transcribe_engine.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_v5_transcribe_engine.py`:
```python
def test_qwen3_asr_wrapper_subprocess_path():
    from backend.engines.transcribe.qwen3_asr import Qwen3AsrTranscribeEngine
    eng = Qwen3AsrTranscribeEngine({
        "engine": "qwen3-asr", "model_size": "1.7B", "language": "zh",
    })
    # Default subprocess Python path resolves under venv_qwen
    assert eng.subprocess_python.endswith("python3") or eng.subprocess_python.endswith("python")
    assert "venv_qwen" in eng.subprocess_python or eng.subprocess_python == "python3.11"


def test_qwen3_asr_runs_subprocess(monkeypatch, tmp_path):
    """Use a fake subprocess.run to simulate Qwen3 output."""
    from backend.engines.transcribe.qwen3_asr import Qwen3AsrTranscribeEngine
    import subprocess
    fake_output = '{"language": "Cantonese", "full_text": "hello", "words": [{"start": 0, "end": 1, "text": "hello"}], "chunks": []}'
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: subprocess.CompletedProcess(
        args=a, returncode=0, stdout=fake_output, stderr=""
    ))
    eng = Qwen3AsrTranscribeEngine({"engine": "qwen3-asr", "language": "zh"})
    audio = tmp_path / "fake.wav"
    audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")  # minimal stub
    segments = eng.transcribe(str(audio), source_lang="zh")
    assert len(segments) == 1
    assert segments[0]["text"] == "hello"
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_transcribe_engine.py -v -k qwen3
```

- [ ] **Step 3: Create `backend/engines/transcribe/qwen3_asr.py`**

```python
"""Qwen3AsrTranscribeEngine — main-process (py3.9) wrapper.

Invokes the py3.11 subprocess at backend/engines/transcribe/qwen3_subprocess.py
via JSON stdin/stdout. Output is converted from word-level tokens into
segment-level (concatenated by chunk).
"""
import json
import os
import subprocess
from pathlib import Path
from typing import Optional


class Qwen3AsrTranscribeEngine:
    """v5-A1 TranscribeEngine implementation wrapping mlx-qwen3-asr via subprocess."""

    def __init__(self, profile: dict):
        self.profile = profile
        self.model = profile.get("model_size") or "1.7B"
        # Resolve subprocess Python: prefer venv_qwen, fall back to python3.11
        repo_root = Path(__file__).resolve().parents[3]
        venv_python = repo_root / "backend" / "scripts" / "v5_prototype" / "venv_qwen" / "bin" / "python"
        self.subprocess_python = str(venv_python) if venv_python.exists() else "python3.11"
        self.subprocess_script = str(repo_root / "backend" / "engines" / "transcribe" / "qwen3_subprocess.py")

    def transcribe(
        self,
        audio_path: str,
        source_lang: str,
        *,
        context: str = "",
        return_timestamps: bool = True,
        timeout_sec: float = 600.0,
        progress=None,
    ) -> list[dict]:
        """Returns list of {start, end, text} segments from chunk-level output."""
        lang_map = {"zh": "Cantonese", "yue": "Cantonese", "en": "English", "ja": "Japanese", "ko": "Korean"}
        language = lang_map.get(source_lang, "Cantonese")
        model_full = f"Qwen/Qwen3-ASR-{self.model}"
        args = {
            "audio_path": audio_path,
            "model": model_full,
            "language": language,
            "context": context,
            "return_timestamps": return_timestamps,
            "return_chunks": True,
        }
        result = subprocess.run(
            [self.subprocess_python, self.subprocess_script],
            input=json.dumps(args),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Qwen3-ASR subprocess failed: {result.stderr}")
        data = json.loads(result.stdout)
        # Prefer chunk-level for sentence boundaries; fall back to word-level
        if data.get("chunks"):
            return [{"start": c["start"], "end": c["end"], "text": c["text"]} for c in data["chunks"]]
        return [{"start": w["start"], "end": w["end"], "text": w["text"]} for w in data.get("words", [])]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_transcribe_engine.py -v -k qwen3
```
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/engines/transcribe/qwen3_asr.py backend/tests/test_v5_transcribe_engine.py
git commit -m "feat(v5-a1): Qwen3AsrTranscribeEngine wrapper (py3.9 subprocess shim)"
```

---

## Phase 5 — Translator + Refiner + Verifier Engines

### Task 18: Default translator prompt templates

**Files:**
- Create: `backend/config/prompt_templates_v5/translator/zh_to_en_default.json`
- Create: `backend/config/prompt_templates_v5/translator/en_to_zh_hk_default.json`

- [ ] **Step 1: Create directory + ZH→EN template**

```bash
mkdir -p backend/config/prompt_templates_v5/translator
```

`backend/config/prompt_templates_v5/translator/zh_to_en_default.json`:
```json
{
  "id": "translator/zh_to_en_default",
  "name": "ZH (HK Cantonese) → EN broadcast translator (default)",
  "version": 1,
  "source_lang": "zh",
  "target_lang": "en",
  "system_prompt": "You are a professional broadcast subtitle translator translating from Hong Kong Cantonese to English.\n\nRules:\n1. Translate the Chinese subtitle line into a SINGLE English line.\n2. Aim for 6-14 English words per segment.\n3. Use natural English broadcast-news register.\n4. Preserve named entities (people, places, organizations).\n5. DO NOT add information not in the source. DO NOT explain.\n6. Output ONLY the English translation, no labels, no Chinese, no preamble.\n\nExamples:\nZH: 這天新10磅仔袁幸瑤出席記者會\nEN: New 10-pound apprentice Yuen Hang-yiu attended the press conference today.\n\nZH: 不少朋友和馬迷\nEN: Many friends and racing fans"
}
```

- [ ] **Step 2: Create EN→ZH HK template** (copy from prototype)

`backend/config/prompt_templates_v5/translator/en_to_zh_hk_default.json`:
```json
{
  "id": "translator/en_to_zh_hk_default",
  "name": "EN → ZH (HK Cantonese broadcast) translator (default)",
  "version": 1,
  "source_lang": "en",
  "target_lang": "zh",
  "system_prompt": "你係香港賽馬電視台嘅資深字幕翻譯員，由英文 broadcast 翻成香港粵語廣播字幕。\n\n規則：\n1. 一行英文 → 一行中文。每段獨立，唔合併、唔拆段、唔濃縮、唔擴寫。\n2. 中文字數 0.4–0.7× 英文字數。\n3. 用香港粵語廣播 register：嘅 / 咗 / 喺 / 同 / 唔 / 啦 / 落去 等粵語 particle；用呢個/嗰個 唔用 這個/那個；用乜嘢/點解 唔用 什麼/為什麼。\n4. 正式賽馬術語/數字/賽事名用書面繁體（一級賽、頭馬、見習騎師、列陣、外閘、跑距）。\n5. 賽馬人名、馬名、馬會場地：保留原文或用標準粵語譯名（Sha Tin → 沙田；BMW Cup → 寶馬大賽；Derby → 打比）。\n6. 唔好加任何英文唔存在嘅資訊。唔解釋、唔形容、唔加 connective word。\n7. 唔好用 v3.18 reject 嘅 formulaic 詞：避免「真正」「儘管」「就此而言」「然而」「事實上」「值得一提的是」「傷病纏身」。\n\n輸出規則：只出一行中文翻譯，唔加 label、唔加引號、唔加解釋。\n\n例子：\nEN: I'm Eden, and on this programme each week I review Hong Kong's upcoming meeting.\nZH: 我係艾登，呢個節目每週同大家回顧香港即將舉行嘅賽事。\n\nEN: This is leg three, a 1600-metre handicap.\nZH: 而家係第三場一千六百米讓賽。\n\nEN: He's drawn well in gate three.\nZH: 佢抽到三檔，位置好。"
}
```

- [ ] **Step 3: Commit**

```bash
git add backend/config/prompt_templates_v5/translator/
git commit -m "feat(v5-a1): default translator prompt templates (zh→en, en→zh HK)"
```

---

### Task 19: TranslatorEngine ABC + LLMTranslator concrete + tests

**Files:**
- Create: `backend/engines/translator/__init__.py`
- Create: `backend/engines/translator/llm_translator.py`
- Test: `backend/tests/test_v5_translator_engine.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_v5_translator_engine.py`:
```python
import pytest
from unittest.mock import Mock


def test_translator_engine_abc_uninstantiable():
    from backend.engines.translator import TranslatorEngine
    with pytest.raises(TypeError):
        TranslatorEngine()


def test_llm_translator_translates_per_segment():
    from backend.engines.translator.llm_translator import LLMTranslator
    fake_llm = Mock()
    fake_llm.call.side_effect = ["translation A", "translation B"]
    tr = LLMTranslator(
        llm=fake_llm,
        system_prompt="translate this",
        source_lang="zh",
        target_lang="en",
    )
    segs = [
        {"start": 0.0, "end": 1.0, "text": "段一"},
        {"start": 1.0, "end": 2.0, "text": "段二"},
    ]
    out = tr.translate(segs)
    assert len(out) == 2
    assert out[0]["text"] == "translation A"
    assert out[1]["text"] == "translation B"
    assert out[0]["start"] == 0.0
    assert out[1]["end"] == 2.0


def test_llm_translator_skips_empty_segments():
    from backend.engines.translator.llm_translator import LLMTranslator
    fake_llm = Mock()
    fake_llm.call.return_value = "x"
    tr = LLMTranslator(
        llm=fake_llm,
        system_prompt="translate",
        source_lang="zh",
        target_lang="en",
    )
    segs = [
        {"start": 0, "end": 1, "text": ""},
        {"start": 1, "end": 2, "text": "real"},
    ]
    out = tr.translate(segs)
    assert out[0]["text"] == ""
    assert out[1]["text"] == "x"
    assert fake_llm.call.call_count == 1
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_translator_engine.py -v
```

- [ ] **Step 3: Create `backend/engines/translator/__init__.py`**

```python
"""TranslatorEngine ABC — cross-lingual conversion."""
from abc import ABC, abstractmethod
from typing import Callable, Optional


class TranslatorEngine(ABC):
    @abstractmethod
    def translate(
        self,
        segments: list[dict],
        *,
        progress: Optional[Callable] = None,
    ) -> list[dict]:
        """Per-segment 1:1; preserves timestamps; outputs target_lang text."""
```

- [ ] **Step 4: Create `backend/engines/translator/llm_translator.py`**

```python
"""LLMTranslator — concrete TranslatorEngine using an LLMEngine backend."""
from typing import Callable, Optional

from backend.engines.translator import TranslatorEngine
from backend.engines.llm import LLMEngine


class LLMTranslator(TranslatorEngine):
    def __init__(
        self,
        llm: LLMEngine,
        system_prompt: str,
        source_lang: str,
        target_lang: str,
    ):
        self.llm = llm
        self.system_prompt = system_prompt
        self.source_lang = source_lang
        self.target_lang = target_lang

    def translate(
        self,
        segments: list[dict],
        *,
        progress: Optional[Callable] = None,
    ) -> list[dict]:
        out: list[dict] = []
        n = len(segments)
        for i, seg in enumerate(segments):
            src = (seg.get("text") or "").strip()
            if not src:
                out.append({"start": seg["start"], "end": seg["end"], "text": ""})
                continue
            # Strip refiner's [HALLUC] tag before translating
            if src.startswith("[HALLUC]"):
                src = src[len("[HALLUC]"):].strip()
            translated = self.llm.call(self.system_prompt, src)
            # Strip common label prefixes
            for prefix in ("EN:", "ZH:", "JA:", "Translation:", "譯文:", "中文:"):
                if translated.startswith(prefix):
                    translated = translated[len(prefix):].strip()
            first_line = next((ln for ln in translated.splitlines() if ln.strip()), "")
            out.append({"start": seg["start"], "end": seg["end"], "text": first_line})
            if progress:
                progress(i + 1, n, first_line)
        return out
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_v5_translator_engine.py -v
```
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/engines/translator/ backend/tests/test_v5_translator_engine.py
git commit -m "feat(v5-a1): TranslatorEngine ABC + LLMTranslator concrete"
```

---

### Task 20: Default refiner prompt templates

**Files:**
- Create: `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json`
- Create: `backend/config/prompt_templates_v5/refiner/en_newscast_default.json`

- [ ] **Step 1: Create directory + ZH broadcast HK template**

```bash
mkdir -p backend/config/prompt_templates_v5/refiner
```

`backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json`:
```json
{
  "id": "refiner/zh_broadcast_hk_default",
  "name": "ZH broadcast HK register refiner (default)",
  "version": 1,
  "lang": "zh",
  "style": "broadcast-hk",
  "system_prompt": "你係香港賽馬電視台嘅字幕編輯。輸入係 Whisper ASR 出嘅原始粵語字幕，可能有以下問題：\n1. 頭幾秒嘅 hallucination（例如「中文字幕提供」「粟米片」呢類同畫面無關嘅垃圾 token）\n2. 個別簡體字漏網\n3. 用詞唔夠 broadcast 風格\n4. 標點冇統一\n\n你要做嘅嘢：\n1. 如果 segment 明顯係 hallucination → 標記為 [HALLUC]，原文保留\n2. 個別簡體 → 繁體（香港用法），但唔好整段重寫\n3. 保留人物地名、保留時間數字、保留語意，淨係潤色用詞\n4. 保持原段嘅字數同節奏\n5. 粵語特徵字 (嘅/咗/啦/喺/嘢) 適度保留\n\n輸出規則：只輸出潤色後嘅字幕一行；唔好加 label、prefix、解釋；如果輸入係 hallucination，prefix `[HALLUC] ` 然後保留原文。"
}
```

- [ ] **Step 2: Create EN newscast template**

`backend/config/prompt_templates_v5/refiner/en_newscast_default.json`:
```json
{
  "id": "refiner/en_newscast_default",
  "name": "EN newscast register refiner (default)",
  "version": 1,
  "lang": "en",
  "style": "newscast",
  "system_prompt": "You are a broadcast subtitle editor for English horse-racing broadcasts. The input is raw English ASR output.\n\nRules:\n1. Output cleaner ENGLISH for the SAME line. Same meaning, no translation.\n2. Fix obvious ASR errors using racing context.\n3. Smooth filler words. Add commas/periods if absent.\n4. Preserve all names (jockeys, horses, trainers, courses).\n5. Keep broadcast register.\n\nOutput: ONE polished English line, no label, no prefix."
}
```

- [ ] **Step 3: Commit**

```bash
git add backend/config/prompt_templates_v5/refiner/
git commit -m "feat(v5-a1): default refiner prompt templates (zh broadcast HK, en newscast)"
```

---

### Task 21: RefinerEngine ABC + LLMRefiner concrete + tests

**Files:**
- Create: `backend/engines/refiner/__init__.py`
- Create: `backend/engines/refiner/llm_refiner.py`
- Test: `backend/tests/test_v5_refiner_engine.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_v5_refiner_engine.py`:
```python
import pytest
from unittest.mock import Mock


def test_refiner_engine_abc_uninstantiable():
    from backend.engines.refiner import RefinerEngine
    with pytest.raises(TypeError):
        RefinerEngine()


def test_llm_refiner_refines_per_segment():
    from backend.engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.side_effect = ["polished A", "[HALLUC] junk"]
    rf = LLMRefiner(
        llm=fake_llm,
        system_prompt="polish",
        lang="zh",
        style="broadcast-hk",
    )
    segs = [
        {"start": 0, "end": 1, "text": "段一"},
        {"start": 1, "end": 2, "text": "中文字幕提供"},
    ]
    out = rf.refine(segs)
    assert out[0]["text"] == "polished A"
    assert out[1]["text"].startswith("[HALLUC]")


def test_llm_refiner_passes_empty_through():
    from backend.engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "x"
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    out = rf.refine([{"start": 0, "end": 1, "text": ""}])
    assert out[0]["text"] == ""
    assert fake_llm.call.call_count == 0
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_refiner_engine.py -v
```

- [ ] **Step 3: Create `backend/engines/refiner/__init__.py`**

```python
"""RefinerEngine ABC — same-lingual polish (register, glossary, disfluency)."""
from abc import ABC, abstractmethod
from typing import Callable, Optional


class RefinerEngine(ABC):
    @abstractmethod
    def refine(
        self,
        segments: list[dict],
        *,
        progress: Optional[Callable] = None,
    ) -> list[dict]:
        """Per-segment 1:1; same lang in/out; preserves timestamps."""
```

- [ ] **Step 4: Create `backend/engines/refiner/llm_refiner.py`**

```python
"""LLMRefiner — concrete RefinerEngine using an LLMEngine backend."""
from typing import Callable, Optional

from backend.engines.refiner import RefinerEngine
from backend.engines.llm import LLMEngine


class LLMRefiner(RefinerEngine):
    def __init__(
        self,
        llm: LLMEngine,
        system_prompt: str,
        lang: str,
        style: str,
    ):
        self.llm = llm
        self.system_prompt = system_prompt
        self.lang = lang
        self.style = style

    def refine(
        self,
        segments: list[dict],
        *,
        progress: Optional[Callable] = None,
    ) -> list[dict]:
        out: list[dict] = []
        n = len(segments)
        for i, seg in enumerate(segments):
            src = (seg.get("text") or "").strip()
            if not src:
                out.append({"start": seg["start"], "end": seg["end"], "text": ""})
                continue
            refined = self.llm.call(self.system_prompt, src)
            for prefix in ("潤:", "潤色:", "Refined:", "輸出:"):
                if refined.startswith(prefix):
                    refined = refined[len(prefix):].strip()
            first_line = next((ln for ln in refined.splitlines() if ln.strip()), "")
            out.append({"start": seg["start"], "end": seg["end"], "text": first_line})
            if progress:
                progress(i + 1, n, first_line)
        return out
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_v5_refiner_engine.py -v
```
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/engines/refiner/ backend/tests/test_v5_refiner_engine.py
git commit -m "feat(v5-a1): RefinerEngine ABC + LLMRefiner concrete"
```

---

### Task 22: Default verifier prompt templates

**Files:**
- Create: `backend/config/prompt_templates_v5/verifier/zh_default.json`
- Create: `backend/config/prompt_templates_v5/verifier/en_default.json`

- [ ] **Step 1: Create directory + ZH verifier template**

```bash
mkdir -p backend/config/prompt_templates_v5/verifier
```

`backend/config/prompt_templates_v5/verifier/zh_default.json`:
```json
{
  "id": "verifier/zh_default",
  "name": "ZH ASR Verifier (LLM-as-judge)",
  "version": 1,
  "lang": "zh",
  "system_prompt": "你係香港賽馬電視台嘅資深字幕編輯，正在處理 ASR 轉錄結果。\n\n兩個獨立 ASR 系統嘅輸出：\n- Whisper：時間軸準，但對粵語廣播容易 hallucinate\n- Qwen3-ASR：粵語識別較準\n\n任務：\n1. 兩個都係空 → 輸出 `[EMPTY]`\n2. 任何一個明顯係 hallucination → 用另一個嘅內容\n3. 兩個都有真實內容 → 揀更準確嘅\n4. 賽馬人名地名術語：信 Qwen3 多啲\n5. 如果兩個都明顯垃圾 → 輸出 `[HALLUC]`\n\n輸出規則：只出一行純文字結果（或 `[EMPTY]` / `[HALLUC]`）；用香港繁體中文；必須完整保留時間範圍嘅內容；唔好加 label。"
}
```

- [ ] **Step 2: Create EN verifier template**

`backend/config/prompt_templates_v5/verifier/en_default.json`:
```json
{
  "id": "verifier/en_default",
  "name": "EN ASR Verifier (LLM-as-judge)",
  "version": 1,
  "lang": "en",
  "system_prompt": "You are a senior subtitle editor verifying ASR output for an English broadcast.\n\nTwo ASR systems transcribed the same audio independently:\n- Whisper-large-v3: timestamps reliable\n- Qwen3-ASR-1.7B: usually catches content even when Whisper hallucinates\n\nTask:\n1. Both EMPTY → `[EMPTY]`\n2. Either is obvious hallucination → use the other\n3. Both have content → pick the more accurate\n4. Names: prefer whichever spells them more conventionally\n5. Both garbage → `[HALLUC]`\n\nOutput: ONE clean English line (or `[EMPTY]` / `[HALLUC]`). Preserve all content for the time range. No labels, no quotes, no explanations."
}
```

- [ ] **Step 3: Commit**

```bash
git add backend/config/prompt_templates_v5/verifier/
git commit -m "feat(v5-a1): default verifier prompt templates (zh, en)"
```

---

### Task 23: VerifierEngine ABC + LLMVerifier + alignment helper + tests

**Files:**
- Create: `backend/engines/verifier/__init__.py`
- Create: `backend/engines/verifier/llm_verifier.py`
- Test: `backend/tests/test_v5_verifier_engine.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_v5_verifier_engine.py`:
```python
import pytest
from unittest.mock import Mock


def test_verifier_engine_abc_uninstantiable():
    from backend.engines.verifier import VerifierEngine
    with pytest.raises(TypeError):
        VerifierEngine()


def test_alignment_collect_words_in_range():
    from backend.engines.verifier.llm_verifier import collect_words_for_range
    words = [
        {"start": 0.0, "end": 0.3, "text": "a"},
        {"start": 0.4, "end": 0.7, "text": "b"},
        {"start": 0.9, "end": 1.2, "text": "c"},
        {"start": 1.3, "end": 1.5, "text": "d"},
    ]
    out = collect_words_for_range(words, 0.0, 1.0)
    # a (mid 0.15) yes, b (mid 0.55) yes, c (mid 1.05) NO
    assert out == "ab"


def test_llm_verifier_uses_qwen_when_whisper_empty():
    from backend.engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "unused"
    v = LLMVerifier(llm=fake_llm, system_prompt="judge", lang="zh")
    primary = [{"start": 0, "end": 1, "text": ""}]
    secondary_words = [{"start": 0.2, "end": 0.5, "text": "hello"}]
    out = v.verify(primary, secondary_words)
    assert out[0]["text"] == "hello"
    # Did not call LLM because trivial QWEN_ONLY
    assert fake_llm.call.call_count == 0


def test_llm_verifier_uses_whisper_when_qwen_empty():
    from backend.engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "unused"
    v = LLMVerifier(llm=fake_llm, system_prompt="judge", lang="zh")
    primary = [{"start": 0, "end": 1, "text": "whisper"}]
    out = v.verify(primary, [])
    assert out[0]["text"] == "whisper"
    assert fake_llm.call.call_count == 0


def test_llm_verifier_judges_disagreement():
    from backend.engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "judged result"
    v = LLMVerifier(llm=fake_llm, system_prompt="judge", lang="zh")
    primary = [{"start": 0, "end": 1, "text": "whisper text"}]
    secondary_words = [{"start": 0.2, "end": 0.8, "text": "qwen"}, {"start": 0.85, "end": 0.95, "text": "text"}]
    out = v.verify(primary, secondary_words)
    assert out[0]["text"] == "judged result"
    assert fake_llm.call.call_count == 1
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_verifier_engine.py -v
```

- [ ] **Step 3: Create `backend/engines/verifier/__init__.py`**

```python
"""VerifierEngine ABC — LLM-as-judge between two ASR outputs."""
from abc import ABC, abstractmethod
from typing import Callable, Optional


class VerifierEngine(ABC):
    @abstractmethod
    def verify(
        self,
        primary_segments: list[dict],
        secondary_words: list[dict],
        *,
        progress: Optional[Callable] = None,
    ) -> list[dict]:
        """Returns canonical source-lang segments aligned to primary's time boundaries."""
```

- [ ] **Step 4: Create `backend/engines/verifier/llm_verifier.py`**

```python
"""LLMVerifier — concrete VerifierEngine using LLM-as-judge."""
from typing import Callable, Optional

from backend.engines.verifier import VerifierEngine
from backend.engines.llm import LLMEngine

try:
    from opencc import OpenCC
    _cc = OpenCC("s2hk")
    def _s2hk(s: str) -> str:
        return _cc.convert(s)
except ImportError:
    def _s2hk(s: str) -> str:
        return s


def collect_words_for_range(words: list[dict], start: float, end: float) -> str:
    """Collect secondary ASR words whose midpoint falls in [start, end)."""
    out: list[str] = []
    for w in words:
        ws = w.get("start")
        we = w.get("end")
        if ws is None or we is None:
            continue
        mid = (ws + we) / 2
        if start <= mid < end:
            out.append(w.get("text", ""))
    return "".join(out)


class LLMVerifier(VerifierEngine):
    def __init__(
        self,
        llm: LLMEngine,
        system_prompt: str,
        lang: str,
    ):
        self.llm = llm
        self.system_prompt = system_prompt
        self.lang = lang

    def verify(
        self,
        primary_segments: list[dict],
        secondary_words: list[dict],
        *,
        progress: Optional[Callable] = None,
    ) -> list[dict]:
        out: list[dict] = []
        n = len(primary_segments)
        for i, ps in enumerate(primary_segments):
            wt = (ps.get("text") or "").strip()
            qt_simp = collect_words_for_range(secondary_words, ps["start"], ps["end"])
            qt = _s2hk(qt_simp) if self.lang == "zh" else qt_simp

            if not wt and not qt:
                decision = "[EMPTY]"
            elif wt == qt and wt:
                decision = qt
            elif not wt:
                decision = qt
            elif not qt:
                decision = wt
            else:
                user_prompt = (
                    f"Time: {ps['start']:.2f}-{ps['end']:.2f}s\n"
                    f"Whisper: {wt}\n"
                    f"Qwen3:   {qt}"
                )
                raw = self.llm.call(self.system_prompt, user_prompt)
                for prefix in ("Output:", "Result:", "輸出:", "輸出："):
                    if raw.startswith(prefix):
                        raw = raw[len(prefix):].strip()
                decision = raw.splitlines()[0].strip() if raw else "[EMPTY]"

            out.append({"start": ps["start"], "end": ps["end"], "text": decision})
            if progress:
                progress(i + 1, n, decision)
        return out
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_v5_verifier_engine.py -v
```
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/engines/verifier/ backend/tests/test_v5_verifier_engine.py
git commit -m "feat(v5-a1): VerifierEngine ABC + LLMVerifier + alignment helper"
```

---

## Phase 6 — Pipeline Integration

### Task 24: Pipeline manager loads v5 schema (no execution)

**Files:**
- Modify: `backend/pipelines.py`
- Test: `backend/tests/test_v5_pipeline_schema.py`

- [ ] **Step 1: Write failing test for `PipelineManager.load_v5`**

Append to `backend/tests/test_v5_pipeline_schema.py`:
```python
def test_pipeline_manager_loads_v5(tmp_path):
    """PipelineManager should accept v5 schema and store + retrieve it."""
    from backend.pipelines import PipelineManager
    mgr = PipelineManager(tmp_path)
    v5_data = {
        "name": "v5 test",
        "version": 5,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "asr_secondary": None,
        "asr_verifier": None,
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "translators": {},
        "glossary_stages": {},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    pid = mgr.create(v5_data, user_id=1, validate_refs=False)
    loaded = mgr.get(pid)
    assert loaded["version"] == 5


def test_pipeline_manager_promotes_v4(tmp_path):
    """A v4 pipeline JSON loaded via the manager should round-trip as v5."""
    from backend.pipelines import PipelineManager
    mgr = PipelineManager(tmp_path)
    v4_data = {
        "name": "legacy v4",
        "asr_profile_id": "asr1",
        "asr_profile": {"language": "zh"},
        "mt_stages": ["mt1"],
        "glossary_stage": {"glossary_ids": ["g1"]},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    pid = mgr.create(v4_data, user_id=1, validate_refs=False)
    loaded = mgr.get(pid)
    # The manager should auto-promote to v5 on read
    assert loaded["version"] == 5
    assert loaded["target_languages"] == ["zh"]
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_pipeline_schema.py -v -k pipeline_manager_loads
```

- [ ] **Step 3: Patch `backend/pipelines.py`**

Open `backend/pipelines.py`. Near the top, add import:
```python
from backend.pipeline_schema_v5 import validate_v5_pipeline, promote_v4_to_v5
```

In the `PipelineManager.create` method, add version branch BEFORE the existing v4 validation logic. Find the spot where data is validated and add:
```python
def create(self, data: dict, *, user_id: int, validate_refs: bool = True) -> str:
    # v5 branch
    if data.get("version") == 5:
        errors = validate_v5_pipeline(data)
        if errors:
            raise ValueError("; ".join(errors))
        pid = str(uuid.uuid4())
        payload = {**data, "id": pid, "user_id": user_id, "created_at": time.time()}
        (self.dir / f"{pid}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return pid
    # v4 path (existing logic) — also add auto-promote at create time
    # ... (keep existing v4 validation)
```

In `PipelineManager.get`:
```python
def get(self, pid: str) -> Optional[dict]:
    path = self.dir / f"{pid}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    # Lazy promote v4 → v5
    if data.get("version") != 5:
        data = promote_v4_to_v5(data)
    return data
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_pipeline_schema.py -v -k pipeline_manager
```
Expected: 2 PASS

- [ ] **Step 5: Verify existing v4 pipeline tests still pass**

```bash
pytest tests/ -k pipeline -v 2>&1 | tail -30
```
Expected: no new failures vs baseline.

- [ ] **Step 6: Commit**

```bash
git add backend/pipelines.py backend/tests/test_v5_pipeline_schema.py
git commit -m "feat(v5-a1): PipelineManager loads v5 + auto-promotes v4 on read"
```

---

### Task 25: `/api/pipelines` accepts v5 JSON + cascade refs validate against new profiles

**Files:**
- Modify: `backend/routes/pipelines.py`
- Test: `backend/tests/test_v5_pipeline_schema.py`

- [ ] **Step 1: Write failing test**

Append:
```python
def test_pipelines_route_accepts_v5(monkeypatch, tmp_path):
    from flask import Flask
    from backend.routes.pipelines import bp as pl_bp
    from backend.pipelines import PipelineManager
    import app as _app
    monkeypatch.setattr(_app, "_pipeline_manager", PipelineManager(tmp_path), raising=False)
    # Stub managers for ref check
    fake = type("FakeMgr", (), {"get": lambda self, x: {"id": x}, "list_visible": lambda self, *a: []})()
    for attr in (
        "_transcribe_profile_manager",
        "_translator_profile_manager",
        "_refiner_profile_manager",
        "_verifier_profile_manager",
        "_glossary_manager",
        "_llm_profile_manager",
    ):
        monkeypatch.setattr(_app, attr, fake, raising=False)
    app = Flask(__name__)
    app.register_blueprint(pl_bp)
    monkeypatch.setattr("flask_login.current_user",
                        type("U", (), {"id": 1, "is_admin": False})())
    client = app.test_client()
    resp = client.post("/api/pipelines", json={
        "name": "v5", "version": 5,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "asr_secondary": None, "asr_verifier": None,
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "translators": {},
        "glossary_stages": {},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    })
    assert resp.status_code == 201
    assert resp.json["version"] == 5
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_pipeline_schema.py::test_pipelines_route_accepts_v5 -v
```

- [ ] **Step 3: Patch `backend/routes/pipelines.py`**

Open the file. In the `POST /api/pipelines` handler, add v5 branch:
```python
# Near top, alongside existing imports:
from backend.pipeline_schema_v5 import (
    validate_v5_pipeline,
    check_cascade_refs as v5_check_cascade_refs,
)

# In create handler:
@bp.post("/api/pipelines")
@login_required
def create_pipeline():
    data = request.get_json(silent=True) or {}
    if data.get("version") == 5:
        errors = validate_v5_pipeline(data)
        if errors:
            return jsonify({"error": "; ".join(errors)}), 400
        # Cascade ref check against v5 managers
        refs = _collect_v5_known_refs()
        broken = v5_check_cascade_refs(data, refs)
        if broken:
            return jsonify({"error": f"unknown references: {broken}"}), 400
        mgr = _app._pipeline_manager
        pid = mgr.create(data, user_id=current_user.id)
        return jsonify(mgr.get(pid)), 201
    # ... existing v4 path unchanged ...
```

Add the helper:
```python
def _collect_v5_known_refs() -> dict:
    """Build the known-refs dict for v5 cascade check from v5 managers."""
    return {
        "transcribe": {p["id"] for p in _app._transcribe_profile_manager.list_visible(current_user.id, True)},
        "translator": {p["id"] for p in _app._translator_profile_manager.list_visible(current_user.id, True)},
        "refiner": {p["id"] for p in _app._refiner_profile_manager.list_visible(current_user.id, True)},
        "verifier": {p["id"] for p in _app._verifier_profile_manager.list_visible(current_user.id, True)},
        "glossary": {g["id"] for g in _app._glossary_manager.list_visible(current_user.id, True)},
        "llm": {p["id"] for p in _app._llm_profile_manager.list_visible(current_user.id, True)},
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_pipeline_schema.py::test_pipelines_route_accepts_v5 -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/pipelines.py backend/tests/test_v5_pipeline_schema.py
git commit -m "feat(v5-a1): /api/pipelines accepts v5 schema with cascade ref check"
```

---

### Task 26: Bootstrap wires 5 new blueprints + manager singletons

**Files:**
- Modify: `backend/bootstrap.py`
- Modify: `backend/managers.py`
- Test: smoke test via `backend/tests/test_v5_profile_routes.py::test_bootstrap_registers_v5_blueprints`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_v5_profile_routes.py`:
```python
def test_bootstrap_registers_v5_blueprints():
    """Verify all 5 v5 blueprints are registered on app."""
    from backend.bootstrap import create_app
    app = create_app(testing=True)
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/api/llm_profiles" in rules
    assert "/api/transcribe_profiles" in rules
    assert "/api/translator_profiles" in rules
    assert "/api/refiner_profiles" in rules
    assert "/api/verifier_profiles" in rules
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_profile_routes.py::test_bootstrap_registers_v5_blueprints -v
```

- [ ] **Step 3: Patch `backend/bootstrap.py`**

Open file. Find the blueprint registration section. Add:
```python
from backend.routes.llm_profiles import bp as llm_profiles_bp
from backend.routes.transcribe_profiles import bp as transcribe_profiles_bp
from backend.routes.translator_profiles import bp as translator_profiles_bp
from backend.routes.refiner_profiles import bp as refiner_profiles_bp
from backend.routes.verifier_profiles import bp as verifier_profiles_bp

def create_app(testing=False):
    # ... existing setup ...
    app.register_blueprint(llm_profiles_bp)
    app.register_blueprint(transcribe_profiles_bp)
    app.register_blueprint(translator_profiles_bp)
    app.register_blueprint(refiner_profiles_bp)
    app.register_blueprint(verifier_profiles_bp)
    # ... existing v4 blueprints ...
    return app
```

- [ ] **Step 4: Patch `backend/managers.py`**

Add 5 manager singletons. Find the section where existing managers are instantiated; add:
```python
from backend.llm_profiles import LLMProfileManager
from backend.transcribe_profiles import TranscribeProfileManager
from backend.translator_profiles import TranslatorProfileManager
from backend.refiner_profiles import RefinerProfileManager
from backend.verifier_profiles import VerifierProfileManager

def init_v5_managers(config_dir: Path):
    """Initialize v5 profile managers; called from bootstrap."""
    import app as _app
    base = Path(config_dir)
    _app._llm_profile_manager = LLMProfileManager(base / "llm_profiles")
    _app._transcribe_profile_manager = TranscribeProfileManager(base / "transcribe_profiles")
    _app._translator_profile_manager = TranslatorProfileManager(base / "translator_profiles")
    _app._refiner_profile_manager = RefinerProfileManager(base / "refiner_profiles")
    _app._verifier_profile_manager = VerifierProfileManager(base / "verifier_profiles")
```

Then wire `init_v5_managers(config_dir)` into bootstrap's `create_app`.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_v5_profile_routes.py::test_bootstrap_registers_v5_blueprints -v
```
Expected: PASS

- [ ] **Step 6: Verify no v4 regression**

```bash
pytest tests/ -v 2>&1 | tail -20
```
Expected: no new failures.

- [ ] **Step 7: Commit**

```bash
git add backend/bootstrap.py backend/managers.py backend/tests/test_v5_profile_routes.py
git commit -m "feat(v5-a1): bootstrap wires 5 v5 blueprints + manager singletons"
```

---

## Phase 7 — Integration Tests + Docs

### Task 27: End-to-end schema load smoke test (v5 JSON → all stages instantiable)

**Files:**
- Test: `backend/tests/test_v5_integration.py`

- [ ] **Step 1: Write end-to-end integration test**

Create `backend/tests/test_v5_integration.py`:
```python
"""v5-A1 integration: load a v5 pipeline JSON end-to-end through profile managers + schema."""
import json
import pytest
from pathlib import Path


def test_v5_full_pipeline_load_end_to_end(tmp_path, monkeypatch):
    """Build profiles, save v5 pipeline JSON, load and verify all refs resolve."""
    from backend.llm_profiles import LLMProfileManager
    from backend.transcribe_profiles import TranscribeProfileManager
    from backend.translator_profiles import TranslatorProfileManager
    from backend.refiner_profiles import RefinerProfileManager
    from backend.verifier_profiles import VerifierProfileManager
    from backend.pipelines import PipelineManager
    from backend.pipeline_schema_v5 import check_cascade_refs

    # Set up managers
    llm = LLMProfileManager(tmp_path / "llm")
    tr = TranscribeProfileManager(tmp_path / "transcribe")
    xl = TranslatorProfileManager(tmp_path / "translator")
    rf = RefinerProfileManager(tmp_path / "refiner")
    vf = VerifierProfileManager(tmp_path / "verifier")
    pl = PipelineManager(tmp_path / "pipeline")

    # Create profiles
    llm_id = llm.create({
        "name": "ollama qwen", "backend": "ollama",
        "model": "qwen3.5:35b-a3b-mlx-bf16", "base_url": "http://localhost:11434",
    }, user_id=1)
    tp_primary = tr.create({
        "name": "whisper", "engine": "whisper", "model_size": "large-v3", "language": "zh",
    }, user_id=1)
    tp_secondary = tr.create({
        "name": "qwen3", "engine": "qwen3-asr", "language": "zh",
    }, user_id=1)
    rp = rf.create({
        "name": "zh-broadcast", "lang": "zh", "style": "broadcast-hk",
        "llm_profile_id": llm_id,
        "prompt_template_id": "refiner/zh_broadcast_hk_default",
    }, user_id=1)
    tr_id = xl.create({
        "name": "zh->en", "source_lang": "zh", "target_lang": "en",
        "llm_profile_id": llm_id,
        "prompt_template_id": "translator/zh_to_en_default",
    }, user_id=1)

    # Build v5 pipeline
    v5 = {
        "name": "HK broadcast (ZH+EN)",
        "version": 5,
        "user_id": 1,
        "asr_primary": {"transcribe_profile_id": tp_primary, "source_lang": "zh"},
        "asr_secondary": {"transcribe_profile_id": tp_secondary, "source_lang": "zh"},
        "asr_verifier": {"llm_profile_id": llm_id, "prompt_template_id": "verifier/zh_default"},
        "target_languages": ["zh", "en"],
        "refinements": {"zh": [{"refiner_profile_id": rp}], "en": []},
        "translators": {"en": {"translator_profile_id": tr_id}},
        "glossary_stages": {},
        "font_config": {"family": "Noto Sans TC", "color": "white", "outline_color": "black"},
    }
    pid = pl.create(v5, user_id=1, validate_refs=False)
    loaded = pl.get(pid)
    assert loaded["version"] == 5
    assert loaded["asr_secondary"]["transcribe_profile_id"] == tp_secondary

    # Cascade ref check against fresh manager-based ref set
    refs = {
        "transcribe": {p["id"] for p in tr.list_visible(1, True)},
        "translator": {p["id"] for p in xl.list_visible(1, True)},
        "refiner": {p["id"] for p in rf.list_visible(1, True)},
        "verifier": {p["id"] for p in vf.list_visible(1, True)},
        "glossary": set(),
        "llm": {p["id"] for p in llm.list_visible(1, True)},
    }
    broken = check_cascade_refs(loaded, refs)
    assert broken == [], f"unexpected broken refs: {broken}"
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_v5_integration.py -v
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_v5_integration.py
git commit -m "test(v5-a1): end-to-end schema load integration test"
```

---

### Task 28: Update CLAUDE.md v5-A1 progress entry

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Read CLAUDE.md "Completed Features" section** and identify the head (currently v4.0 A6).

- [ ] **Step 2: Add v5-A1 entry above v4.0 A6**

Insert under "## Completed Features":
```markdown
### v5-A1 — Schema + Engine ABCs (in progress on `chore/asr-mt-rearchitecture-research`)
- Foundation phase for v5 dual-ASR + Refiner-Translator separation. Spec: [docs/superpowers/specs/2026-05-19-v5-dual-asr-refiner-translator-design.md](docs/superpowers/specs/2026-05-19-v5-dual-asr-refiner-translator-design.md). Plan: [docs/superpowers/plans/2026-05-19-v5-A1-schema-engines-plan.md](docs/superpowers/plans/2026-05-19-v5-A1-schema-engines-plan.md).
- **Schema (T1-T2)**: New `backend/pipeline_schema_v5.py` — `validate_v5_pipeline`, `promote_v4_to_v5` (lossless v4→v5 auto-promote), `check_cascade_refs` (cross-manager ref validation).
- **5 new profile managers + REST blueprints (T3-T12)**:
  - `LLMProfileManager` ([backend/llm_profiles.py](backend/llm_profiles.py)) — Ollama / OpenRouter / Claude backend config
  - `TranscribeProfileManager` ([backend/transcribe_profiles.py](backend/transcribe_profiles.py)) — adds `qwen3-asr` engine to whisper / mlx-whisper
  - `TranslatorProfileManager` ([backend/translator_profiles.py](backend/translator_profiles.py)) — NEW cross-lingual profile (source_lang ≠ target_lang)
  - `RefinerProfileManager` ([backend/refiner_profiles.py](backend/refiner_profiles.py)) — same-lingual polish (rename of MT, narrowed semantics)
  - `VerifierProfileManager` ([backend/verifier_profiles.py](backend/verifier_profiles.py)) — NEW LLM-as-judge config
- **5 new REST blueprints** under `backend/routes/` (`llm_profiles.py` / `transcribe_profiles.py` / `translator_profiles.py` / `refiner_profiles.py` / `verifier_profiles.py`); 5 endpoints each (list/create/get/patch/delete) following v4 P1 ownership + TOCTOU pattern.
- **Backward-compat**: `/api/asr_profiles` + `/api/mt_profiles` keep working with `Deprecation: true` + `Link: <successor>` + `Sunset: 2026-12-31` headers. Removed in v5-A3.
- **5 new engine ABCs** under `backend/engines/`:
  - `LLMEngine` ([backend/engines/llm/](backend/engines/llm/)) + `OllamaLLM` + `OpenRouterLLM` concrete; supports Qwen3 `think: false` to disable reasoning chain for non-reasoning tasks (186× speedup observed in prototype).
  - `TranscribeEngine` alias of v4 `ASREngine` ([backend/engines/transcribe/](backend/engines/transcribe/)) + factory dispatch; `Qwen3AsrTranscribeEngine` subprocess wrapper invoking py3.11 `mlx-qwen3-asr` via JSON stdin/stdout.
  - `TranslatorEngine` ABC + `LLMTranslator` concrete (cross-lingual, per-segment 1:1, strips `[HALLUC]` tag before translating).
  - `RefinerEngine` ABC + `LLMRefiner` concrete (same-lingual polish, per-segment 1:1).
  - `VerifierEngine` ABC + `LLMVerifier` concrete with `collect_words_for_range` alignment helper + OpenCC s2hk conversion for Cantonese source.
- **6 default prompt templates** under `backend/config/prompt_templates_v5/` (translator zh→en + en→zh HK; refiner zh broadcast HK + en newscast; verifier zh + en), seeded from working prototype prompts validated in HK clip + Winning Factor runs (see spec §10).
- **Pipeline integration (T24-T26)**: `PipelineManager` accepts v5 JSON natively; v4 pipelines auto-promote on read. `/api/pipelines` POST validates v5 + cascade-checks all refs across the 5 new + glossary + LLM managers. `bootstrap.create_app()` wires all 5 v5 blueprints + manager singletons.
- **End-to-end integration test (T27)** ([backend/tests/test_v5_integration.py](backend/tests/test_v5_integration.py)) — builds 5 profiles, saves v5 pipeline JSON, loads + cascade-checks; passes.
- **Out of A1 scope** (deferred to A2 / A3): `pipeline_runner` DAG executor (A2); new stage classes (A2); file registry multi-lang `by_lang` shape (A2); frontend redesign (A3); SenseVoice third ASR (post-v5).
- **Tests**: ~80 new backend pytest cases across `test_v5_pipeline_schema.py` / `test_v5_profile_managers.py` / `test_v5_profile_routes.py` / `test_v5_llm_engine.py` / `test_v5_transcribe_engine.py` / `test_v5_translator_engine.py` / `test_v5_refiner_engine.py` / `test_v5_verifier_engine.py` / `test_v5_integration.py`. All v4 tests unchanged.
- **Validation evidence**: Prototype runs at [backend/scripts/v5_prototype/out/](backend/scripts/v5_prototype/out/) (HK clip 261s, 97 segments — first 28s hallucination fully recovered + 8 entity names corrected vs Whisper-only baseline) and [backend/scripts/v5_prototype/out_winfactor/](backend/scripts/v5_prototype/out_winfactor/) (Winning Factor EN 577s — zero v3.18 black-list formulaic phrases vs 7+ in v4 baseline). 50.9 / 228 second end-to-end with `think:false`.
```

- [ ] **Step 3: Verify CLAUDE.md still renders cleanly**

```bash
head -200 CLAUDE.md | tail -50
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(v5-a1): CLAUDE.md progress entry for schema + engine ABCs phase"
```

---

## Final verification

After all 28 tasks:

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend && source venv/bin/activate
pytest tests/ -v 2>&1 | tail -30
```
Expected: All v5-A1 new tests PASS; v4 baseline unchanged; 14 pre-existing failures from CLAUDE.md baseline preserved.

- [ ] **Step 2: Test count diff**

```bash
pytest tests/ --collect-only 2>&1 | grep "test_v5" | wc -l
```
Expected: ~80 new tests collected.

- [ ] **Step 3: Verify no v4 endpoint regression**

```bash
pytest tests/ -k "asr_profile or mt_profile or pipeline" -v 2>&1 | tail -20
```
Expected: All previously-green v4 endpoint tests still green.

- [ ] **Step 4: Smoke test the v5 schema via curl** (manual, requires running backend)

```bash
# Start backend
cd backend && source venv/bin/activate && python app.py &

# Login + create v5 pipeline
TOKEN=$(curl -s -c /tmp/cookies.txt -X POST http://localhost:5001/login \
  -d 'username=admin&password=AdminPass1!')

curl -b /tmp/cookies.txt -X POST http://localhost:5001/api/transcribe_profiles \
  -H "Content-Type: application/json" \
  -d '{"name":"qwen3","engine":"qwen3-asr","language":"zh"}'
```
Expected: 201 with profile JSON.

---

## Self-review notes

Run after writing the entire plan:

1. **Spec coverage** — every spec section §3 (schema) / §4 (ABCs) / §5 (stages skipped, see §9 phase split) / §6 (overrides handled at engine level via custom_system_prompt) / §7 (API endpoints all listed) / §9 (migration via promote_v4_to_v5) / §12 (acceptance via Final verification) has at least one task.
2. **Placeholder scan** — no TBD / TODO / FIXME / "fill in" in the plan (✓ verified before commit).
3. **Type consistency** — `validate_*_profile`, `create_*_profile_manager`, `*_profile_manager` singleton naming all consistent across tasks.
4. **A2 dependencies** — A2 will need `PipelineRunner` to consume the v5 schema. A1 leaves the schema loadable but execution path unchanged; A2 starts by writing new stage classes that delegate to the 5 engine ABCs created here.

---

**End of v5-A1 plan.**
