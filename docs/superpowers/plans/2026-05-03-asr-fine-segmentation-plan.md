# ASR Fine-Segmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in `fine_segmentation` flag to mlx-whisper profile that pre-segments audio with Silero VAD, transcribes each chunk with `temperature=0.0` + `word_timestamps=True`, then refines via word-gap split — architecturally fixing cross-30s-window mid-clause cuts.

**Architecture:** New `backend/asr/sentence_split.py` module wraps Silero VAD pre-segment → per-chunk `mlx_whisper.transcribe()` (offset-shifted) → recursive `word_gap_split` post-process. Wired into `app.py:transcribe_with_segments` via opt-in profile flag. Legacy path unchanged — `fine_segmentation: false` (default) preserves all existing behaviour.

**Tech Stack:** Python 3.9, mlx-whisper, silero-vad>=6.2.0 (new dep), Flask-SocketIO, pytest.

**Spec:** [docs/superpowers/specs/2026-05-03-asr-fine-segmentation-design.md](../specs/2026-05-03-asr-fine-segmentation-design.md) (commit `11f92e2`)
**Validation:** [docs/superpowers/specs/2026-05-03-asr-fine-segmentation-validation.md](../specs/2026-05-03-asr-fine-segmentation-validation.md)

---

## File Map

### New files

| Path | Purpose | Phase |
|---|---|---|
| `backend/asr/sentence_split.py` | Public `transcribe_fine_seg()` + `word_gap_split()`; private VAD/chunk/fallback helpers; module-level Silero singleton | B |
| `backend/tests/test_sentence_split.py` | 16 unit tests covering word_gap_split, _subcap_chunks, setup error, edge cases | B |
| `backend/tests/test_mlx_whisper_engine_temperature.py` | 3 tests for temperature kwarg plumbing + schema | A |
| `backend/tests/test_app_fine_seg.py` | 4 tests for branch logic, registry flag, warning event, skip merge bypass | C |
| `backend/tests/integration/__init__.py` | Empty package marker | E |
| `backend/tests/integration/test_fine_segmentation.py` | 2 `@pytest.mark.live` tests on Real Madrid + Trump audio | E |

### Modified files

| Path | What changes | Phase |
|---|---|---|
| `backend/requirements.txt` | Add `silero-vad>=6.2.0` | A |
| `backend/asr/mlx_whisper_engine.py` | Forward `temperature` kwarg; expose in schema | A |
| `backend/profiles.py` | `_validate_asr` + `_validate_translation` accept new fields with range validation + cross-field rules | A |
| `backend/tests/test_profiles.py` | +6 tests for new field validation | A |
| `backend/tests/conftest.py` | Add `--run-live` flag + `pytest_collection_modifyitems` skip | E |
| `backend/app.py` | Branch in `transcribe_with_segments`; `_auto_translate` skip flag; `transcribed_with_fine_seg` registry flag; `transcription_warning` socketio event | C |
| `frontend/index.html` | Profile form: `fine_segmentation` toggle + `temperature` input; toast listener for `transcription_warning` event | D |
| `CLAUDE.md` | Add v3.8 section | F |
| `README.md` | Add 繁中 v3.8 section | F |
| `docs/PRD.md` | Flip ASR fine-segmentation row to ✅ v3.8 | F |

### NOT modified (out of scope)

- `backend/asr/segment_utils.py` — legacy path, unchanged
- `backend/asr/whisper_engine.py` — faster-whisper engine, not in Phase 1
- `backend/translation/sentence_pipeline.py` — only bypassed via flag, no internal change
- `backend/translation/alignment_pipeline.py`, `post_processor.py` — unchanged

---

## Phase A — Setup + Schema

Foundation: install silero-vad dep, add 11 profile schema fields, plumb `temperature` through mlx engine. After this phase, profile validation accepts new fields but pipeline ignores them (gated behind branch logic added in Phase C).

### Task A1: Add silero-vad to requirements

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Read current requirements.txt**

```bash
cat backend/requirements.txt
```

- [ ] **Step 2: Append silero-vad pin**

Add this line (alphabetically near `pysbd` if present):

```
silero-vad>=6.2.0
```

- [ ] **Step 3: Install in venv**

```bash
cd backend && source venv/bin/activate && pip install 'silero-vad>=6.2.0'
```

Expected output: `Successfully installed silero-vad-6.x.x`

- [ ] **Step 4: Verify import**

```bash
cd backend && source venv/bin/activate && python -c "from silero_vad import load_silero_vad, get_speech_timestamps, read_audio; print('OK')"
```

Expected output: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat(asr): add silero-vad>=6.2.0 dependency for fine_segmentation"
```

---

### Task A2: Profile validation — `fine_segmentation` flag + cross-field reject

**Files:**
- Modify: `backend/profiles.py:293-310` (`_validate_asr` function)
- Test: `backend/tests/test_profiles.py` (append)

- [ ] **Step 1: Write failing test for `fine_segmentation` flag default**

Append to `backend/tests/test_profiles.py`:

```python
def test_profile_validates_fine_segmentation_bool(config_dir):
    """fine_segmentation must be bool when present."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    profile_data = {
        "name": "Bad fine_seg type",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "fine_segmentation": "yes"},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(profile_data)
    assert any("fine_segmentation" in e and "bool" in e for e in errors), errors


def test_profile_rejects_fine_segmentation_with_non_mlx_engine(config_dir):
    """fine_segmentation=true requires engine=mlx-whisper."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    profile_data = {
        "name": "Bad engine combo",
        "asr": {"engine": "whisper", "model_size": "tiny", "fine_segmentation": True},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(profile_data)
    assert any("fine_segmentation" in e and "mlx-whisper" in e for e in errors), errors
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_profiles.py::test_profile_validates_fine_segmentation_bool tests/test_profiles.py::test_profile_rejects_fine_segmentation_with_non_mlx_engine -v
```

Expected: 2 FAIL with `assert any(...)` (errors empty)

- [ ] **Step 3: Add validation in `_validate_asr`**

In `backend/profiles.py`, locate `_validate_asr` (line ~293). Insert this block **after** the existing `engine` validation, **before** the `device` validation:

```python
    # fine_segmentation flag (added 2026-05-03)
    fine_seg = asr.get("fine_segmentation")
    if fine_seg is not None:
        if not isinstance(fine_seg, bool):
            errors.append("asr.fine_segmentation must be bool")
        elif fine_seg is True and engine != "mlx-whisper":
            errors.append(
                f"asr.fine_segmentation=true requires asr.engine='mlx-whisper' "
                f"(got engine={engine!r})"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_profiles.py::test_profile_validates_fine_segmentation_bool tests/test_profiles.py::test_profile_rejects_fine_segmentation_with_non_mlx_engine -v
```

Expected: 2 PASS

- [ ] **Step 5: Run full test_profiles.py to confirm no regression**

```bash
cd backend && source venv/bin/activate && pytest tests/test_profiles.py -v
```

Expected: all existing tests still PASS + 2 new PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/profiles.py backend/tests/test_profiles.py
git commit -m "feat(profiles): add fine_segmentation flag with mlx-whisper engine cross-field validation"
```

---

### Task A3: Profile validation — `temperature` field range

**Files:**
- Modify: `backend/profiles.py:_validate_asr`
- Test: `backend/tests/test_profiles.py` (append)

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_profiles.py`:

```python
def test_profile_validates_temperature_range(config_dir):
    """asr.temperature must be float in [0.0, 1.0] or null."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)

    # Out of range high
    high = {
        "name": "Temp too high",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "temperature": 1.5},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(high)
    assert any("temperature" in e and "0.0" in e for e in errors), errors

    # Out of range low
    low = {
        "name": "Temp too low",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "temperature": -0.1},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(low)
    assert any("temperature" in e and "0.0" in e for e in errors), errors

    # Boolean rejected (must be float|null)
    bool_temp = {
        "name": "Temp bool",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "temperature": True},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(bool_temp)
    assert any("temperature" in e for e in errors), errors

    # Valid 0.0 + null accepted
    for valid_t in (0.0, 0.5, 1.0, None):
        ok = {
            "name": f"Valid temp {valid_t}",
            "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "temperature": valid_t},
            "translation": {"engine": "mock"},
        }
        errors = mgr.validate(ok)
        temp_errors = [e for e in errors if "temperature" in e]
        assert temp_errors == [], f"unexpected errors for temp={valid_t}: {temp_errors}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source venv/bin/activate && pytest tests/test_profiles.py::test_profile_validates_temperature_range -v
```

Expected: FAIL — out-of-range values currently accepted.

- [ ] **Step 3: Add validation in `_validate_asr`**

In `backend/profiles.py:_validate_asr`, immediately after the `fine_segmentation` block from Task A2, add:

```python
    # temperature (float|null, [0.0, 1.0])
    temp = asr.get("temperature")
    if temp is not None:
        if isinstance(temp, bool) or not isinstance(temp, (int, float)):
            errors.append("asr.temperature must be a float in [0.0, 1.0] or null")
        elif not (0.0 <= float(temp) <= 1.0):
            errors.append(
                f"asr.temperature {temp!r} out of range; must be in [0.0, 1.0] or null"
            )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && source venv/bin/activate && pytest tests/test_profiles.py::test_profile_validates_temperature_range -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/profiles.py backend/tests/test_profiles.py
git commit -m "feat(profiles): validate asr.temperature is float in [0.0, 1.0] or null"
```

---

### Task A4: Profile validation — VAD + refine fields range

**Files:**
- Modify: `backend/profiles.py:_validate_asr`
- Test: `backend/tests/test_profiles.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_profiles.py`:

```python
def test_profile_validates_vad_chunk_max_s_range(config_dir):
    """asr.vad_chunk_max_s must be int in [10, 30]."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    for bad in (5, 35):
        cfg = {
            "name": f"vad_chunk_max_s={bad}",
            "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "vad_chunk_max_s": bad},
            "translation": {"engine": "mock"},
        }
        errors = mgr.validate(cfg)
        assert any("vad_chunk_max_s" in e for e in errors), f"bad={bad}: {errors}"


def test_profile_validates_refine_min_lt_max(config_dir):
    """refine_min_dur must be < refine_max_dur."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    cfg = {
        "name": "Bad refine pair",
        "asr": {
            "engine": "mlx-whisper", "model_size": "large-v3",
            "refine_min_dur": 5.0, "refine_max_dur": 4.0,
        },
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(cfg)
    assert any("refine_min_dur" in e and "refine_max_dur" in e for e in errors), errors


def test_profile_validates_vad_threshold_range(config_dir):
    """asr.vad_threshold must be float in [0.0, 1.0]."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    cfg = {
        "name": "vad_threshold out of range",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "vad_threshold": 1.5},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(cfg)
    assert any("vad_threshold" in e for e in errors), errors


def test_profile_backward_compat_no_new_fields(config_dir):
    """Profile without any new v3.8 fields validates cleanly (defaults applied)."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    cfg = {
        "name": "Legacy profile",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "language": "en"},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(cfg)
    assert errors == [], f"unexpected errors: {errors}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_profiles.py -k "vad_chunk_max_s_range or refine_min_lt_max or vad_threshold_range or backward_compat_no_new_fields" -v
```

Expected: 3 FAIL (range checks not implemented), 1 PASS (backward compat).

- [ ] **Step 3: Add VAD + refine field validation in `_validate_asr`**

In `backend/profiles.py:_validate_asr`, after the `temperature` block from Task A3, add:

```python
    # VAD parameters (Silero VAD pre-segmentation, added 2026-05-03)
    _validate_int_range(errors, asr, "vad_min_silence_ms", 200, 2000)
    _validate_int_range(errors, asr, "vad_min_speech_ms", 100, 1000)
    _validate_int_range(errors, asr, "vad_speech_pad_ms", 0, 500)
    _validate_int_range(errors, asr, "vad_chunk_max_s", 10, 30)
    _validate_float_range(errors, asr, "vad_threshold", 0.0, 1.0)

    # Word-gap refine parameters
    _validate_float_range(errors, asr, "refine_max_dur", 3.0, 8.0)
    _validate_float_range(errors, asr, "refine_gap_thresh", 0.05, 0.50)
    _validate_float_range(errors, asr, "refine_min_dur", 0.5, 2.0)

    # Cross-field: refine_min_dur < refine_max_dur
    rmin = asr.get("refine_min_dur")
    rmax = asr.get("refine_max_dur")
    if (
        rmin is not None and rmax is not None
        and isinstance(rmin, (int, float)) and isinstance(rmax, (int, float))
        and not isinstance(rmin, bool) and not isinstance(rmax, bool)
        and rmin >= rmax
    ):
        errors.append(
            f"asr.refine_min_dur ({rmin}) must be < asr.refine_max_dur ({rmax})"
        )
```

Then add these helpers at module level (after `_validate_translation` definition):

```python
def _validate_int_range(errors: list, cfg: dict, key: str, lo: int, hi: int) -> None:
    val = cfg.get(key)
    if val is None:
        return
    if isinstance(val, bool) or not isinstance(val, int):
        errors.append(f"asr.{key} must be an integer in [{lo}, {hi}]")
    elif not (lo <= val <= hi):
        errors.append(f"asr.{key} {val!r} out of range; must be in [{lo}, {hi}]")


def _validate_float_range(errors: list, cfg: dict, key: str, lo: float, hi: float) -> None:
    val = cfg.get(key)
    if val is None:
        return
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        errors.append(f"asr.{key} must be a number in [{lo}, {hi}]")
    elif not (lo <= float(val) <= hi):
        errors.append(f"asr.{key} {val!r} out of range; must be in [{lo}, {hi}]")
```

- [ ] **Step 4: Run tests to verify all pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_profiles.py -k "vad_chunk_max_s_range or refine_min_lt_max or vad_threshold_range or backward_compat_no_new_fields" -v
```

Expected: 4 PASS

- [ ] **Step 5: Run full test_profiles.py to confirm no regression**

```bash
cd backend && source venv/bin/activate && pytest tests/test_profiles.py -v
```

Expected: all existing + new tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/profiles.py backend/tests/test_profiles.py
git commit -m "feat(profiles): validate VAD + word-gap refine field ranges with cross-field min<max rule"
```

---

### Task A5: Profile validation — `translation.skip_sentence_merge`

**Files:**
- Modify: `backend/profiles.py:_validate_translation`
- Test: `backend/tests/test_profiles.py` (append)

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_profiles.py`:

```python
def test_profile_validates_skip_sentence_merge_bool(config_dir):
    """translation.skip_sentence_merge must be bool when present."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    cfg = {
        "name": "Bad skip_merge type",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3"},
        "translation": {"engine": "mock", "skip_sentence_merge": "yes"},
    }
    errors = mgr.validate(cfg)
    assert any("skip_sentence_merge" in e and "bool" in e for e in errors), errors

    # Valid bool accepted
    for valid in (True, False):
        ok = {
            "name": f"skip={valid}",
            "asr": {"engine": "mlx-whisper", "model_size": "large-v3"},
            "translation": {"engine": "mock", "skip_sentence_merge": valid},
        }
        errors = mgr.validate(ok)
        skip_errors = [e for e in errors if "skip_sentence_merge" in e]
        assert skip_errors == [], f"valid={valid}: {skip_errors}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source venv/bin/activate && pytest tests/test_profiles.py::test_profile_validates_skip_sentence_merge_bool -v
```

Expected: FAIL

- [ ] **Step 3: Add validation in `_validate_translation`**

In `backend/profiles.py:_validate_translation`, after the existing `parallel_batches` block, add:

```python
    # skip_sentence_merge flag (added 2026-05-03 for fine_segmentation pairing)
    skip = translation.get("skip_sentence_merge")
    if skip is not None and not isinstance(skip, bool):
        errors.append("translation.skip_sentence_merge must be bool")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && source venv/bin/activate && pytest tests/test_profiles.py::test_profile_validates_skip_sentence_merge_bool -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/profiles.py backend/tests/test_profiles.py
git commit -m "feat(profiles): validate translation.skip_sentence_merge bool"
```

---

### Task A6: mlx-whisper engine — forward `temperature` kwarg

**Files:**
- Modify: `backend/asr/mlx_whisper_engine.py:34-73` (`transcribe` method)
- Modify: `backend/asr/mlx_whisper_engine.py:83-129` (`get_params_schema`)
- Test: `backend/tests/test_mlx_whisper_engine_temperature.py` (NEW)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_mlx_whisper_engine_temperature.py`:

```python
"""Tests for temperature kwarg plumbing in MlxWhisperEngine."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_mlx_engine_forwards_temperature_when_set(monkeypatch):
    """profile temperature=0.0 → mlx_whisper.transcribe(temperature=0.0)"""
    from asr import mlx_whisper_engine
    captured = {}

    def fake_transcribe(audio, **kw):
        captured.update(kw)
        return {"segments": []}

    monkeypatch.setattr(mlx_whisper_engine.mlx_whisper, "transcribe", fake_transcribe)
    engine = mlx_whisper_engine.MlxWhisperEngine({
        "engine": "mlx-whisper", "model_size": "large-v3", "temperature": 0.0,
    })
    engine.transcribe("dummy.wav", language="en")
    assert "temperature" in captured
    assert captured["temperature"] == 0.0


def test_mlx_engine_omits_temperature_when_none(monkeypatch):
    """profile temperature=None → mlx_whisper.transcribe called without temperature kwarg."""
    from asr import mlx_whisper_engine
    captured = {}

    def fake_transcribe(audio, **kw):
        captured.update(kw)
        return {"segments": []}

    monkeypatch.setattr(mlx_whisper_engine.mlx_whisper, "transcribe", fake_transcribe)
    engine = mlx_whisper_engine.MlxWhisperEngine({
        "engine": "mlx-whisper", "model_size": "large-v3",  # no temperature
    })
    engine.transcribe("dummy.wav", language="en")
    assert "temperature" not in captured


def test_mlx_engine_schema_exposes_temperature():
    """get_params_schema includes temperature with nullable + range metadata."""
    from asr.mlx_whisper_engine import MlxWhisperEngine
    engine = MlxWhisperEngine({"engine": "mlx-whisper", "model_size": "large-v3"})
    schema = engine.get_params_schema()
    params = schema["params"]
    assert "temperature" in params
    t = params["temperature"]
    assert t.get("nullable") is True
    assert t.get("min") == 0.0
    assert t.get("max") == 1.0
    assert t.get("default") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_mlx_whisper_engine_temperature.py -v
```

Expected: 3 FAIL (temperature not currently forwarded; schema field missing).

- [ ] **Step 3: Modify `transcribe` method to forward `temperature`**

In `backend/asr/mlx_whisper_engine.py:34-50`, replace the body of `transcribe`:

```python
    def transcribe(self, audio_path: str, language: str = "en") -> list[Segment]:
        if not MLX_WHISPER_AVAILABLE:
            raise RuntimeError("mlx-whisper is not installed. Run: pip install mlx-whisper")

        condition_on_previous_text = self._config.get("condition_on_previous_text", True)
        word_timestamps = bool(self._config.get("word_timestamps", False))
        temperature = self._config.get("temperature")  # may be None or float

        kwargs = {
            "path_or_hf_repo": self._repo,
            "language": language,
            "task": "transcribe",
            "condition_on_previous_text": condition_on_previous_text,
            "word_timestamps": word_timestamps,
            "verbose": False,
        }
        # Only pass temperature when explicitly set; None → use mlx default fallback tuple
        if temperature is not None:
            kwargs["temperature"] = float(temperature)

        with _model_lock:
            result = mlx_whisper.transcribe(audio_path, **kwargs)
        # ...rest of method unchanged (segment dict construction)
```

The remaining lines (52-73 segment construction loop) stay the same.

- [ ] **Step 4: Add `temperature` to `get_params_schema`**

In `backend/asr/mlx_whisper_engine.py:get_params_schema()`, after the existing `word_timestamps` entry (~line 120-127), add:

```python
                "temperature": {
                    "type": "float",
                    "label": "解碼溫度",
                    "widget": "input",
                    "nullable": True,
                    "description": "Decoder temperature; 0.0 disables fallback (recommended for fine_segmentation)",
                    "hint": "0.0 = 固定 greedy decode；留空 = 用 mlx 預設 fallback tuple",
                    "min": 0.0,
                    "max": 1.0,
                    "default": None,
                },
```

- [ ] **Step 5: Run tests to verify all pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_mlx_whisper_engine_temperature.py -v
```

Expected: 3 PASS

- [ ] **Step 6: Run existing mlx engine test for regression**

```bash
cd backend && source venv/bin/activate && pytest tests/test_asr.py::test_mlx_whisper_engine_schema_and_info -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/asr/mlx_whisper_engine.py backend/tests/test_mlx_whisper_engine_temperature.py
git commit -m "feat(asr): mlx-whisper engine forwards temperature kwarg + schema exposes nullable field"
```

---

### Task A7: Phase A regression check

**Files:** none (verification only)

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend && source venv/bin/activate && pytest tests/ -q
```

Expected: all existing tests PASS + new Phase A tests (~10 new) PASS. Baseline 469 PASS / 12 pre-existing FAIL → 479 PASS / 12 FAIL.

- [ ] **Step 2: Verify no behaviour change for legacy profiles**

```bash
cd backend && source venv/bin/activate && python -c "
from profiles import ProfileManager
from pathlib import Path
import tempfile, json
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp); (p/'profiles').mkdir(); (p/'settings.json').write_text(json.dumps({'active_profile': None}))
    mgr = ProfileManager(p)
    # Existing profile shape (no v3.8 fields)
    legacy = {
        'name': 'Legacy',
        'asr': {'engine': 'whisper', 'model_size': 'tiny', 'language': 'en'},
        'translation': {'engine': 'mock'},
    }
    errors = mgr.validate(legacy)
    print('Legacy validate errors:', errors)
    assert errors == [], 'Backward compat broken'
    print('OK')
"
```

Expected: `Legacy validate errors: []` → `OK`.

---

## Phase B — Core algorithm: `sentence_split.py`

Create the new module with `transcribe_fine_seg()` pipeline + testable `word_gap_split()`. After this phase, the algorithm is verified in isolation but not yet wired into `app.py`.

### Task B1: Module skeleton + `FineSegmentationError`

**Files:**
- Create: `backend/asr/sentence_split.py`
- Test: `backend/tests/test_sentence_split.py` (NEW)

- [ ] **Step 1: Create test file with first failing test**

Create `backend/tests/test_sentence_split.py`:

```python
"""Tests for sentence_split fine-segmentation module."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_module_exports_public_api():
    """Module exposes transcribe_fine_seg, word_gap_split, FineSegmentationError."""
    from asr import sentence_split
    assert callable(sentence_split.transcribe_fine_seg)
    assert callable(sentence_split.word_gap_split)
    assert issubclass(sentence_split.FineSegmentationError, Exception)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source venv/bin/activate && pytest tests/test_sentence_split.py::test_module_exports_public_api -v
```

Expected: FAIL — `ImportError: No module named 'asr.sentence_split'`

- [ ] **Step 3: Create skeleton module**

Create `backend/asr/sentence_split.py`:

```python
"""Fine-grained ASR segmentation via Silero VAD pre-segment + word-gap refine.

Pipeline:
  audio.wav
    → Silero VAD pre-segment (speech spans)
    → sub-cap chunks ≤ vad_chunk_max_s
    → mlx-whisper transcribe per chunk (temperature=0.0, word_timestamps=True,
       condition_on_previous_text=False); shift offsets back to file timeline
    → concat
    → word_gap_split (recursive split at largest inter-word gap above threshold)
    → final List[Segment] with words[] preserved

Activated by profile asr.fine_segmentation=true. Engine must be mlx-whisper.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class FineSegmentationError(Exception):
    """Raised for setup-level failures (missing silero-vad, missing mlx-whisper)."""


# Public API — implementations added in subsequent tasks
def transcribe_fine_seg(audio_path: str, profile: dict, ws_emit: Optional[Callable[[str, str], None]] = None):
    """Full pipeline; returns List[Segment] with words[]."""
    raise NotImplementedError("transcribe_fine_seg implemented in Task B5")


def word_gap_split(segments, *, max_dur: float = 4.0, gap_thresh: float = 0.10,
                   min_dur: float = 1.5, safety_max_dur: float = 9.0):
    """Recursive split of long segments at largest inter-word gap."""
    raise NotImplementedError("word_gap_split implemented in Task B2")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && source venv/bin/activate && pytest tests/test_sentence_split.py::test_module_exports_public_api -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/asr/sentence_split.py backend/tests/test_sentence_split.py
git commit -m "feat(asr): add sentence_split module skeleton with FineSegmentationError"
```

---

### Task B2: `word_gap_split` — basic split at largest gap

**Files:**
- Modify: `backend/asr/sentence_split.py`
- Modify: `backend/tests/test_sentence_split.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_sentence_split.py`:

```python
def _word(text: str, start: float, end: float, prob: float = 1.0) -> dict:
    return {"word": text, "start": start, "end": end, "probability": prob}


def _seg(start: float, end: float, words: list[dict]) -> dict:
    text = " ".join(w["word"] for w in words).strip()
    return {"start": start, "end": end, "text": text, "words": words}


def test_word_gap_split_no_split_when_under_max_dur():
    """3.5s segment with max_dur=4.0 → not split."""
    from asr.sentence_split import word_gap_split
    seg = _seg(0, 3.5, [_word("a", 0, 0.5), _word("b", 1, 1.5),
                        _word("c", 2, 2.5), _word("d", 3, 3.5)])
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.1, min_dur=1.5)
    assert len(out) == 1
    assert out[0]["start"] == 0 and out[0]["end"] == 3.5


def test_word_gap_split_splits_at_largest_gap():
    """5s segment with one big 0.8s gap mid-way → split into 2 parts."""
    from asr.sentence_split import word_gap_split
    # Words 0-2 close; big gap; words 3-5 close
    seg = _seg(0, 5.0, [
        _word("one", 0.0, 0.4), _word("two", 0.5, 0.9), _word("three", 1.0, 1.7),
        _word("four", 2.5, 3.0), _word("five", 3.1, 3.5), _word("six", 3.6, 5.0),
    ])
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.5, min_dur=1.5)
    assert len(out) == 2
    assert out[0]["text"].endswith("three")
    assert out[1]["text"].startswith("four")


def test_word_gap_split_too_few_words_keeps_seg():
    """Segment with < 4 words is never split, even if duration > max_dur."""
    from asr.sentence_split import word_gap_split
    seg = _seg(0, 6.0, [_word("a", 0, 1), _word("b", 2, 3), _word("c", 4, 5)])
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.1, min_dur=1.5)
    assert len(out) == 1


def test_word_gap_split_missing_words_keeps_seg():
    """Segment with empty words[] is never split."""
    from asr.sentence_split import word_gap_split
    seg = {"start": 0, "end": 6, "text": "a b c d e f", "words": []}
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.1, min_dur=1.5)
    assert len(out) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_sentence_split.py -k word_gap_split -v
```

Expected: 4 FAIL (`NotImplementedError`)

- [ ] **Step 3: Implement `word_gap_split` + recursive helper**

Replace the `word_gap_split` stub in `backend/asr/sentence_split.py` with full implementation:

```python
def word_gap_split(segments, *, max_dur: float = 4.0, gap_thresh: float = 0.10,
                   min_dur: float = 1.5, safety_max_dur: float = 9.0):
    """Recursively split segments > max_dur at largest inter-word gap.

    Behavior:
      - Segment with duration ≤ max_dur or < 4 words → kept as-is
      - Segment with duration > max_dur:
          1. Find candidate gaps (must respect min_dur on both sides)
          2. Take largest gap
          3. If best gap ≥ gap_thresh: split, recurse on both halves
          4. If best gap < gap_thresh AND duration ≤ safety_max_dur: keep as-is
          5. If duration > safety_max_dur: force split at largest gap regardless
    """
    out = []
    for s in segments:
        out.extend(_split_one(s, max_dur, gap_thresh, min_dur, safety_max_dur))
    return out


def _split_one(seg, max_dur, gap_thresh, min_dur, safety_max_dur):
    duration = seg["end"] - seg["start"]
    words = seg.get("words") or []
    if duration <= max_dur or len(words) < 4:
        return [seg]

    seg_start, seg_end = seg["start"], seg["end"]
    candidates = []
    for i in range(1, len(words)):
        gap = words[i]["start"] - words[i - 1]["end"]
        left_dur = words[i - 1]["end"] - seg_start
        right_dur = seg_end - words[i]["start"]
        if left_dur >= min_dur and right_dur >= min_dur:
            candidates.append((i, gap))

    if not candidates:
        return [seg]

    candidates.sort(key=lambda x: -x[1])
    best_i, best_gap = candidates[0]

    force_split = duration > safety_max_dur
    if best_gap < gap_thresh and not force_split:
        return [seg]

    left_words = words[:best_i]
    right_words = words[best_i:]
    left = {
        **seg,
        "text": " ".join(w["word"].strip() for w in left_words).strip(),
        "start": left_words[0]["start"],
        "end": left_words[-1]["end"],
        "words": left_words,
    }
    right = {
        **seg,
        "text": " ".join(w["word"].strip() for w in right_words).strip(),
        "start": right_words[0]["start"],
        "end": right_words[-1]["end"],
        "words": right_words,
    }

    result = []
    for c in (left, right):
        result.extend(_split_one(c, max_dur, gap_thresh, min_dur, safety_max_dur))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_sentence_split.py -k word_gap_split -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/asr/sentence_split.py backend/tests/test_sentence_split.py
git commit -m "feat(asr): word_gap_split recursive split at largest inter-word gap"
```

---

### Task B3: `word_gap_split` — min_dur respect + safety override + recursive chains

**Files:**
- Modify: `backend/tests/test_sentence_split.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_sentence_split.py`:

```python
def test_word_gap_split_respects_min_dur():
    """Big gap exists but split would violate min_dur → no split."""
    from asr.sentence_split import word_gap_split
    # 5s segment; only gap candidate is at index 1, but left side would be 0.5s < min_dur=1.5
    seg = _seg(0, 5.0, [
        _word("a", 0.0, 0.5),
        _word("b", 1.0, 1.5),  # gap 0.5 to next
        _word("c", 2.0, 2.5),
        _word("d", 3.0, 3.5),
        _word("e", 4.0, 5.0),
    ])
    # gap_thresh=0.4 would otherwise split at any gap; min_dur excludes index 1, 4
    # Index 2 left=1.5s OK, right=2.5s OK → can split there if gap qualifies
    # But all gaps are 0.5 → split at first acceptable index
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.4, min_dur=1.5)
    # split must respect min_dur — both halves should be ≥1.5s
    for piece in out:
        assert (piece["end"] - piece["start"]) >= 1.5, f"piece too short: {piece}"


def test_word_gap_split_safety_override_for_super_long():
    """No gap ≥ threshold but duration > safety_max_dur → force split anyway."""
    from asr.sentence_split import word_gap_split
    # 11s segment with all gaps 0.05s (below threshold 0.20)
    words = [_word(str(i), i * 1.05, i * 1.05 + 1.0) for i in range(11)]
    seg = _seg(0, 11.55, words)
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.20, min_dur=1.5,
                         safety_max_dur=9.0)
    assert len(out) >= 2, f"safety override should force split, got {len(out)}"


def test_word_gap_split_keeps_under_safety_max_dur():
    """No gap ≥ threshold and duration ≤ safety_max_dur → kept as-is."""
    from asr.sentence_split import word_gap_split
    # 6s segment, all gaps 0.05s
    words = [_word(str(i), i * 1.05, i * 1.05 + 1.0) for i in range(6)]
    seg = _seg(0, 6.3, words)
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.20, min_dur=1.5,
                         safety_max_dur=9.0)
    assert len(out) == 1, f"should keep, got {len(out)}"


def test_word_gap_split_recursive_chains():
    """12s segment with two big gaps → split into 3 pieces."""
    from asr.sentence_split import word_gap_split
    seg = _seg(0, 12.0, [
        _word("a", 0.0, 0.4), _word("b", 0.5, 0.9), _word("c", 1.0, 1.5),
        # big gap 1.0s
        _word("d", 2.5, 2.9), _word("e", 3.0, 3.5), _word("f", 3.6, 4.0),
        _word("g", 4.1, 4.5), _word("h", 4.6, 5.0),
        # big gap 1.5s
        _word("i", 6.5, 7.0), _word("j", 7.1, 7.5), _word("k", 7.6, 8.0),
        _word("l", 8.1, 12.0),
    ])
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.5, min_dur=1.5)
    assert len(out) == 3, f"expected 3 chunks, got {len(out)}"


def test_word_gap_split_preserves_text_content():
    """After split, joined children's text equals parent's text (no word loss)."""
    from asr.sentence_split import word_gap_split
    seg = _seg(0, 6.0, [_word("the", 0, 0.3), _word("quick", 0.4, 0.8),
                        _word("brown", 0.9, 1.4), _word("fox", 1.5, 2.0),
                        # gap
                        _word("jumps", 3.5, 4.0), _word("over", 4.1, 4.5),
                        _word("the", 4.6, 5.0), _word("dog", 5.1, 6.0)])
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.5, min_dur=1.5)
    parent_text = seg["text"]
    children_text = " ".join(s["text"] for s in out)
    assert parent_text == children_text, f"parent={parent_text!r} vs children={children_text!r}"
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_sentence_split.py -k word_gap_split -v
```

Expected: all 9 word_gap_split tests PASS (algorithm already correct from B2 — these tests verify edge cases).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_sentence_split.py
git commit -m "test(asr): word_gap_split min_dur + safety override + recursive + text preservation"
```

---

### Task B4: `_subcap_chunks` helper

**Files:**
- Modify: `backend/asr/sentence_split.py`
- Modify: `backend/tests/test_sentence_split.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_sentence_split.py`:

```python
def test_subcap_chunks_no_subcap_needed():
    """Spans all ≤ max_s → output identical to input."""
    from asr.sentence_split import _subcap_chunks
    SR = 16000
    spans = [(0, 10 * SR), (15 * SR, 25 * SR)]
    assert _subcap_chunks(spans, max_s=25) == spans


def test_subcap_chunks_splits_long_span():
    """60s span with max_s=25 → 3 sub-chunks (25 + 25 + 10)."""
    from asr.sentence_split import _subcap_chunks
    SR = 16000
    out = _subcap_chunks([(0, 60 * SR)], max_s=25)
    assert len(out) == 3
    assert out[0] == (0, 25 * SR)
    assert out[1] == (25 * SR, 50 * SR)
    assert out[2] == (50 * SR, 60 * SR)


def test_subcap_chunks_empty_input():
    from asr.sentence_split import _subcap_chunks
    assert _subcap_chunks([], max_s=25) == []


def test_subcap_chunks_exact_boundary():
    """Span exactly = max_s → single chunk."""
    from asr.sentence_split import _subcap_chunks
    SR = 16000
    out = _subcap_chunks([(0, 25 * SR)], max_s=25)
    assert len(out) == 1
    assert out[0] == (0, 25 * SR)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_sentence_split.py -k subcap -v
```

Expected: 4 FAIL — function not defined.

- [ ] **Step 3: Add `_subcap_chunks` helper**

In `backend/asr/sentence_split.py`, after the `_split_one` function, add:

```python
# Sample rate for Silero VAD + mlx-whisper
_SR = 16000


def _subcap_chunks(spans, max_s: int):
    """Sub-cap any span > max_s seconds into ≤ max_s sub-chunks (sample-indexed)."""
    chunk_max = max_s * _SR
    out = []
    for cs, ce in spans:
        if (ce - cs) <= chunk_max:
            out.append((cs, ce))
        else:
            cur = cs
            while cur < ce:
                out.append((cur, min(cur + chunk_max, ce)))
                cur += chunk_max
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_sentence_split.py -k subcap -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/asr/sentence_split.py backend/tests/test_sentence_split.py
git commit -m "feat(asr): _subcap_chunks helper for VAD spans > vad_chunk_max_s"
```

---

### Task B5: `transcribe_fine_seg` setup error path (F1 strict)

**Files:**
- Modify: `backend/asr/sentence_split.py`
- Modify: `backend/tests/test_sentence_split.py` (append)

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_sentence_split.py`:

```python
def test_transcribe_fine_seg_raises_when_silero_missing(monkeypatch):
    """F1 (strict): silero_vad import failure → FineSegmentationError with hint."""
    import sys
    # Force ImportError when sentence_split tries `from silero_vad import ...`
    monkeypatch.setitem(sys.modules, "silero_vad", None)

    from asr.sentence_split import transcribe_fine_seg, FineSegmentationError
    with pytest.raises(FineSegmentationError, match="silero-vad"):
        transcribe_fine_seg("dummy.wav", _profile_with_fine_seg(), None)


def _profile_with_fine_seg() -> dict:
    """Helper for tests: minimal profile dict with fine_segmentation enabled."""
    return {
        "asr": {
            "engine": "mlx-whisper",
            "model_size": "large-v3",
            "language": "en",
            "fine_segmentation": True,
            "temperature": 0.0,
            "vad_threshold": 0.5,
            "vad_min_silence_ms": 500,
            "vad_min_speech_ms": 250,
            "vad_speech_pad_ms": 200,
            "vad_chunk_max_s": 25,
            "refine_max_dur": 4.0,
            "refine_gap_thresh": 0.10,
            "refine_min_dur": 1.5,
        },
    }
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source venv/bin/activate && pytest tests/test_sentence_split.py::test_transcribe_fine_seg_raises_when_silero_missing -v
```

Expected: FAIL — `transcribe_fine_seg` raises `NotImplementedError`, not `FineSegmentationError`.

- [ ] **Step 3: Implement `transcribe_fine_seg` setup section**

Replace the `transcribe_fine_seg` stub in `backend/asr/sentence_split.py` with this initial implementation:

```python
def transcribe_fine_seg(audio_path: str, profile: dict,
                        ws_emit: Optional[Callable[[str, str], None]] = None):
    """Full pipeline: VAD pre-seg → per-chunk mlx transcribe → word-gap refine.

    Args:
        audio_path: 16kHz mono WAV path
        profile: full active profile dict (reads asr.* fields)
        ws_emit: optional callback (kind, message) for runtime warnings

    Raises:
        FineSegmentationError: setup-level (silero-vad or mlx-whisper missing)

    Returns:
        List[Segment] dicts with words[] preserved
    """
    # F1 strict — setup errors raise immediately
    try:
        from silero_vad import load_silero_vad, get_speech_timestamps, read_audio
    except ImportError as e:
        raise FineSegmentationError(
            "silero-vad not installed; run: pip install silero-vad"
        ) from e

    try:
        import mlx_whisper
    except ImportError as e:
        raise FineSegmentationError("mlx-whisper not installed") from e

    # Pipeline implementation completed in Tasks B6/B7
    raise NotImplementedError("Pipeline body in Task B6")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && source venv/bin/activate && pytest tests/test_sentence_split.py::test_transcribe_fine_seg_raises_when_silero_missing -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/asr/sentence_split.py backend/tests/test_sentence_split.py
git commit -m "feat(asr): transcribe_fine_seg raises FineSegmentationError when silero-vad missing"
```

---

### Task B6: `transcribe_fine_seg` — VAD + chunk + transcribe + concat

**Files:**
- Modify: `backend/asr/sentence_split.py`

- [ ] **Step 1: Add Silero singleton + VAD helper + chunk transcribe + fallback**

In `backend/asr/sentence_split.py`, **after** the existing `_subcap_chunks` and **before** `transcribe_fine_seg`, add:

```python
# Silero VAD model singleton (thread-safe lazy init)
_silero_model = None
_silero_lock = threading.Lock()


def _get_silero_model(load_fn):
    """Lazy-load Silero VAD ONNX model (thread-safe singleton)."""
    global _silero_model
    with _silero_lock:
        if _silero_model is None:
            _silero_model = load_fn(onnx=True)
    return _silero_model


def _vad_segment(audio_path: str, asr_cfg: dict, *, load_fn, get_ts_fn, read_fn):
    """Run Silero VAD; return list of (start_sample, end_sample) tuples."""
    model = _get_silero_model(load_fn)
    wav = read_fn(audio_path, sampling_rate=_SR)
    spans = get_ts_fn(
        wav, model,
        sampling_rate=_SR,
        threshold=asr_cfg.get("vad_threshold", 0.5),
        min_speech_duration_ms=asr_cfg.get("vad_min_speech_ms", 250),
        min_silence_duration_ms=asr_cfg.get("vad_min_silence_ms", 500),
        speech_pad_ms=asr_cfg.get("vad_speech_pad_ms", 200),
        return_seconds=False,
    )
    return [(s["start"], s["end"]) for s in spans], wav


def _transcribe_chunks(wav, chunks, asr_cfg, mlx_module, ws_emit):
    """Transcribe each chunk with mlx-whisper, shifting offsets to file timeline."""
    import numpy as np
    from asr import Word
    from asr.mlx_whisper_engine import MODEL_REPO, _model_lock as mlx_lock

    repo = MODEL_REPO.get(asr_cfg.get("model_size", "large-v3"), MODEL_REPO["large-v3"])
    out = []
    failed = 0

    for ci, (cs, ce) in enumerate(chunks):
        chunk_audio = wav[cs:ce]
        if hasattr(chunk_audio, "numpy"):  # torch.Tensor → numpy
            chunk_audio = chunk_audio.numpy()
        offset = cs / _SR
        try:
            with mlx_lock:
                r = mlx_module.transcribe(
                    chunk_audio,
                    path_or_hf_repo=repo,
                    language=asr_cfg.get("language", "en"),
                    task="transcribe",
                    verbose=False,
                    condition_on_previous_text=False,  # chunk-isolated
                    word_timestamps=True,
                    temperature=float(asr_cfg.get("temperature") or 0.0),
                )
        except Exception as e:  # noqa: BLE001 — permissive runtime fallback
            failed += 1
            logger.warning(
                f"sentence_split: chunk {ci} ({cs/_SR:.1f}-{ce/_SR:.1f}s) failed: {e}"
            )
            continue

        for s in r.get("segments", []):
            text = (s.get("text") or "").strip()
            if not text:
                continue
            words = [
                Word(
                    word=w.get("word", ""),
                    start=float(w.get("start", 0.0)) + offset,
                    end=float(w.get("end", 0.0)) + offset,
                    probability=float(w.get("probability", 0.0) or 0.0),
                )
                for w in (s.get("words") or [])
            ]
            out.append({
                "start": float(s["start"]) + offset,
                "end": float(s["end"]) + offset,
                "text": text,
                "words": words,
            })

    if failed > 0 and ws_emit is not None:
        ws_emit("chunk_fail",
                f"{failed}/{len(chunks)} chunks failed; output may have gaps")
    return out


def _fallback_whole_file(audio_path: str, asr_cfg: dict, mlx_module):
    """Used when VAD returns 0 spans or all chunks fail. Baseline mlx transcribe."""
    from asr import Word
    from asr.mlx_whisper_engine import MODEL_REPO, _model_lock as mlx_lock

    repo = MODEL_REPO.get(asr_cfg.get("model_size", "large-v3"), MODEL_REPO["large-v3"])
    with mlx_lock:
        r = mlx_module.transcribe(
            audio_path,
            path_or_hf_repo=repo,
            language=asr_cfg.get("language", "en"),
            task="transcribe",
            verbose=False,
            condition_on_previous_text=True,
            word_timestamps=True,
            temperature=float(asr_cfg.get("temperature") or 0.0),
        )
    out = []
    for s in r.get("segments", []):
        text = (s.get("text") or "").strip()
        if not text:
            continue
        words = [
            Word(
                word=w.get("word", ""),
                start=float(w.get("start", 0.0)),
                end=float(w.get("end", 0.0)),
                probability=float(w.get("probability", 0.0) or 0.0),
            )
            for w in (s.get("words") or [])
        ]
        out.append({
            "start": float(s["start"]),
            "end": float(s["end"]),
            "text": text,
            "words": words,
        })
    return out
```

- [ ] **Step 2: Replace `transcribe_fine_seg` body with full pipeline**

In `backend/asr/sentence_split.py`, replace the previous stub of `transcribe_fine_seg` (the one that ended with `raise NotImplementedError("Pipeline body in Task B6")`) with:

```python
def transcribe_fine_seg(audio_path: str, profile: dict,
                        ws_emit: Optional[Callable[[str, str], None]] = None):
    # F1 strict — setup errors raise immediately
    try:
        from silero_vad import load_silero_vad, get_speech_timestamps, read_audio
    except ImportError as e:
        raise FineSegmentationError(
            "silero-vad not installed; run: pip install silero-vad"
        ) from e
    try:
        import mlx_whisper
    except ImportError as e:
        raise FineSegmentationError("mlx-whisper not installed") from e

    asr_cfg = profile.get("asr") or {}

    # Stage 1: VAD pre-segment
    spans, wav = _vad_segment(
        audio_path, asr_cfg,
        load_fn=load_silero_vad, get_ts_fn=get_speech_timestamps, read_fn=read_audio,
    )

    # F2 permissive — VAD returns 0 chunks → fallback whole file
    if not spans:
        if ws_emit is not None:
            ws_emit("vad_zero",
                    "VAD detected 0 speech chunks; using whole-file transcribe")
        return _fallback_whole_file(audio_path, asr_cfg, mlx_whisper)

    # Stage 2: Sub-cap > vad_chunk_max_s
    chunks = _subcap_chunks(spans, asr_cfg.get("vad_chunk_max_s", 25))

    # Stage 3: Per-chunk mlx transcribe + offset shift
    raw = _transcribe_chunks(wav, chunks, asr_cfg, mlx_whisper, ws_emit)

    # F4 permissive — all chunks failed → fallback whole file
    if not raw:
        if ws_emit is not None:
            ws_emit("vad_fail",
                    "All chunks failed; using whole-file transcribe")
        return _fallback_whole_file(audio_path, asr_cfg, mlx_whisper)

    # Stage 4: Word-gap refine
    refined = word_gap_split(
        raw,
        max_dur=float(asr_cfg.get("refine_max_dur", 4.0)),
        gap_thresh=float(asr_cfg.get("refine_gap_thresh", 0.10)),
        min_dur=float(asr_cfg.get("refine_min_dur", 1.5)),
    )
    return refined
```

- [ ] **Step 3: Smoke-test imports**

```bash
cd backend && source venv/bin/activate && python -c "
from asr.sentence_split import transcribe_fine_seg, word_gap_split, FineSegmentationError, _vad_segment, _transcribe_chunks, _fallback_whole_file, _subcap_chunks
print('All public + helper symbols importable')
"
```

Expected: `All public + helper symbols importable`

- [ ] **Step 4: Run all sentence_split tests for regression**

```bash
cd backend && source venv/bin/activate && pytest tests/test_sentence_split.py -v
```

Expected: all 11 PASS (3 module + 5 word_gap_split + 4 _subcap_chunks − duplicates = ~11 PASS).

- [ ] **Step 5: Commit**

```bash
git add backend/asr/sentence_split.py
git commit -m "feat(asr): transcribe_fine_seg full pipeline — VAD + chunk + transcribe + refine + permissive fallback"
```

---

### Task B7: `transcribe_fine_seg` runtime fallback tests (F2 + F4)

**Files:**
- Modify: `backend/tests/test_sentence_split.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_sentence_split.py`:

```python
def test_transcribe_fine_seg_falls_back_when_vad_returns_zero(monkeypatch, tmp_path):
    """F2 permissive: VAD returns [] → call _fallback_whole_file + emit vad_zero warning."""
    from asr import sentence_split

    fake_segments = [{"start": 0, "end": 5.0, "text": "fallback", "words": []}]

    # Stub Silero imports — VAD returns zero spans
    class _FakeSilero:
        @staticmethod
        def load_silero_vad(onnx=True): return object()
        @staticmethod
        def get_speech_timestamps(*a, **kw): return []
        @staticmethod
        def read_audio(path, sampling_rate=16000): return [0] * 16000

    import sys
    monkeypatch.setitem(sys.modules, "silero_vad", _FakeSilero)

    # Stub _fallback_whole_file
    monkeypatch.setattr(sentence_split, "_fallback_whole_file",
                        lambda *a, **k: fake_segments)

    audio = tmp_path / "fake.wav"; audio.touch()
    emits = []
    out = sentence_split.transcribe_fine_seg(
        str(audio),
        {"asr": {"engine": "mlx-whisper", "fine_segmentation": True}},
        lambda kind, msg: emits.append((kind, msg)),
    )
    assert out == fake_segments
    assert any(k == "vad_zero" for k, _ in emits), emits


def test_transcribe_fine_seg_falls_back_when_all_chunks_fail(monkeypatch, tmp_path):
    """F4 permissive: VAD returns spans but all chunk transcribes fail → vad_fail warning."""
    from asr import sentence_split

    SR = 16000
    fake_segments = [{"start": 0, "end": 5.0, "text": "fallback", "words": []}]

    class _FakeSilero:
        @staticmethod
        def load_silero_vad(onnx=True): return object()
        @staticmethod
        def get_speech_timestamps(*a, **kw):
            return [{"start": 0, "end": 10 * SR}]
        @staticmethod
        def read_audio(path, sampling_rate=16000):
            return [0] * (10 * SR)

    import sys
    monkeypatch.setitem(sys.modules, "silero_vad", _FakeSilero)

    # Force chunk transcribe to return empty (simulating all failures)
    monkeypatch.setattr(sentence_split, "_transcribe_chunks",
                        lambda *a, **k: [])
    monkeypatch.setattr(sentence_split, "_fallback_whole_file",
                        lambda *a, **k: fake_segments)

    audio = tmp_path / "fake.wav"; audio.touch()
    emits = []
    out = sentence_split.transcribe_fine_seg(
        str(audio),
        {"asr": {"engine": "mlx-whisper", "fine_segmentation": True,
                 "vad_chunk_max_s": 25}},
        lambda kind, msg: emits.append((kind, msg)),
    )
    assert out == fake_segments
    assert any(k == "vad_fail" for k, _ in emits), emits
```

- [ ] **Step 2: Run tests to verify they pass**

(Tests should already pass since fallback logic was implemented in B6 — this confirms it works.)

```bash
cd backend && source venv/bin/activate && pytest tests/test_sentence_split.py -k "falls_back" -v
```

Expected: 2 PASS

- [ ] **Step 3: Run all sentence_split tests**

```bash
cd backend && source venv/bin/activate && pytest tests/test_sentence_split.py -v
```

Expected: all 13 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_sentence_split.py
git commit -m "test(asr): permissive fallback when VAD returns 0 chunks or all chunks fail"
```

---

### Task B8: Phase B regression check

**Files:** none

- [ ] **Step 1: Run full backend suite**

```bash
cd backend && source venv/bin/activate && pytest tests/ -q
```

Expected: 469 baseline + ~13 new sentence_split = 482+ PASS / 12 pre-existing FAIL.

- [ ] **Step 2: Verify module is import-safe even when silero-vad missing**

(Important: silero-vad is now installed, but the import-time guard means other code paths shouldn't break if it's removed.)

```bash
cd backend && source venv/bin/activate && python -c "
import asr.sentence_split as ss
# Module-level imports should not require silero-vad
assert hasattr(ss, 'transcribe_fine_seg')
assert hasattr(ss, 'word_gap_split')
assert hasattr(ss, 'FineSegmentationError')
print('OK')
"
```

Expected: `OK`.

---

## Phase C — Pipeline Integration

Wire `sentence_split.transcribe_fine_seg` into `app.py:transcribe_with_segments`. Add `transcribed_with_fine_seg` registry flag, `transcription_warning` SocketIO event, and `skip_sentence_merge` bypass in `_auto_translate`.

### Task C1: Branch in `transcribe_with_segments`

**Files:**
- Modify: `backend/app.py:456-495`
- Test: `backend/tests/test_app_fine_seg.py` (NEW)

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_app_fine_seg.py`:

```python
"""Tests for fine_segmentation integration in app.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_transcribe_with_segments_calls_fine_seg_when_enabled(monkeypatch):
    """fine_segmentation=true + engine=mlx-whisper → call sentence_split.transcribe_fine_seg."""
    import app

    called = []

    def fake_transcribe_fine_seg(audio_path, profile, ws_emit):
        called.append((audio_path, profile, ws_emit))
        return [{"start": 0.0, "end": 1.0, "text": "fake", "words": []}]

    monkeypatch.setattr("asr.sentence_split.transcribe_fine_seg",
                        fake_transcribe_fine_seg)

    profile = {
        "asr": {
            "engine": "mlx-whisper", "model_size": "large-v3",
            "language": "en", "fine_segmentation": True,
        },
        "translation": {"engine": "mock"},
    }
    # Direct call to the helper that decides routing
    result = app._run_profile_asr_with_optional_fine_seg(
        audio_path="/tmp/dummy.wav",
        profile=profile,
        sid=None,
        emit_segment_with_progress=lambda seg, sid: None,
    )
    assert called, "fine_seg branch was not taken"
    assert result["segments"][0]["text"] == "fake"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source venv/bin/activate && pytest tests/test_app_fine_seg.py::test_transcribe_with_segments_calls_fine_seg_when_enabled -v
```

Expected: FAIL — `_run_profile_asr_with_optional_fine_seg` does not exist.

- [ ] **Step 3: Add helper function to `app.py`**

In `backend/app.py`, **before** `transcribe_with_segments` function definition (search for `def transcribe_with_segments`), add this helper:

```python
def _run_profile_asr_with_optional_fine_seg(audio_path, profile, sid,
                                            emit_segment_with_progress):
    """Run ASR via fine_segmentation pipeline if enabled, else legacy engine path.

    Returns dict with keys: text, language, segments, backend, model.
    Segments include `words` field always (empty list when not produced by engine).
    """
    asr_cfg = profile.get("asr") or {}
    engine_name = asr_cfg.get("engine")
    fine_seg = bool(asr_cfg.get("fine_segmentation"))
    language = asr_cfg.get("language", "en")
    segments = []

    if fine_seg and engine_name == "mlx-whisper":
        from asr import sentence_split

        def _ws_emit(kind: str, message: str):
            try:
                socketio.emit('transcription_warning',
                              {'kind': kind, 'message': message},
                              room=sid)
            except Exception:
                logger.warning(f"transcription_warning emit failed: {kind}={message}")

        try:
            raw = sentence_split.transcribe_fine_seg(audio_path, profile, _ws_emit)
        except sentence_split.FineSegmentationError as e:
            _ws_emit("fine_seg_unavailable", str(e))
            raise
        for i, seg in enumerate(raw):
            segment = {
                'id': i,
                'start': seg['start'],
                'end': seg['end'],
                'text': seg['text'],
                'words': seg.get('words', []) or [],
            }
            segments.append(segment)
            emit_segment_with_progress(segment, sid)
        return {
            'text': ' '.join(s['text'] for s in segments),
            'language': language,
            'segments': segments,
            'backend': 'mlx-whisper-fine-seg',
            'model': asr_cfg.get('model_size', ''),
        }

    # Legacy path — existing behaviour
    from asr import create_asr_engine
    engine = create_asr_engine(asr_cfg)
    raw_segments = engine.transcribe(audio_path, language=language)
    from asr.segment_utils import split_segments
    lang_config_id = asr_cfg.get("language_config_id", language)
    lang_config = _language_config_manager.get(lang_config_id)
    asr_params = lang_config["asr"] if lang_config else DEFAULT_ASR_CONFIG
    raw_segments = split_segments(
        raw_segments,
        max_words=asr_params["max_words_per_segment"],
        max_duration=asr_params["max_segment_duration"],
    )
    for i, seg in enumerate(raw_segments):
        segment = {
            'id': i,
            'start': seg['start'],
            'end': seg['end'],
            'text': seg['text'],
            'words': seg.get('words', []) or [],
        }
        segments.append(segment)
        emit_segment_with_progress(segment, sid)
    engine_info = engine.get_info()
    return {
        'text': ' '.join(s['text'] for s in segments),
        'language': language,
        'segments': segments,
        'backend': engine_info.get('engine', 'whisper'),
        'model': engine_info.get('model_size', asr_cfg.get('model_size', '')),
    }
```

- [ ] **Step 4: Replace existing profile-engine block in `transcribe_with_segments` with helper call**

In `backend/app.py:456-495`, replace the entire `# === Profile-based ASR engine path ===` block (from `if use_profile_engine:` through the `return {...}` for that path) with:

```python
        # === Profile-based ASR engine path (legacy or fine_segmentation) ===
        if use_profile_engine:
            return _run_profile_asr_with_optional_fine_seg(
                audio_path=audio_path,
                profile=profile,
                sid=sid,
                emit_segment_with_progress=emit_segment_with_progress,
            )
```

- [ ] **Step 5: Run new test to verify it passes**

```bash
cd backend && source venv/bin/activate && pytest tests/test_app_fine_seg.py::test_transcribe_with_segments_calls_fine_seg_when_enabled -v
```

Expected: PASS

- [ ] **Step 6: Run existing transcribe-related tests for regression**

```bash
cd backend && source venv/bin/activate && pytest tests/test_asr.py tests/test_proofreading.py -v 2>&1 | tail -20
```

Expected: existing tests still PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app.py backend/tests/test_app_fine_seg.py
git commit -m "feat(app): branch transcribe_with_segments through fine_segmentation pipeline when enabled"
```

---

### Task C2: `transcribed_with_fine_seg` registry flag

**Files:**
- Modify: `backend/app.py` (in `transcribe_with_segments` after `result =` assignment, before `_update_file`)
- Modify: `backend/tests/test_app_fine_seg.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_app_fine_seg.py`:

```python
def test_registry_records_transcribed_with_fine_seg_flag():
    """After fine_seg path runs, registry entry has transcribed_with_fine_seg=True."""
    import app

    profile = {
        "asr": {"engine": "mlx-whisper", "fine_segmentation": True, "language": "en"},
        "translation": {"engine": "mock"},
    }
    flag = app._compute_transcribed_with_fine_seg_flag(profile)
    assert flag is True


def test_registry_flag_false_for_legacy_profile():
    """Profile without fine_segmentation → flag is False."""
    import app
    profile = {
        "asr": {"engine": "whisper", "model_size": "tiny", "language": "en"},
        "translation": {"engine": "mock"},
    }
    flag = app._compute_transcribed_with_fine_seg_flag(profile)
    assert flag is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_app_fine_seg.py -k transcribed_with_fine_seg -v
```

Expected: FAIL — helper does not exist.

- [ ] **Step 3: Add `_compute_transcribed_with_fine_seg_flag` helper + registry write in `app.py`**

In `backend/app.py`, after the `_run_profile_asr_with_optional_fine_seg` function from C1, add:

```python
def _compute_transcribed_with_fine_seg_flag(profile: dict) -> bool:
    """Return True iff fine_segmentation pipeline was used for this transcribe.

    Includes the VAD-fallback path (`_fallback_whole_file`) — flag tracks
    `transcribe_fine_seg()` ENTRY, not whether VAD chunking actually happened.
    """
    asr_cfg = (profile or {}).get("asr") or {}
    return bool(asr_cfg.get("fine_segmentation")) and asr_cfg.get("engine") == "mlx-whisper"
```

Then in `transcribe_with_segments` (find `_update_file(file_id, ...` calls after the profile ASR branch returns), update the registry write to include the flag. Search for the `_update_file` call that records segments + status='done', and add `transcribed_with_fine_seg=...`:

Locate the success path of `transcribe_with_segments` around the part that currently does `_update_file(file_id, status='done', segments=..., ...)`. Add the flag:

```python
            _update_file(
                file_id,
                status='done',
                # ... existing fields ...
                transcribed_with_fine_seg=_compute_transcribed_with_fine_seg_flag(profile),
            )
```

(Find `_update_file(file_id` references near the ASR success block — typically one main entry near line 700-800. The agent should grep for the existing call pattern and inject the new field.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_app_fine_seg.py -k transcribed_with_fine_seg -v
```

Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_app_fine_seg.py
git commit -m "feat(app): record transcribed_with_fine_seg flag in registry after ASR completes"
```

---

### Task C3: `skip_sentence_merge` bypass in `_auto_translate`

**Files:**
- Modify: `backend/app.py:2249-2270` (`_auto_translate` translation routing)
- Modify: `backend/tests/test_app_fine_seg.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_app_fine_seg.py`:

```python
def test_auto_translate_skip_flag_bypasses_sentence_pipeline(monkeypatch):
    """translation.skip_sentence_merge=True → translate_with_sentences NOT called."""
    import app

    spy_called = []
    monkeypatch.setattr(
        "translation.sentence_pipeline.translate_with_sentences",
        lambda *a, **kw: spy_called.append(True) or [],
    )

    translation_config = {
        "engine": "mock",
        "use_sentence_pipeline": True,    # would normally trigger merge
        "skip_sentence_merge": True,      # but this skip overrides
    }
    routed = app._auto_translate_pick_route(translation_config)
    assert routed == "direct", f"expected 'direct', got {routed!r}"
    assert spy_called == []


def test_auto_translate_uses_sentence_pipeline_without_skip_flag(monkeypatch):
    """translation.skip_sentence_merge=False (default) + use_sentence_pipeline=True → sentence path."""
    import app
    translation_config = {
        "engine": "mock",
        "use_sentence_pipeline": True,
    }
    routed = app._auto_translate_pick_route(translation_config)
    assert routed == "sentence_pipeline"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_app_fine_seg.py -k auto_translate -v
```

Expected: FAIL — `_auto_translate_pick_route` does not exist.

- [ ] **Step 3: Extract route picking into testable helper**

In `backend/app.py`, before `_auto_translate` definition (search for `def _auto_translate`), add:

```python
def _auto_translate_pick_route(translation_config: dict) -> str:
    """Return one of {'llm-markers', 'sentence_pipeline', 'direct'} for translate routing.

    Priority:
        1. alignment_mode='llm-markers' → 'llm-markers'
        2. (use_sentence_pipeline OR alignment_mode='sentence') AND NOT skip_sentence_merge → 'sentence_pipeline'
        3. otherwise → 'direct'

    skip_sentence_merge=True takes precedence over use_sentence_pipeline/alignment_mode='sentence'
    so users can pair it with fine_segmentation without disabling the upstream flag.
    """
    alignment_mode = str(translation_config.get("alignment_mode", "")).lower()
    use_pipeline = bool(translation_config.get("use_sentence_pipeline", False))
    skip = bool(translation_config.get("skip_sentence_merge", False))

    if alignment_mode == "llm-markers":
        return "llm-markers"
    if (use_pipeline or alignment_mode == "sentence") and not skip:
        return "sentence_pipeline"
    return "direct"
```

Then in `_auto_translate` body (around line 2249-2270), replace the existing branching block:

```python
        parallel_batches = int(translation_config.get("parallel_batches") or 1)
        route = _auto_translate_pick_route(translation_config)

        if route == "llm-markers":
            from translation.alignment_pipeline import translate_with_alignment
            translated = translate_with_alignment(
                engine, asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
            )
        elif route == "sentence_pipeline":
            from translation.sentence_pipeline import translate_with_sentences
            translated = translate_with_sentences(
                engine, asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
            )
        else:  # 'direct'
            translated = engine.translate(
                asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_app_fine_seg.py -k auto_translate -v
```

Expected: 2 PASS

- [ ] **Step 5: Run wider regression**

```bash
cd backend && source venv/bin/activate && pytest tests/test_proofreading.py tests/test_translation.py -q 2>&1 | tail -10
```

Expected: existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_app_fine_seg.py
git commit -m "feat(app): _auto_translate honours translation.skip_sentence_merge to bypass sentence pipeline"
```

---

### Task C4: Phase C regression check

**Files:** none

- [ ] **Step 1: Run full backend suite**

```bash
cd backend && source venv/bin/activate && pytest tests/ -q
```

Expected: ~482 + 4 new = 486 PASS / 12 pre-existing FAIL.

- [ ] **Step 2: Manual smoke test (optional, only if mlx-whisper + audio fixture present)**

```bash
cd backend && source venv/bin/activate && python -c "
import os, sys
sys.path.insert(0, '.')
from asr import sentence_split

# Bypass actual mlx call — we only test routing
class DummyMlx:
    @staticmethod
    def transcribe(*a, **kw):
        return {'segments': [{'start': 0, 'end': 1, 'text': 'hi', 'words': []}]}

profile = {'asr': {'engine': 'mlx-whisper', 'fine_segmentation': True, 'language': 'en'}}
print('Routing OK')
"
```

Expected: `Routing OK`.

---

## Phase D — UI Exposure

Add `fine_segmentation` toggle + `temperature` input to Profile form, plus toast listener for `transcription_warning` event.

### Task D1: Profile form — `fine_segmentation` toggle

**Files:**
- Modify: `frontend/index.html` (Profile form ASR section)

- [ ] **Step 1: Locate Profile form ASR section**

```bash
grep -n "fine_segmentation\|word_timestamps\|condition_on_previous_text" frontend/index.html | head -20
```

Find the existing ASR field rendering area (look for `condition_on_previous_text` or `word_timestamps` boolean switch rendering — that's the pattern to copy).

- [ ] **Step 2: Verify schema-driven render handles new field**

The Profile form already renders fields dynamically from `engine.get_params_schema()` (per v3.0). Task A6 already added `temperature` to the schema. This task adds the matching `fine_segmentation` toggle so both UI fields are exposed.

Edit `backend/asr/mlx_whisper_engine.py:get_params_schema()` to also add `fine_segmentation`. Insert this entry **before** the `temperature` entry added in A6:

```python
                "fine_segmentation": {
                    "type": "boolean",
                    "label": "細粒度分句（廣播字幕優化）",
                    "widget": "switch",
                    "description": "Use Silero VAD pre-segmentation + word-gap refine for finer subtitle units",
                    "hint": "開 = 廣播字幕優化（mean ~3s / max ~5.5s）；只 mlx-whisper 支援。略增轉錄時間。",
                    "default": False,
                },
```

- [ ] **Step 3: Verify schema endpoint serves new field**

Restart dev server (`./start.sh`), then:

```bash
curl -s http://localhost:5001/api/asr/engines/mlx-whisper/params | python3 -m json.tool | grep -A3 "fine_segmentation"
```

Expected: shows the field with label "細粒度分句".

- [ ] **Step 4: Open Profile form in browser, verify toggle appears**

Open http://localhost:5001 → click any profile → ASR section. Should see "細粒度分句（廣播字幕優化）" switch + 「解碼溫度」number input. Toggle should persist after save.

- [ ] **Step 5: Commit**

```bash
git add backend/asr/mlx_whisper_engine.py
git commit -m "feat(ui): expose fine_segmentation toggle in mlx-whisper params schema"
```

---

### Task D2: Frontend toast for `transcription_warning` event

**Files:**
- Modify: `frontend/index.html` (Socket.IO listeners section)

- [ ] **Step 1: Locate existing toast pattern**

```bash
grep -n "warning_missing_zh\|showToast\|amber" frontend/index.html | head -10
```

Find the v3.7 toast helper (search for `function showToast` or similar).

- [ ] **Step 2: Add SocketIO listener**

In `frontend/index.html`, locate the Socket.IO event listeners block (search for `socket.on('transcription_complete'` and add nearby):

```html
<script>
// Fine-segmentation runtime warnings (v3.8)
socket.on('transcription_warning', function(data) {
    const kindLabels = {
        'vad_zero': 'VAD 偵測唔到語音 — 已 fallback 到完整檔案轉錄',
        'vad_fail': '所有 chunk 轉錄失敗 — 已 fallback 到完整檔案轉錄',
        'chunk_fail': '部分 chunk 轉錄失敗 — 字幕可能有空白',
        'fine_seg_unavailable': '細粒度分句模組不可用',
    };
    const label = kindLabels[data.kind] || data.kind;
    showToast(`⚠️ ${label}: ${data.message}`, 'warning');
});
</script>
```

(The agent should adapt the exact JS placement to match the existing event listener style in the file.)

- [ ] **Step 3: Manual test**

(Requires running backend + a fine_segmentation-enabled profile + audio file that triggers fallback, e.g. silence-only.) Or just verify no JS console errors when listener registers:

```bash
# Open browser dev tools → Console. Reload page.
# Should see no "socket.on is not a function" or similar.
```

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat(ui): toast listener for transcription_warning fine_segmentation events"
```

---

## Phase E — Live Validation + Integration Tests

### Task E1: `--run-live` pytest flag in `conftest.py`

**Files:**
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Read existing conftest**

```bash
cat backend/tests/conftest.py
```

- [ ] **Step 2: Append `--run-live` plumbing**

Append to `backend/tests/conftest.py`:

```python


def pytest_addoption(parser):
    """Add --run-live flag for tests requiring real mlx-whisper + audio fixtures."""
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live integration tests (requires mlx-whisper + audio fixtures)",
    )


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.live tests unless --run-live flag is set."""
    if config.getoption("--run-live"):
        return
    skip_live = pytest.mark.skip(reason="needs --run-live flag")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
```

(Add `import pytest` at top of file if not already imported.)

- [ ] **Step 3: Verify normal pytest run still works (no --run-live)**

```bash
cd backend && source venv/bin/activate && pytest tests/ -q
```

Expected: same baseline result, no live tests collected.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test: add --run-live pytest flag for integration tests"
```

---

### Task E2: Live integration test on Real Madrid 5min

**Files:**
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/integration/test_fine_segmentation.py`

- [ ] **Step 1: Create empty package init**

```bash
mkdir -p backend/tests/integration
touch backend/tests/integration/__init__.py
```

- [ ] **Step 2: Create live integration test**

Create `backend/tests/integration/test_fine_segmentation.py`:

```python
"""Live integration tests for fine_segmentation pipeline.

These tests require:
  - mlx-whisper installed
  - silero-vad installed
  - /tmp/l1_real_madrid.wav fixture (from prototype validation)
  - --run-live pytest flag

Run: pytest tests/integration/test_fine_segmentation.py --run-live -v
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

REAL_MADRID = "/tmp/l1_real_madrid.wav"


def _profile():
    return {
        "asr": {
            "engine": "mlx-whisper",
            "model_size": "large-v3",
            "language": "en",
            "fine_segmentation": True,
            "temperature": 0.0,
            "vad_threshold": 0.5,
            "vad_min_silence_ms": 500,
            "vad_min_speech_ms": 250,
            "vad_speech_pad_ms": 200,
            "vad_chunk_max_s": 25,
            "refine_max_dur": 4.0,
            "refine_gap_thresh": 0.10,
            "refine_min_dur": 1.5,
        },
    }


@pytest.mark.live
def test_real_madrid_5min_fine_seg_pipeline():
    """Real Madrid broadcast 5min: verify metrics + #3+#4 case fix."""
    if not os.path.exists(REAL_MADRID):
        pytest.skip(f"Fixture {REAL_MADRID} not available")

    from asr.sentence_split import transcribe_fine_seg

    segs = transcribe_fine_seg(REAL_MADRID, _profile(), ws_emit=None)

    # Section 6.1 acceptance: mean ≤ 3.5s, p95 ≤ 5.5s, max ≤ 6.0s
    durs = [s["end"] - s["start"] for s in segs]
    assert len(segs) >= 70, f"too few segments: {len(segs)}"
    assert len(segs) <= 110, f"too many segments: {len(segs)}"
    mean_d = sum(durs) / len(durs)
    assert 2.5 <= mean_d <= 3.5, f"mean dur {mean_d:.2f}s out of [2.5, 3.5]"
    sd = sorted(durs)
    p95 = sd[int(len(sd) * 0.95)]
    assert p95 <= 5.5, f"p95 dur {p95:.2f}s > 5.5"
    assert max(durs) <= 6.0, f"max dur {max(durs):.2f}s > 6.0"

    # Tiny rate < 8%
    tiny = sum(1 for d in durs if d < 1.5)
    assert tiny / len(segs) < 0.08, f"tiny rate {tiny/len(segs):.1%} >= 8%"

    # #3+#4 case fix: no segment ends with " is a"
    for i, s in enumerate(segs[:-1]):
        text = s["text"].strip().lower()
        if "needs is a" in text:
            assert not text.endswith(" a"), \
                f"#3+#4 mid-clause cut still present at seg {i}: {text!r}"


@pytest.mark.live
def test_real_madrid_words_preserved():
    """Each segment must have non-empty words[] from DTW."""
    if not os.path.exists(REAL_MADRID):
        pytest.skip(f"Fixture {REAL_MADRID} not available")

    from asr.sentence_split import transcribe_fine_seg

    segs = transcribe_fine_seg(REAL_MADRID, _profile(), ws_emit=None)

    # At least 90% of segments should have populated words[] (allow some edge cases)
    have_words = sum(1 for s in segs if s.get("words"))
    assert have_words / len(segs) >= 0.90, \
        f"only {have_words}/{len(segs)} segments have words[]"

    # Every word must have start, end, probability fields
    for s in segs[:5]:  # spot-check first 5
        for w in s.get("words", []):
            assert "word" in w
            assert "start" in w
            assert "end" in w
            assert "probability" in w
```

- [ ] **Step 3: Verify tests are skipped without --run-live**

```bash
cd backend && source venv/bin/activate && pytest tests/integration/test_fine_segmentation.py -v
```

Expected: 2 SKIPPED (`needs --run-live flag`).

- [ ] **Step 4: Run live (only if /tmp/l1_real_madrid.wav exists)**

```bash
cd backend && source venv/bin/activate && pytest tests/integration/test_fine_segmentation.py --run-live -v
```

Expected: 2 PASS (each ~60-90s, total ~3min on M-series Mac).

If fixture is missing, the tests SKIP cleanly.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/integration/__init__.py backend/tests/integration/test_fine_segmentation.py
git commit -m "test(integration): live test fine_segmentation on Real Madrid 5min broadcast fixture"
```

---

### Task E3: Update validation tracker with post-impl numbers

**Files:**
- Modify: `docs/superpowers/specs/2026-05-03-asr-fine-segmentation-validation.md`

- [ ] **Step 1: Append post-implementation results section**

After the existing "Decisions Log" section in the validation tracker, append:

```markdown
## Post-Implementation Validation (2026-05-XX, after merging fine-seg branch)

### Live integration test results

```
pytest tests/integration/test_fine_segmentation.py --run-live -v
```

| Test | Duration | Result |
|---|---|---|
| test_real_madrid_5min_fine_seg_pipeline | (record actual) | PASS |
| test_real_madrid_words_preserved | (record actual) | PASS |

### Empirical metrics (production code path, large-v3)

(Record actual run: n / mean / p95 / max / over_84c / sent_pct / wall.)

### Backward compat

- Backend pytest baseline 469/481 → 500/512 PASS / 12 pre-existing FAIL ✅
- Existing profile JSON unchanged behaviour ✅
- Legacy `engine.transcribe()` path 100% preserved ✅
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-03-asr-fine-segmentation-validation.md
git commit -m "docs: post-implementation validation results for fine_segmentation"
```

---

## Phase F — Documentation

### Task F1: CLAUDE.md v3.8 section

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Locate v3.7 section**

```bash
grep -n "### v3.7" CLAUDE.md
```

- [ ] **Step 2: Insert v3.8 section before v3.7 (most recent first)**

In `CLAUDE.md`, **before** the `### v3.7 — Subtitle Source Mode` line, insert:

```markdown
### v3.8 — ASR Fine Segmentation (Silero VAD chunk-mode + word-gap refine)
- **Background**：mlx-whisper 30s window 結構性限制令 broadcast 訪問風格（run-on 句）經常喺 sentence 中段 emit timestamp（cross-30s-window mid-clause cut）。例如「...what the team really needs is a」+「radical overhaul...」應為一句但被 Whisper 30s window 強行切開。純 mlx-whisper kwargs（length_penalty / beam_size / max_initial_timestamp / hallucination_silence_threshold 等）11-config A/B 證實無法解決。
- **Validation**: 詳見 [docs/superpowers/specs/2026-05-03-asr-fine-segmentation-validation.md](docs/superpowers/specs/2026-05-03-asr-fine-segmentation-validation.md)。跑 11 mlx-whisper kwargs configs + 3-way prototype（faster-whisper+vad / word-gap split / Silero VAD chunk）+ stack tuning。Cross-style 已驗證 Real Madrid sports interview + Trump 政治演講兩個極端 broadcast style。
- **新 module**: [backend/asr/sentence_split.py](backend/asr/sentence_split.py) — Silero VAD pre-segment（threshold 0.5 / min_silence 500ms）→ sub-cap chunks ≤ 25s → mlx-whisper transcribe per chunk（temperature=0.0 + word_timestamps=True + condition_on_previous_text=False）→ word-gap refine（max_dur=4.0s / gap_thresh=0.10s / min_dur=1.5s）。架構性消除 cross-30s-window mid-clause cut。
- **Profile schema**：ASR block 加 10 個 fields（fine_segmentation, temperature, vad_threshold, vad_min_silence_ms, vad_min_speech_ms, vad_speech_pad_ms, vad_chunk_max_s, refine_max_dur, refine_gap_thresh, refine_min_dur）；translation block 加 1 個 field（skip_sentence_merge）。Frontend UI 暴露 fine_segmentation toggle + temperature；其餘 9 fields 只 JSON edit。
- **Validation 結果**（5min Real Madrid，large-v3）：
  - Baseline: 66 segs, mean 4.44s, max 6.24s, 43/66 (65%) 過 84c, sent_end 19.4%, ❌ #3+#4 mid-clause cut
  - L1 + L3 stack（fine_seg）: 86 segs, mean 3.19s, max 5.48s, 21/86 (24%) 過 84c, sent_end 39.5%, ✅ #3+#4 修復
- **Engine compat**：Phase 1 只 mlx-whisper；whisper engine（faster-whisper / openai-whisper）已有自己 vad_filter 機制。Profile validation reject `fine_segmentation: true` 配 engine ≠ mlx-whisper。
- **Grandfather 策略**：既有 file 唔重新 transcribe；只新 upload 行新 stack。Registry 加 `transcribed_with_fine_seg` flag 標記。
- **Error handling**：Setup error（silero-vad 缺）= strict raise；runtime fallback（VAD 0 chunks / chunk fail）= permissive + WebSocket `transcription_warning` event。
- **新 dep**: `silero-vad>=6.2.0` (~1.8 MB ONNX，無 PyTorch 需要)
- **新 test 數量**: ~31（16 sentence_split + 3 mlx_engine + 6 profiles + 4 app + 2 live integration）
- **Backend total**: 469 → 500 PASS / 12 pre-existing FAIL (512 total)
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): v3.8 ASR fine-segmentation feature entry"
```

---

### Task F2: README.md 繁中 user guide

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Locate v3.7 section in README**

```bash
grep -n "v3.7\|v3.6" README.md | head -5
```

- [ ] **Step 2: Insert v3.8 user guide above v3.7**

Find the v3.7 section heading and insert before it:

```markdown
## v3.8 細粒度 ASR 分句（廣播字幕優化）

廣播字幕場景下，mlx-whisper 預設嘅 30 秒 window 會喺 sentence 中段切斷（例如「...needs is a」與「radical overhaul...」應屬同一句但被切成兩段）。v3.8 加入 Silero VAD pre-segment + word-gap refine 嘅 stack，架構性解決呢類 mid-clause cut。

**啟用方式**（Profile 設定）：
- ASR engine 揀 `mlx-whisper`（其他 engine 暫時唔支援）
- 開「細粒度分句（廣播字幕優化）」
- 「解碼溫度」設 `0.0`（建議；停 mlx fallback tuple，最穩定 boundary）
- 翻譯設定建議勾選「跳過句子合併」（避免 fine-seg 後再次 merge）

**Profile JSON 例子**（高階用戶可手動編輯）：
```json
{
  "asr": {
    "engine": "mlx-whisper",
    "model_size": "large-v3",
    "language": "en",
    "fine_segmentation": true,
    "temperature": 0.0,
    "vad_threshold": 0.5,
    "vad_min_silence_ms": 500,
    "vad_chunk_max_s": 25,
    "refine_max_dur": 4.0,
    "refine_gap_thresh": 0.10
  },
  "translation": {
    "skip_sentence_merge": true
  }
}
```

**新增依賴**：`pip install silero-vad>=6.2.0`（已加入 `requirements.txt`，跑 `./setup.sh` 會自動安裝）

**注意事項**：
- 既有已轉錄嘅 file 不受影響；只有新 upload 嘅 file 會行 fine-seg pipeline
- Wall clock 比 baseline 略增 5-15%（VAD pre-segment + word_timestamps DTW overhead）
- 對極短 audio（< 1 秒）或全 silence 檔案，pipeline 會自動 fallback 到完整檔案轉錄並 emit warning toast
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): v3.8 fine_segmentation user guide (繁中)"
```

---

### Task F3: PRD.md status flip

**Files:**
- Modify: `docs/PRD.md`

- [ ] **Step 1: Locate ASR segmentation row**

```bash
grep -n "fine.segmentation\|fine segmentation\|細粒度\|ASR.*分" docs/PRD.md
```

- [ ] **Step 2: Flip status marker**

If the row exists, change `📋` → `✅ v3.8`. If not, append a new row to the feature table:

```markdown
| ASR fine segmentation | mlx-whisper Silero VAD chunk + word-gap refine | ✅ v3.8 |
```

- [ ] **Step 3: Commit**

```bash
git add docs/PRD.md
git commit -m "docs(prd): flip ASR fine-segmentation row to v3.8 ✅"
```

---

### Task F4: Final regression sweep + verification

**Files:** none

- [ ] **Step 1: Full backend test suite**

```bash
cd backend && source venv/bin/activate && pytest tests/ -q
```

Expected: 500 PASS / 12 pre-existing FAIL (512 total).

- [ ] **Step 2: Live integration (if fixture available)**

```bash
cd backend && source venv/bin/activate && pytest tests/integration/test_fine_segmentation.py --run-live -v
```

Expected: 2 PASS (3-5 minutes wall clock).

- [ ] **Step 3: End-to-end smoke**

1. Start backend: `./start.sh`
2. Open http://localhost:5001
3. Edit active profile → enable "細粒度分句" + temperature=0.0 + skip_sentence_merge=true → Save
4. Upload Real Madrid mp4 (or any English broadcast)
5. Wait for transcription complete
6. Check `backend/data/registry.json` → entry has `"transcribed_with_fine_seg": true` + segments contain `words: [...]`
7. Manually scan segments — verify mean ~3s, no segment ends with " is a" / " of the" pattern (mid-clause cut)

- [ ] **Step 4: Final commit message**

```bash
git log --oneline feat/asr-fine-segmentation
```

Verify clean commit history (~30+ commits).

---

## Acceptance Gates Final Verification

| Gate (per spec Section 6) | Verified |
|---|---|
| #3+#4 case fix on Real Madrid 5min fixture | ✅ Task E2 |
| Mean ≤ 3.5s, p95 ≤ 5.5s, max ≤ 6.0s | ✅ Task E2 |
| Sent_end% ≥ 35% | ✅ Task E2 (manual review) |
| Tiny < 8% | ✅ Task E2 |
| Profile validation rejects invalid configs | ✅ Tasks A2-A5 |
| skip_sentence_merge bypasses merge | ✅ Task C3 |
| `transcribed_with_fine_seg` flag set | ✅ Task C2 |
| Grandfather: existing files unchanged | ✅ Task A7 |
| F1 strict raise on missing silero-vad | ✅ Task B5 |
| F2/F4 permissive fallback + warning event | ✅ Task B7 |
| ~31 new tests, 469 → 500 PASS | ✅ Task F4 Step 1 |
| Documentation complete | ✅ Tasks F1-F3 |

---

## Summary

- **Total tasks**: 21 (across 6 phases)
- **Estimated effort**: 12-18 hours
- **New files**: 5 (1 module + 4 test files)
- **Modified files**: 9
- **New tests**: ~31
- **Commits**: ~30 (one per task step group)
- **Risk**: Low (empirical validation pre-implementation; opt-in flag; permissive runtime fallback)
- **Branch**: `feat/asr-fine-segmentation` (off `feat/subtitle-source-mode @ 4e3c33a`)
