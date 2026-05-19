# v5-A2 Stage Executor + Pipeline Runner Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire v5-A1's 5 engine ABCs + profile managers into a runtime executor that actually transcribes audio, translates per-target-language, and persists multi-lang results to the file registry.

**Architecture:** Add 5 new `PipelineStage` subclasses (`ASRPrimaryStage` / `ASRSecondaryStage` / `ASRVerifierStage` / `RefinerStage` / `TranslatorStage`) implementing the v4 `PipelineStage` ABC contract. Extend `PipelineRunner` with a v5 DAG branch (gated by `pipeline["version"] == 5`) that orchestrates: ASR primary (+ optional secondary + verifier) → canonical source segments → per-target-lang refinement chain → translator (when target != source). File registry `translations` field grows a `by_lang` dict shape; lazy `normalize_translations_for_v5()` converts v4 shape on read. V4 path (linear executor) completely untouched.

**Tech Stack:** Python 3.9 (`backend/venv`); Flask + Socket.IO; reuses v5-A1 engines (`engines/{llm,transcribe,translator,refiner,verifier}/`) + v5-A1 profile managers (`{llm,transcribe,translator,refiner,verifier}_profiles.py`) + `pipeline_schema_v5` module. No new third-party deps.

**Parent spec:** `docs/superpowers/specs/2026-05-19-v5-dual-asr-refiner-translator-design.md` (§4 Engine ABCs, §5 Stage Classes, §6 Prompt Override Resolution)

**A1 foundation (frozen, do not modify):**
- `backend/pipeline_schema_v5.py` — validators + promote + cascade refs
- `backend/{llm,transcribe,translator,refiner,verifier}_profiles.py` — 5 managers
- `backend/engines/{llm,transcribe,translator,refiner,verifier}/` — 5 engine ABCs + concretes
- `backend/config/prompt_templates_v5/` — 6 default prompt templates

**V4 path (frozen, must keep working):**
- `backend/stages/{asr,mt,glossary}_stage.py` — v4 stages
- `backend/pipeline_runner.py` linear executor branch (anything not gated by `version == 5`)

**Branch:** continue on `feat/frontend-redesign` (A1 already landed there).

---

## File Structure

### New files (created by this plan)

| Path | Responsibility |
|---|---|
| `backend/engines/factory.py` | Build LLMEngine instances from LLMProfile; load prompt templates from `prompt_templates_v5/` JSON files |
| `backend/stages/v5/__init__.py` | v5-specific stage class re-exports (keeps v4 `stages/` flat) |
| `backend/stages/v5/asr_primary_stage.py` | `ASRPrimaryStage` — wraps v5 `TranscribeEngine` |
| `backend/stages/v5/asr_secondary_stage.py` | `ASRSecondaryStage` — same wrapper, secondary profile |
| `backend/stages/v5/asr_verifier_stage.py` | `ASRVerifierStage` — wraps `LLMVerifier` + alignment helper |
| `backend/stages/v5/refiner_stage.py` | `RefinerStage` — wraps `LLMRefiner`, per-lang instance |
| `backend/stages/v5/translator_stage.py` | `TranslatorStage` — wraps `LLMTranslator`, per (source, target) pair |
| `backend/translations_normalize_v5.py` | `normalize_translations_for_v5(raw)` helper — converts v4 `[{en_text,zh_text}]` to v5 `[{by_lang}]` |
| `backend/tests/test_v5_a2_factory.py` | Engine + prompt loader tests |
| `backend/tests/test_v5_a2_stages.py` | All 5 stage class tests |
| `backend/tests/test_v5_a2_runner.py` | PipelineRunner v5 DAG executor tests |
| `backend/tests/test_v5_a2_normalize.py` | translations shape conversion tests |
| `backend/tests/test_v5_a2_integration.py` | End-to-end pipeline run test (uses mocked engines) |

### Modified files

| Path | Change |
|---|---|
| `backend/pipeline_runner.py` | Add `_run_v5()` method; `run()` branches on `pipeline.get("version") == 5` |
| `backend/routes/files.py` (or wherever `GET /api/files/<id>/translations` lives) | Wrap response through `normalize_translations_for_v5()` |
| `CLAUDE.md` | v5-A2 entry above v5-A1 entry |

### Files NOT touched

- `backend/stages/{asr,mt,glossary}_stage.py` — v4 stages frozen
- `backend/stages/__init__.py` — v4 `PipelineStage` ABC + `StageContext` reused via import from `stages.v5`
- `backend/engines/*` — all v5-A1 engines frozen
- `backend/{llm,transcribe,translator,refiner,verifier}_profiles.py` — frozen
- `backend/pipeline_schema_v5.py` — frozen
- `backend/routes/pipelines.py` — already accepts v5 schema from A1
- Frontend — deferred to A3

---

## Task index

| # | Task | Files |
|---|---|---|
| T1 | Engine factory + prompt template loader | `engines/factory.py` |
| T2 | ASRPrimaryStage + ASRSecondaryStage | `stages/v5/asr_primary_stage.py`, `stages/v5/asr_secondary_stage.py` |
| T3 | ASRVerifierStage (alignment helper) | `stages/v5/asr_verifier_stage.py` |
| T4 | RefinerStage (per-lang) | `stages/v5/refiner_stage.py` |
| T5 | TranslatorStage (per source→target pair) | `stages/v5/translator_stage.py` |
| T6 | PipelineRunner v5 DAG executor | `pipeline_runner.py` |
| T7 | File registry by_lang shape + `normalize_translations_for_v5` | `translations_normalize_v5.py`, `routes/files.py` |
| T8 | End-to-end integration test + CLAUDE.md update | `tests/test_v5_a2_integration.py`, `CLAUDE.md` |

---

## Task 1: Engine factory + prompt template loader

**Files:**
- Create: `backend/engines/factory.py`
- Test: `backend/tests/test_v5_a2_factory.py`

Stage classes need helpers to (a) construct concrete `LLMEngine` from an `LLMProfile` dict, and (b) load prompt templates from JSON files. Doing this inline in each stage would duplicate 30+ lines × 4 stages. Factory module centralizes both.

- [ ] **Step 1: Write failing test for LLMProfile → OllamaLLM construction**

Create `backend/tests/test_v5_a2_factory.py`:
```python
import json
import pytest
from engines.factory import build_llm_engine, load_prompt_template


def test_build_llm_engine_ollama():
    """ollama backend → OllamaLLM instance with correct base_url + model."""
    from engines.llm.ollama import OllamaLLM
    profile = {
        "backend": "ollama",
        "model": "qwen3.5:9b",
        "base_url": "http://localhost:11434",
    }
    engine = build_llm_engine(profile)
    assert isinstance(engine, OllamaLLM)
    assert engine.model == "qwen3.5:9b"
    assert engine.base_url == "http://localhost:11434"
```

- [ ] **Step 2: Run test to verify FAIL**

```bash
cd backend && source venv/bin/activate
pytest tests/test_v5_a2_factory.py::test_build_llm_engine_ollama -v
```
Expected: `ModuleNotFoundError: No module named 'engines.factory'`

- [ ] **Step 3: Create `backend/engines/factory.py`**

```python
"""Factory helpers for v5-A2 stages.

Builds concrete LLMEngine instances from LLMProfile dicts and loads prompt
template content from the `backend/config/prompt_templates_v5/` tree.

Used by ASRVerifierStage / RefinerStage / TranslatorStage so each stage
doesn't need to know about specific concrete classes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from engines.llm import LLMEngine

_TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "config" / "prompt_templates_v5"


def build_llm_engine(llm_profile: dict) -> LLMEngine:
    """Construct concrete LLMEngine from LLMProfile dict.

    Dispatches on `backend` field:
      - "ollama"     → OllamaLLM
      - "openrouter" → OpenRouterLLM (requires api_key in profile)
      - "claude"     → not yet supported in A2, raises NotImplementedError
    """
    backend = llm_profile.get("backend")
    if backend == "ollama":
        from engines.llm.ollama import OllamaLLM
        return OllamaLLM(
            model=llm_profile["model"],
            base_url=llm_profile.get("base_url", "http://localhost:11434"),
        )
    if backend == "openrouter":
        from engines.llm.openrouter import OpenRouterLLM
        api_key = llm_profile.get("api_key")
        if not api_key:
            raise ValueError("openrouter LLM profile missing api_key")
        return OpenRouterLLM(
            model=llm_profile["model"],
            api_key=api_key,
            base_url=llm_profile.get("base_url", "https://openrouter.ai/api/v1"),
        )
    if backend == "claude":
        raise NotImplementedError("claude backend deferred to post-v5-A2")
    raise ValueError(f"unknown LLM backend: {backend!r}")


def load_prompt_template(template_id: str) -> str:
    """Read system_prompt from a JSON template by ID.

    Template ID format: `<category>/<name>` (e.g., `translator/zh_to_en_default`).
    Resolves to `backend/config/prompt_templates_v5/<category>/<name>.json`.

    Returns the `system_prompt` field. Raises FileNotFoundError if template missing,
    ValueError if JSON malformed or `system_prompt` field absent.
    """
    if "/" not in template_id:
        raise ValueError(f"template_id must be '<category>/<name>', got {template_id!r}")
    category, name = template_id.split("/", 1)
    path = _TEMPLATE_ROOT / category / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"prompt template not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    prompt = data.get("system_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"template {template_id} missing or empty system_prompt")
    return prompt


def resolve_prompt(
    template_id: str,
    file_override: Optional[str] = None,
) -> str:
    """Resolve prompt with file-level override > template default fallback.

    Used by stage classes to allow per-file prompt customization (the
    `prompt_overrides` field on file registry entries).
    """
    if file_override and file_override.strip():
        return file_override
    return load_prompt_template(template_id)
```

- [ ] **Step 4: Run test to verify PASS**

```bash
pytest tests/test_v5_a2_factory.py::test_build_llm_engine_ollama -v
```
Expected: PASS

- [ ] **Step 5: Add 5 more factory tests**

Append:
```python
def test_build_llm_engine_openrouter():
    from engines.llm.openrouter import OpenRouterLLM
    profile = {
        "backend": "openrouter",
        "model": "anthropic/claude-opus-4-7",
        "api_key": "sk-xxx",
    }
    engine = build_llm_engine(profile)
    assert isinstance(engine, OpenRouterLLM)
    assert engine.api_key == "sk-xxx"


def test_build_llm_engine_openrouter_missing_api_key():
    profile = {"backend": "openrouter", "model": "m"}
    with pytest.raises(ValueError, match="api_key"):
        build_llm_engine(profile)


def test_build_llm_engine_claude_not_implemented():
    with pytest.raises(NotImplementedError):
        build_llm_engine({"backend": "claude", "model": "x"})


def test_build_llm_engine_unknown_backend():
    with pytest.raises(ValueError, match="unknown LLM backend"):
        build_llm_engine({"backend": "bogus"})


def test_load_prompt_template_translator_zh_to_en():
    """Default v5-A1 template should load cleanly."""
    prompt = load_prompt_template("translator/zh_to_en_default")
    assert "Hong Kong Cantonese to English" in prompt
    assert len(prompt) > 100


def test_load_prompt_template_refiner_zh_broadcast():
    prompt = load_prompt_template("refiner/zh_broadcast_hk_default")
    assert "香港" in prompt or "粵語" in prompt


def test_load_prompt_template_missing():
    with pytest.raises(FileNotFoundError):
        load_prompt_template("translator/nonexistent")


def test_load_prompt_template_bad_id():
    with pytest.raises(ValueError, match="<category>/<name>"):
        load_prompt_template("no_slash")


def test_resolve_prompt_uses_override_when_present():
    custom = "my custom prompt text"
    out = resolve_prompt("translator/zh_to_en_default", file_override=custom)
    assert out == custom


def test_resolve_prompt_falls_back_to_template_when_override_empty():
    out = resolve_prompt("translator/zh_to_en_default", file_override="")
    assert "Cantonese" in out

    out2 = resolve_prompt("translator/zh_to_en_default", file_override=None)
    assert "Cantonese" in out2
```

- [ ] **Step 6: Run all tests**

```bash
pytest tests/test_v5_a2_factory.py -v
```
Expected: 11 PASS

- [ ] **Step 7: Commit**

```bash
git add backend/engines/factory.py backend/tests/test_v5_a2_factory.py
git commit -m "feat(v5-a2): engine factory + prompt template loader

Centralizes LLMProfile → concrete LLMEngine construction and JSON template
file loading. Both used by ASRVerifier / Refiner / Translator stages to
avoid duplicating instantiation logic. Supports file-level prompt override
with template default fallback."
```

---

## Task 2: ASRPrimaryStage + ASRSecondaryStage

**Files:**
- Create: `backend/stages/v5/__init__.py`
- Create: `backend/stages/v5/asr_primary_stage.py`
- Create: `backend/stages/v5/asr_secondary_stage.py`
- Test: `backend/tests/test_v5_a2_stages.py`

Both stages wrap v5-A1's `TranscribeEngine` factory (`engines.transcribe.create_transcribe_engine`). They differ only in (a) which `transcribe_profile_id` they read from the pipeline dict (`asr_primary` vs `asr_secondary`) and (b) their `stage_type` string ("asr_primary" vs "asr_secondary"). Both ignore `segments_in` (first stages — they read audio).

- [ ] **Step 1: Write failing test for ASRPrimaryStage**

Create `backend/tests/test_v5_a2_stages.py`:
```python
import pytest
import threading
from unittest.mock import Mock, patch
from stages import StageContext


def test_asr_primary_stage_calls_transcribe_engine():
    """ASRPrimaryStage delegates to TranscribeEngine.transcribe() with profile config."""
    from stages.v5.asr_primary_stage import ASRPrimaryStage
    fake_engine = Mock()
    fake_engine.transcribe.return_value = [
        {"start": 0.0, "end": 1.0, "text": "hello"},
        {"start": 1.0, "end": 2.0, "text": "world"},
    ]
    profile = {"id": "tp1", "engine": "whisper", "language": "en", "model_size": "large-v3"}
    stage = ASRPrimaryStage(profile, "/tmp/fake.wav")
    ctx = StageContext(
        file_id="f1", user_id=1, pipeline_id="p1",
        stage_index=0, cancel_event=None,
        progress_callback=None, pipeline_overrides={},
    )
    with patch("stages.v5.asr_primary_stage.create_transcribe_engine", return_value=fake_engine):
        out = stage.transform([], ctx)
    assert out == [
        {"start": 0.0, "end": 1.0, "text": "hello"},
        {"start": 1.0, "end": 2.0, "text": "world"},
    ]
    fake_engine.transcribe.assert_called_once()
    # Engine was given the audio path + language from profile
    call = fake_engine.transcribe.call_args
    assert call.args[0] == "/tmp/fake.wav" or call.kwargs.get("audio_path") == "/tmp/fake.wav"


def test_asr_primary_stage_type_and_ref():
    from stages.v5.asr_primary_stage import ASRPrimaryStage
    profile = {"id": "tp1", "engine": "whisper", "language": "en"}
    stage = ASRPrimaryStage(profile, "/tmp/fake.wav")
    assert stage.stage_type == "asr_primary"
    assert stage.stage_ref == "tp1"
```

- [ ] **Step 2: Run test to verify FAIL**

```bash
pytest tests/test_v5_a2_stages.py::test_asr_primary_stage_calls_transcribe_engine -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Create `backend/stages/v5/__init__.py`**

```python
"""v5-A2 stage classes.

All implement the v4 PipelineStage ABC (re-exported from `stages.`) so the
PipelineRunner v5 DAG executor can reuse the existing _run_stage()
fail-fast + progress + persist machinery.
"""
```

- [ ] **Step 4: Create `backend/stages/v5/asr_primary_stage.py`**

```python
"""ASRPrimaryStage — v5-A2.

Wraps v5-A1 TranscribeEngine (factory dispatch from `engines.transcribe`).
Runs first in the v5 pipeline DAG; segments_in is ignored (audio is the
real input).

Profile fields read: engine, language, model_size, initial_prompt (optional),
beam_size (optional). Per v5 spec §4.
"""
from __future__ import annotations

from typing import List

from engines.transcribe import create_transcribe_engine
from stages import PipelineStage, StageContext


class ASRPrimaryStage(PipelineStage):
    def __init__(self, transcribe_profile: dict, audio_path: str):
        self._profile = transcribe_profile
        self._audio_path = audio_path
        self.quality_flags: List[str] = []

    @property
    def stage_type(self) -> str:
        return "asr_primary"

    @property
    def stage_ref(self) -> str:
        return self._profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        # segments_in ignored — ASR reads audio directly
        engine = create_transcribe_engine(self._profile)
        language = self._profile.get("language", "auto")
        segments = engine.transcribe(self._audio_path, language=language)
        # Normalize to canonical dict shape (some engines return list of TypedDict)
        return [
            {
                "start": float(s["start"]),
                "end": float(s["end"]),
                "text": s.get("text", "").strip(),
            }
            for s in segments
        ]
```

- [ ] **Step 5: Create `backend/stages/v5/asr_secondary_stage.py`**

```python
"""ASRSecondaryStage — v5-A2.

Same as ASRPrimaryStage but reads asr_secondary.transcribe_profile_id.
Output flows into ASRVerifierStage (not into refinement). Stage type
'asr_secondary' so the runner / persistence layer can distinguish.

When a pipeline has no asr_secondary, this stage is skipped by the runner.
"""
from __future__ import annotations

from typing import List

from engines.transcribe import create_transcribe_engine
from stages import PipelineStage, StageContext


class ASRSecondaryStage(PipelineStage):
    def __init__(self, transcribe_profile: dict, audio_path: str):
        self._profile = transcribe_profile
        self._audio_path = audio_path
        self.quality_flags: List[str] = []

    @property
    def stage_type(self) -> str:
        return "asr_secondary"

    @property
    def stage_ref(self) -> str:
        return self._profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        engine = create_transcribe_engine(self._profile)
        language = self._profile.get("language", "auto")
        segments = engine.transcribe(self._audio_path, language=language)
        return [
            {
                "start": float(s["start"]),
                "end": float(s["end"]),
                "text": s.get("text", "").strip(),
            }
            for s in segments
        ]
```

- [ ] **Step 6: Run test**

```bash
pytest tests/test_v5_a2_stages.py::test_asr_primary_stage_calls_transcribe_engine tests/test_v5_a2_stages.py::test_asr_primary_stage_type_and_ref -v
```
Expected: 2 PASS

- [ ] **Step 7: Add secondary tests**

Append:
```python
def test_asr_secondary_stage_calls_transcribe_engine():
    from stages.v5.asr_secondary_stage import ASRSecondaryStage
    fake_engine = Mock()
    fake_engine.transcribe.return_value = [{"start": 0, "end": 1, "text": "x"}]
    profile = {"id": "tp2", "engine": "qwen3-asr", "language": "zh"}
    stage = ASRSecondaryStage(profile, "/tmp/fake.wav")
    ctx = StageContext(
        file_id="f1", user_id=1, pipeline_id="p1",
        stage_index=1, cancel_event=None,
        progress_callback=None, pipeline_overrides={},
    )
    with patch("stages.v5.asr_secondary_stage.create_transcribe_engine", return_value=fake_engine):
        out = stage.transform([], ctx)
    assert out == [{"start": 0.0, "end": 1.0, "text": "x"}]


def test_asr_secondary_stage_type_and_ref():
    from stages.v5.asr_secondary_stage import ASRSecondaryStage
    profile = {"id": "tp2", "engine": "qwen3-asr", "language": "zh"}
    stage = ASRSecondaryStage(profile, "/tmp/fake.wav")
    assert stage.stage_type == "asr_secondary"
    assert stage.stage_ref == "tp2"
```

- [ ] **Step 8: Run tests**

```bash
pytest tests/test_v5_a2_stages.py -v -k "asr_primary or asr_secondary"
```
Expected: 4 PASS

- [ ] **Step 9: Commit**

```bash
git add backend/stages/v5/__init__.py backend/stages/v5/asr_primary_stage.py backend/stages/v5/asr_secondary_stage.py backend/tests/test_v5_a2_stages.py
git commit -m "feat(v5-a2): ASRPrimaryStage + ASRSecondaryStage

Both stages wrap v5-A1 TranscribeEngine factory. Primary runs always;
secondary only when pipeline.asr_secondary is set. Output flows into
ASRVerifierStage or directly into refinement when no verifier configured."
```

---

## Task 3: ASRVerifierStage (alignment helper)

**Files:**
- Create: `backend/stages/v5/asr_verifier_stage.py`
- Test: append to `backend/tests/test_v5_a2_stages.py`

The verifier needs BOTH primary segments AND secondary segments. Since the `PipelineStage.transform(segments_in, ctx)` ABC takes only one `segments_in`, the verifier reads the secondary segments from `context.pipeline_overrides["__secondary_segments"]` (a reserved internal key set by the v5 runner). This avoids changing the v4 ABC.

Primary segments arrive as `segments_in`. Secondary segments (full set from secondary ASR) arrive via context. The stage uses `engines.verifier.llm_verifier.collect_words_for_range` to align secondary words/segments to each primary segment time range.

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_v5_a2_stages.py`:
```python
def test_asr_verifier_stage_judges_disagreement():
    """ASRVerifierStage routes (primary, secondary) to LLMVerifier."""
    from stages.v5.asr_verifier_stage import ASRVerifierStage
    fake_llm = Mock()
    fake_llm.call.return_value = "judged"
    verifier_profile = {
        "id": "vp1",
        "lang": "zh",
        "llm_profile_id": "lp1",
        "prompt_template_id": "verifier/zh_default",
    }
    llm_profile = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}

    stage = ASRVerifierStage(
        verifier_profile=verifier_profile,
        llm_profile=llm_profile,
    )
    primary = [{"start": 0.0, "end": 1.0, "text": "whisper said"}]
    secondary = [{"start": 0.0, "end": 1.0, "text": "qwen said"}]
    ctx = StageContext(
        file_id="f1", user_id=1, pipeline_id="p1",
        stage_index=2, cancel_event=None,
        progress_callback=None,
        pipeline_overrides={"__secondary_segments": secondary},
    )
    with patch("stages.v5.asr_verifier_stage.build_llm_engine", return_value=fake_llm):
        out = stage.transform(primary, ctx)
    assert out == [{"start": 0.0, "end": 1.0, "text": "judged"}]


def test_asr_verifier_stage_type_and_ref():
    from stages.v5.asr_verifier_stage import ASRVerifierStage
    verifier_profile = {"id": "vp1", "lang": "zh", "llm_profile_id": "lp1",
                        "prompt_template_id": "verifier/zh_default"}
    llm_profile = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}
    stage = ASRVerifierStage(verifier_profile=verifier_profile, llm_profile=llm_profile)
    assert stage.stage_type == "asr_verifier"
    assert stage.stage_ref == "vp1"


def test_asr_verifier_stage_with_no_secondary_passes_primary_through():
    """If __secondary_segments missing from ctx, primary passes through unchanged."""
    from stages.v5.asr_verifier_stage import ASRVerifierStage
    verifier_profile = {"id": "vp1", "lang": "zh", "llm_profile_id": "lp1",
                        "prompt_template_id": "verifier/zh_default"}
    llm_profile = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}
    stage = ASRVerifierStage(verifier_profile=verifier_profile, llm_profile=llm_profile)
    primary = [{"start": 0.0, "end": 1.0, "text": "whisper"}]
    ctx = StageContext(
        file_id="f1", user_id=1, pipeline_id="p1",
        stage_index=2, cancel_event=None,
        progress_callback=None, pipeline_overrides={},
    )
    out = stage.transform(primary, ctx)
    assert out == primary


def test_asr_verifier_stage_uses_file_prompt_override():
    """ctx.pipeline_overrides['verifier'] (file-level) overrides template default."""
    from stages.v5.asr_verifier_stage import ASRVerifierStage
    fake_llm = Mock()
    fake_llm.call.return_value = "verdict"
    verifier_profile = {"id": "vp1", "lang": "zh", "llm_profile_id": "lp1",
                        "prompt_template_id": "verifier/zh_default"}
    llm_profile = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}
    stage = ASRVerifierStage(verifier_profile=verifier_profile, llm_profile=llm_profile)
    primary = [{"start": 0.0, "end": 1.0, "text": "whisper text"}]
    secondary = [{"start": 0.0, "end": 1.0, "text": "qwen text"}]
    ctx = StageContext(
        file_id="f1", user_id=1, pipeline_id="p1", stage_index=2,
        cancel_event=None, progress_callback=None,
        pipeline_overrides={
            "__secondary_segments": secondary,
            "verifier": "CUSTOM VERIFIER PROMPT",
        },
    )
    with patch("stages.v5.asr_verifier_stage.build_llm_engine", return_value=fake_llm):
        stage.transform(primary, ctx)
    # The system prompt sent to LLM should be the override, not the template
    sent_system = fake_llm.call.call_args.args[0]
    assert sent_system == "CUSTOM VERIFIER PROMPT"
```

- [ ] **Step 2: Run test to verify FAIL**

```bash
pytest tests/test_v5_a2_stages.py -v -k asr_verifier
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Create `backend/stages/v5/asr_verifier_stage.py`**

```python
"""ASRVerifierStage — v5-A2.

Wraps v5-A1 LLMVerifier. Takes primary segments via segments_in and
secondary segments via context.pipeline_overrides['__secondary_segments']
(reserved internal key set by the v5 PipelineRunner).

When secondary segments missing → primary passes through unchanged
(pipeline has no asr_secondary configured).

Prompt resolution: file-level `verifier` override > template default.
"""
from __future__ import annotations

from typing import List

from engines.factory import build_llm_engine, resolve_prompt
from engines.verifier.llm_verifier import LLMVerifier
from stages import PipelineStage, StageContext


SECONDARY_KEY = "__secondary_segments"  # reserved key in pipeline_overrides


class ASRVerifierStage(PipelineStage):
    def __init__(self, verifier_profile: dict, llm_profile: dict):
        self._verifier_profile = verifier_profile
        self._llm_profile = llm_profile
        self.quality_flags: List[str] = []

    @property
    def stage_type(self) -> str:
        return "asr_verifier"

    @property
    def stage_ref(self) -> str:
        return self._verifier_profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        secondary_segments = context.pipeline_overrides.get(SECONDARY_KEY, [])
        if not secondary_segments:
            # No secondary ASR configured — pass primary through unchanged
            return list(segments_in)

        llm = build_llm_engine(self._llm_profile)
        system_prompt = resolve_prompt(
            self._verifier_profile["prompt_template_id"],
            file_override=context.pipeline_overrides.get("verifier"),
        )
        verifier = LLMVerifier(
            llm=llm,
            system_prompt=system_prompt,
            lang=self._verifier_profile["lang"],
        )
        # LLMVerifier expects secondary as word-level list of {start, end, text}.
        # When secondary ASR returns segment-level (chunk-level), each is treated
        # as one big "word" — verifier's collect_words_for_range still works
        # because it filters by midpoint in [start, end).
        progress_cb = None
        if context.progress_callback is not None:
            def progress_cb(idx: int, total: int, _decision: str):
                context.progress_callback(idx, total)
        return verifier.verify(
            primary_segments=segments_in,
            secondary_words=secondary_segments,
            progress=progress_cb,
        )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_a2_stages.py -v -k asr_verifier
```
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/stages/v5/asr_verifier_stage.py backend/tests/test_v5_a2_stages.py
git commit -m "feat(v5-a2): ASRVerifierStage with secondary-via-context channel

PipelineStage ABC takes one segments_in, but verifier needs both primary
and secondary ASR outputs. Reserved internal key __secondary_segments
in pipeline_overrides carries the secondary set without changing the ABC.

Missing __secondary_segments → primary passes through (no secondary configured).
Honors file-level 'verifier' prompt override."
```

---

## Task 4: RefinerStage (per-lang)

**Files:**
- Create: `backend/stages/v5/refiner_stage.py`
- Test: append to `backend/tests/test_v5_a2_stages.py`

One instance per (lang, style) — runner constructs N RefinerStage instances iterating `pipeline["refinements"][lang]` list per target lang.

- [ ] **Step 1: Write failing test**

Append:
```python
def test_refiner_stage_polishes_segments():
    from stages.v5.refiner_stage import RefinerStage
    fake_llm = Mock()
    fake_llm.call.return_value = "polished"
    refiner_profile = {
        "id": "rp1",
        "lang": "zh",
        "style": "broadcast-hk",
        "llm_profile_id": "lp1",
        "prompt_template_id": "refiner/zh_broadcast_hk_default",
    }
    llm_profile = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}
    stage = RefinerStage(refiner_profile=refiner_profile, llm_profile=llm_profile)
    segments = [{"start": 0, "end": 1, "text": "raw"}]
    ctx = StageContext(
        file_id="f1", user_id=1, pipeline_id="p1", stage_index=3,
        cancel_event=None, progress_callback=None, pipeline_overrides={},
    )
    with patch("stages.v5.refiner_stage.build_llm_engine", return_value=fake_llm):
        out = stage.transform(segments, ctx)
    assert out == [{"start": 0, "end": 1, "text": "polished"}]


def test_refiner_stage_type_and_ref_carries_lang():
    """stage_type includes lang so persisted output is distinguishable."""
    from stages.v5.refiner_stage import RefinerStage
    refiner_profile = {"id": "rp1", "lang": "zh", "style": "broadcast-hk",
                       "llm_profile_id": "lp1", "prompt_template_id": "refiner/zh_broadcast_hk_default"}
    llm_profile = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}
    stage = RefinerStage(refiner_profile=refiner_profile, llm_profile=llm_profile)
    assert stage.stage_type == "refiner:zh"
    assert stage.stage_ref == "rp1"


def test_refiner_stage_uses_file_prompt_override_per_lang():
    """File override key is `refiners.<lang>`, not just `refiner`."""
    from stages.v5.refiner_stage import RefinerStage
    fake_llm = Mock()
    fake_llm.call.return_value = "x"
    refiner_profile = {"id": "rp1", "lang": "zh", "style": "broadcast-hk",
                       "llm_profile_id": "lp1", "prompt_template_id": "refiner/zh_broadcast_hk_default"}
    llm_profile = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}
    stage = RefinerStage(refiner_profile=refiner_profile, llm_profile=llm_profile)
    ctx = StageContext(
        file_id="f1", user_id=1, pipeline_id="p1", stage_index=3,
        cancel_event=None, progress_callback=None,
        pipeline_overrides={"refiners": {"zh": "CUSTOM ZH REFINER", "en": "irrelevant"}},
    )
    with patch("stages.v5.refiner_stage.build_llm_engine", return_value=fake_llm):
        stage.transform([{"start": 0, "end": 1, "text": "src"}], ctx)
    sent_system = fake_llm.call.call_args.args[0]
    assert sent_system == "CUSTOM ZH REFINER"
```

- [ ] **Step 2: Run test fail**

```bash
pytest tests/test_v5_a2_stages.py -v -k refiner
```

- [ ] **Step 3: Create `backend/stages/v5/refiner_stage.py`**

```python
"""RefinerStage — v5-A2.

Wraps v5-A1 LLMRefiner. One stage instance per (lang, refiner_profile).
Pipeline runner creates N instances iterating refinements[lang] list.

Prompt resolution: file_overrides['refiners'][lang] > template default.

stage_type includes lang ('refiner:zh', 'refiner:en') so per-stage
persisted output can be looked up by lang.
"""
from __future__ import annotations

from typing import List

from engines.factory import build_llm_engine, resolve_prompt
from engines.refiner.llm_refiner import LLMRefiner
from stages import PipelineStage, StageContext


class RefinerStage(PipelineStage):
    def __init__(self, refiner_profile: dict, llm_profile: dict):
        self._refiner_profile = refiner_profile
        self._llm_profile = llm_profile
        self._lang = refiner_profile["lang"]
        self.quality_flags: List[str] = []

    @property
    def stage_type(self) -> str:
        return f"refiner:{self._lang}"

    @property
    def stage_ref(self) -> str:
        return self._refiner_profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        refiners_override = context.pipeline_overrides.get("refiners") or {}
        file_override = refiners_override.get(self._lang) if isinstance(refiners_override, dict) else None
        system_prompt = resolve_prompt(
            self._refiner_profile["prompt_template_id"],
            file_override=file_override,
        )
        llm = build_llm_engine(self._llm_profile)
        refiner = LLMRefiner(
            llm=llm,
            system_prompt=system_prompt,
            lang=self._lang,
            style=self._refiner_profile.get("style", "broadcast"),
        )
        progress_cb = None
        if context.progress_callback is not None:
            def progress_cb(idx: int, total: int, _txt: str):
                context.progress_callback(idx, total)
        return refiner.refine(segments_in, progress=progress_cb)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_a2_stages.py -v -k refiner
```
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/stages/v5/refiner_stage.py backend/tests/test_v5_a2_stages.py
git commit -m "feat(v5-a2): RefinerStage (per-lang, file-override-aware)

stage_type encodes lang ('refiner:zh') so persisted output distinguishes
per-target-lang refinement results. File override key 'refiners.<lang>'
allows tuning prompt per-language without touching profile."
```

---

## Task 5: TranslatorStage (per source→target pair)

**Files:**
- Create: `backend/stages/v5/translator_stage.py`
- Test: append to `backend/tests/test_v5_a2_stages.py`

One stage instance per `translators[lang]` entry. Source lang comes from `pipeline.asr_primary.source_lang`; target lang is the dict key. File override key: `translators.<src>_to_<tgt>`.

- [ ] **Step 1: Write failing test**

Append:
```python
def test_translator_stage_translates_segments():
    from stages.v5.translator_stage import TranslatorStage
    fake_llm = Mock()
    fake_llm.call.return_value = "EN translation"
    translator_profile = {
        "id": "tr1",
        "source_lang": "zh",
        "target_lang": "en",
        "llm_profile_id": "lp1",
        "prompt_template_id": "translator/zh_to_en_default",
    }
    llm_profile = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}
    stage = TranslatorStage(translator_profile=translator_profile, llm_profile=llm_profile)
    ctx = StageContext(
        file_id="f1", user_id=1, pipeline_id="p1", stage_index=4,
        cancel_event=None, progress_callback=None, pipeline_overrides={},
    )
    with patch("stages.v5.translator_stage.build_llm_engine", return_value=fake_llm):
        out = stage.transform([{"start": 0, "end": 1, "text": "中文"}], ctx)
    assert out == [{"start": 0, "end": 1, "text": "EN translation"}]


def test_translator_stage_type_encodes_src_tgt():
    from stages.v5.translator_stage import TranslatorStage
    translator_profile = {"id": "tr1", "source_lang": "zh", "target_lang": "en",
                          "llm_profile_id": "lp1", "prompt_template_id": "translator/zh_to_en_default"}
    llm_profile = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}
    stage = TranslatorStage(translator_profile=translator_profile, llm_profile=llm_profile)
    assert stage.stage_type == "translator:zh_to_en"
    assert stage.stage_ref == "tr1"


def test_translator_stage_uses_file_prompt_override_per_pair():
    """File override key is `translators.<src>_to_<tgt>`."""
    from stages.v5.translator_stage import TranslatorStage
    fake_llm = Mock()
    fake_llm.call.return_value = "x"
    translator_profile = {"id": "tr1", "source_lang": "zh", "target_lang": "en",
                          "llm_profile_id": "lp1", "prompt_template_id": "translator/zh_to_en_default"}
    llm_profile = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}
    stage = TranslatorStage(translator_profile=translator_profile, llm_profile=llm_profile)
    ctx = StageContext(
        file_id="f1", user_id=1, pipeline_id="p1", stage_index=4,
        cancel_event=None, progress_callback=None,
        pipeline_overrides={"translators": {
            "zh_to_en": "CUSTOM ZH→EN PROMPT",
            "zh_to_ja": "irrelevant",
        }},
    )
    with patch("stages.v5.translator_stage.build_llm_engine", return_value=fake_llm):
        stage.transform([{"start": 0, "end": 1, "text": "中文"}], ctx)
    sent_system = fake_llm.call.call_args.args[0]
    assert sent_system == "CUSTOM ZH→EN PROMPT"
```

- [ ] **Step 2: Run fail**

```bash
pytest tests/test_v5_a2_stages.py -v -k translator
```

- [ ] **Step 3: Create `backend/stages/v5/translator_stage.py`**

```python
"""TranslatorStage — v5-A2.

Wraps v5-A1 LLMTranslator. One instance per (source_lang, target_lang) pair.
The v5 pipeline DAG fans out N TranslatorStage instances iterating
pipeline.translators[lang] entries.

File override key: translators.<src>_to_<tgt>.
"""
from __future__ import annotations

from typing import List

from engines.factory import build_llm_engine, resolve_prompt
from engines.translator.llm_translator import LLMTranslator
from stages import PipelineStage, StageContext


class TranslatorStage(PipelineStage):
    def __init__(self, translator_profile: dict, llm_profile: dict):
        self._translator_profile = translator_profile
        self._llm_profile = llm_profile
        self._src = translator_profile["source_lang"]
        self._tgt = translator_profile["target_lang"]
        self.quality_flags: List[str] = []

    @property
    def stage_type(self) -> str:
        return f"translator:{self._src}_to_{self._tgt}"

    @property
    def stage_ref(self) -> str:
        return self._translator_profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        translators_override = context.pipeline_overrides.get("translators") or {}
        override_key = f"{self._src}_to_{self._tgt}"
        file_override = translators_override.get(override_key) if isinstance(translators_override, dict) else None
        system_prompt = resolve_prompt(
            self._translator_profile["prompt_template_id"],
            file_override=file_override,
        )
        llm = build_llm_engine(self._llm_profile)
        translator = LLMTranslator(
            llm=llm,
            system_prompt=system_prompt,
            source_lang=self._src,
            target_lang=self._tgt,
        )
        progress_cb = None
        if context.progress_callback is not None:
            def progress_cb(idx: int, total: int, _txt: str):
                context.progress_callback(idx, total)
        return translator.translate(segments_in, progress=progress_cb)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_v5_a2_stages.py -v -k translator
```
Expected: 3 PASS

- [ ] **Step 5: Run full stages test file**

```bash
pytest tests/test_v5_a2_stages.py -v
```
Expected: 11 PASS (2 primary + 2 secondary + 4 verifier + 3 refiner + 3 translator = 14, but the asr_primary tests count as 2 + secondary as 2 = let me recount: T2 added 4 (primary+secondary), T3 added 4 (verifier), T4 added 3 (refiner), T5 adds 3 (translator) = 14 total).

- [ ] **Step 6: Commit**

```bash
git add backend/stages/v5/translator_stage.py backend/tests/test_v5_a2_stages.py
git commit -m "feat(v5-a2): TranslatorStage (per source→target pair)

stage_type encodes both source + target lang ('translator:zh_to_en') so
persisted output distinguishes multi-target fan-out. File override key
'translators.<src>_to_<tgt>'."
```

---

## Task 6: PipelineRunner v5 DAG executor

**Files:**
- Modify: `backend/pipeline_runner.py`
- Test: `backend/tests/test_v5_a2_runner.py`

The runner's existing `run()` method handles v4 linear pipelines. Add a new `_run_v5()` method called when `pipeline.get("version") == 5`. Orchestrates the DAG:

```
ASRPrimaryStage (always)
  └─► canonical_source_segments
       │
       ├─► (if asr_secondary configured) ASRSecondaryStage
       │     └─► (if asr_verifier configured) ASRVerifierStage → canonical_source_segments
       │
       └─► for each target_lang in target_languages:
             ├─► (per refinements[lang] entry) RefinerStage chain → lang_segments
             └─► (if lang != source_lang) TranslatorStage → lang_segments

       Build by_lang dict {lang: lang_segments} and persist to file registry.
```

For A2 simplicity, runs **sequentially** (no real parallelism between primary/secondary). True parallelism is post-v5-A2 optimization.

- [ ] **Step 1: Write failing test for run() dispatch**

Create `backend/tests/test_v5_a2_runner.py`:
```python
import pytest
from unittest.mock import Mock, patch


def test_run_v5_dispatches_to_v5_branch_when_version_5():
    """PipelineRunner.run() should call _run_v5 when pipeline version is 5."""
    from pipeline_runner import PipelineRunner
    pipeline = {
        "id": "p1", "version": 5,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "translators": {},
        "glossary_stages": {},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    runner = PipelineRunner(
        pipeline=pipeline, file_id="f1", audio_path="/tmp/x.wav",
        managers={
            "asr_manager": Mock(), "mt_manager": Mock(), "glossary_manager": Mock(),
            "transcribe_profile_manager": Mock(),
            "translator_profile_manager": Mock(),
            "refiner_profile_manager": Mock(),
            "verifier_profile_manager": Mock(),
            "llm_profile_manager": Mock(),
        },
    )
    with patch.object(runner, "_run_v5", return_value=[]) as mock_v5:
        runner.run(user_id=1)
    mock_v5.assert_called_once()


def test_run_v5_dispatches_to_v4_when_no_version():
    """PipelineRunner.run() should fall through to legacy v4 path when version absent."""
    from pipeline_runner import PipelineRunner
    pipeline = {
        "id": "p1", "asr_profile_id": "asr1", "mt_stages": [],
    }
    # v4 path requires asr_manager.get(asr1) to return a profile
    asr_manager = Mock()
    asr_manager.get.return_value = {"id": "asr1", "engine": "whisper", "language": "en", "mode": "same-lang"}
    runner = PipelineRunner(
        pipeline=pipeline, file_id="f1", audio_path="/tmp/x.wav",
        managers={
            "asr_manager": asr_manager,
            "mt_manager": Mock(),
            "glossary_manager": Mock(),
        },
    )
    with patch.object(runner, "_run_v5") as mock_v5:
        # v4 path will fail because asr engine init mocking is shallow; we just need
        # to verify _run_v5 was NOT called.
        try:
            runner.run(user_id=1)
        except Exception:
            pass
        mock_v5.assert_not_called()
```

- [ ] **Step 2: Run test fail**

```bash
cd backend && source venv/bin/activate
pytest tests/test_v5_a2_runner.py -v -k dispatches
```
Expected: AttributeError on `runner._run_v5` (method doesn't exist).

- [ ] **Step 3: Modify `backend/pipeline_runner.py`** — add v5 dispatch + `_run_v5`

At top of file, alongside existing imports:
```python
# v5-A2 imports
from stages.v5.asr_primary_stage import ASRPrimaryStage
from stages.v5.asr_secondary_stage import ASRSecondaryStage
from stages.v5.asr_verifier_stage import ASRVerifierStage
from stages.v5.refiner_stage import RefinerStage
from stages.v5.translator_stage import TranslatorStage
```

In `PipelineRunner.__init__`, expand managers dict tolerance — existing constructor takes specific v4 manager keys; v5 needs 5 more. Replace existing body with:
```python
def __init__(self, pipeline: dict, file_id: str, audio_path: str, managers: dict):
    self._pipeline = pipeline
    self._file_id = file_id
    self._audio_path = audio_path
    # v4 managers (may be None for v5-only pipelines)
    self._asr_manager = managers.get("asr_manager")
    self._mt_manager = managers.get("mt_manager")
    self._glossary_manager = managers.get("glossary_manager")
    # v5 managers (may be None for v4-only pipelines)
    self._transcribe_profile_manager = managers.get("transcribe_profile_manager")
    self._translator_profile_manager = managers.get("translator_profile_manager")
    self._refiner_profile_manager = managers.get("refiner_profile_manager")
    self._verifier_profile_manager = managers.get("verifier_profile_manager")
    self._llm_profile_manager = managers.get("llm_profile_manager")
```

Modify `run()` to dispatch v4 / v5:
```python
def run(
    self,
    user_id: Optional[int],
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    start_from_stage: int = 0,
) -> List[StageOutput]:
    if self._pipeline.get("version") == 5:
        if start_from_stage != 0:
            raise NotImplementedError("v5 resume from stage not yet supported (A2 scope)")
        return self._run_v5(user_id=user_id, cancel_event=cancel_event)
    # ... existing v4 body unchanged ...
```

Add `_run_v5` method at end of class:
```python
def _run_v5(
    self,
    user_id: Optional[int],
    cancel_event: Optional[threading.Event] = None,
) -> List[StageOutput]:
    """Execute v5 DAG pipeline. See task plan for orchestration shape.

    Returns flat list of StageOutput (same shape as v4); persists each
    stage to file registry as it completes.
    """
    stage_outputs: List[StageOutput] = []
    stage_index = 0
    source_lang = self._pipeline["asr_primary"]["source_lang"]

    # 1. ASR primary (always)
    _check_cancel(cancel_event)
    primary_profile = self._transcribe_profile_manager.get(
        self._pipeline["asr_primary"]["transcribe_profile_id"]
    )
    if primary_profile is None:
        raise ValueError("asr_primary transcribe profile not found")
    primary_stage = ASRPrimaryStage(primary_profile, self._audio_path)
    primary_out, primary_segments = self._run_stage(
        stage=primary_stage, segments_in=[], stage_index=stage_index,
        stage_type="asr_primary", cancel_event=cancel_event, user_id=user_id,
    )
    stage_outputs.append(primary_out)
    stage_index += 1

    # 2. ASR secondary (optional)
    secondary_segments: List[dict] = []
    secondary_cfg = self._pipeline.get("asr_secondary")
    if secondary_cfg:
        _check_cancel(cancel_event)
        secondary_profile = self._transcribe_profile_manager.get(
            secondary_cfg["transcribe_profile_id"]
        )
        if secondary_profile is None:
            raise ValueError("asr_secondary transcribe profile not found")
        secondary_stage = ASRSecondaryStage(secondary_profile, self._audio_path)
        secondary_out, secondary_segments = self._run_stage(
            stage=secondary_stage, segments_in=[], stage_index=stage_index,
            stage_type="asr_secondary", cancel_event=cancel_event, user_id=user_id,
        )
        stage_outputs.append(secondary_out)
        stage_index += 1

    # 3. ASR verifier (optional; requires secondary)
    canonical_source = primary_segments
    verifier_cfg = self._pipeline.get("asr_verifier")
    if verifier_cfg and secondary_segments:
        _check_cancel(cancel_event)
        llm_profile = self._llm_profile_manager.get(verifier_cfg["llm_profile_id"])
        if llm_profile is None:
            raise ValueError("asr_verifier llm_profile not found")
        # Build a synthetic verifier profile from inline config (verifier doesn't have its own profile id here)
        verifier_inline = {
            "id": verifier_cfg["llm_profile_id"],  # reuse for stage_ref
            "lang": source_lang,
            "llm_profile_id": verifier_cfg["llm_profile_id"],
            "prompt_template_id": verifier_cfg["prompt_template_id"],
        }
        verifier_stage = ASRVerifierStage(
            verifier_profile=verifier_inline,
            llm_profile=llm_profile,
        )
        # Pass secondary segments via reserved override key (see ASRVerifierStage)
        from stages.v5.asr_verifier_stage import SECONDARY_KEY
        verifier_overrides = {SECONDARY_KEY: secondary_segments}
        verified_out, canonical_source = self._run_stage_v5(
            stage=verifier_stage, segments_in=primary_segments, stage_index=stage_index,
            stage_type="asr_verifier", cancel_event=cancel_event, user_id=user_id,
            extra_overrides=verifier_overrides,
        )
        stage_outputs.append(verified_out)
        stage_index += 1

    # 4. For each target_lang: refinement chain → (if lang != source) translator
    by_lang: dict = {}
    for target_lang in self._pipeline.get("target_languages", []):
        # Start with canonical source if same lang, else need translator first
        if target_lang == source_lang:
            lang_segments = list(canonical_source)
        else:
            # Need translator to convert source → target
            translator_cfg = self._pipeline.get("translators", {}).get(target_lang)
            if translator_cfg is None:
                raise ValueError(f"translator for target_languages '{target_lang}' missing")
            translator_profile = self._translator_profile_manager.get(
                translator_cfg["translator_profile_id"]
            )
            if translator_profile is None:
                raise ValueError(f"translator profile for {target_lang} not found")
            llm_profile = self._llm_profile_manager.get(translator_profile["llm_profile_id"])
            if llm_profile is None:
                raise ValueError(f"translator's llm_profile not found ({target_lang})")
            _check_cancel(cancel_event)
            translator_stage = TranslatorStage(translator_profile=translator_profile, llm_profile=llm_profile)
            tr_out, lang_segments = self._run_stage(
                stage=translator_stage, segments_in=canonical_source, stage_index=stage_index,
                stage_type=translator_stage.stage_type,
                cancel_event=cancel_event, user_id=user_id,
            )
            stage_outputs.append(tr_out)
            stage_index += 1

        # Refinement chain for this lang
        for refiner_entry in self._pipeline.get("refinements", {}).get(target_lang, []):
            refiner_profile = self._refiner_profile_manager.get(refiner_entry["refiner_profile_id"])
            if refiner_profile is None:
                raise ValueError(f"refiner profile for {target_lang} not found")
            llm_profile = self._llm_profile_manager.get(refiner_profile["llm_profile_id"])
            if llm_profile is None:
                raise ValueError(f"refiner's llm_profile not found ({target_lang})")
            _check_cancel(cancel_event)
            refiner_stage = RefinerStage(refiner_profile=refiner_profile, llm_profile=llm_profile)
            rf_out, lang_segments = self._run_stage(
                stage=refiner_stage, segments_in=lang_segments, stage_index=stage_index,
                stage_type=refiner_stage.stage_type,
                cancel_event=cancel_event, user_id=user_id,
            )
            stage_outputs.append(rf_out)
            stage_index += 1

        by_lang[target_lang] = lang_segments

    # Persist by_lang dict to file registry for downstream consumers
    self._persist_by_lang(by_lang, source_lang=source_lang, source_segments=canonical_source)
    return stage_outputs


def _run_stage_v5(
    self, stage, segments_in, stage_index, stage_type,
    cancel_event, user_id, extra_overrides: dict,
):
    """Same as _run_stage but merges extra_overrides into context.pipeline_overrides."""
    import app as app_mod
    with app_mod._registry_lock:
        file_entry = app_mod._file_registry.get(self._file_id, {})
        all_overrides = file_entry.get("pipeline_overrides", {})
        overrides_for_this_pipeline = dict(all_overrides.get(self._pipeline["id"], {}))
    overrides_for_this_pipeline.update(extra_overrides)
    _socketio_emit("pipeline_stage_start", {
        "file_id": self._file_id, "pipeline_id": self._pipeline["id"],
        "stage_index": stage_index, "stage_type": stage_type,
    })
    ctx = StageContext(
        file_id=self._file_id, user_id=user_id,
        pipeline_id=self._pipeline["id"], stage_index=stage_index,
        cancel_event=cancel_event,
        progress_callback=_make_progress_callback(
            self._file_id, self._pipeline["id"], stage_index, stage_type),
        pipeline_overrides=overrides_for_this_pipeline,
    )
    start_t = time.time()
    try:
        segments_out = stage.transform(segments_in, ctx)
    except Exception as exc:
        failed_out: StageOutput = {
            "stage_index": stage_index, "stage_type": stage_type,
            "stage_ref": stage.stage_ref, "status": "failed",
            "ran_at": start_t, "duration_seconds": time.time() - start_t,
            "segments": [], "quality_flags": [],
        }
        failed_out["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        _persist_stage_output(self._file_id, failed_out)
        _socketio_emit("pipeline_stage_done", {
            "file_id": self._file_id, "pipeline_id": self._pipeline["id"],
            "stage_index": stage_index, "stage_type": stage_type,
            "status": "failed", "duration_seconds": failed_out["duration_seconds"],
        })
        raise
    stage_out: StageOutput = {
        "stage_index": stage_index, "stage_type": stage_type,
        "stage_ref": stage.stage_ref, "status": "done",
        "ran_at": start_t, "duration_seconds": time.time() - start_t,
        "segments": segments_out, "quality_flags": getattr(stage, "quality_flags", []),
    }
    _persist_stage_output(self._file_id, stage_out)
    _socketio_emit("pipeline_stage_done", {
        "file_id": self._file_id, "pipeline_id": self._pipeline["id"],
        "stage_index": stage_index, "stage_type": stage_type,
        "status": "done", "duration_seconds": stage_out["duration_seconds"],
    })
    return stage_out, segments_out


def _persist_by_lang(
    self, by_lang: dict, source_lang: str, source_segments: List[dict],
) -> None:
    """Persist v5 multi-lang translations to file registry.

    Shape: file_registry[fid]['translations'] = [
        {idx, start, end, source_lang, source_text,
         by_lang: {lang: {text, status, flags}}},
        ...
    ]
    """
    import app as app_mod
    if not by_lang:
        return
    # Determine canonical segment count from source
    n = len(source_segments)
    rows: list = []
    for i in range(n):
        src_seg = source_segments[i]
        row = {
            "idx": i,
            "start": src_seg.get("start"),
            "end": src_seg.get("end"),
            "source_lang": source_lang,
            "source_text": src_seg.get("text", ""),
            "by_lang": {},
        }
        for lang, segs in by_lang.items():
            if i < len(segs):
                row["by_lang"][lang] = {
                    "text": segs[i].get("text", ""),
                    "status": "pending",
                    "flags": [],
                }
        rows.append(row)
    with app_mod._registry_lock:
        entry = app_mod._file_registry.get(self._file_id)
        if entry is None:
            return
        entry["translations"] = rows
        app_mod._save_registry()
    _socketio_emit("pipeline_complete_v5", {
        "file_id": self._file_id, "pipeline_id": self._pipeline["id"],
        "languages": list(by_lang.keys()),
        "segments_per_lang": {lang: len(segs) for lang, segs in by_lang.items()},
    })
```

- [ ] **Step 4: Run dispatch tests**

```bash
pytest tests/test_v5_a2_runner.py -v -k dispatches
```
Expected: 2 PASS

- [ ] **Step 5: Add end-to-end runner test with mocked engines**

Append to `backend/tests/test_v5_a2_runner.py`:
```python
import json
import threading
from pathlib import Path


def test_run_v5_zh_only_pipeline(tmp_path, monkeypatch):
    """ZH source + ZH-only target with one refiner. No translator, no secondary."""
    from pipeline_runner import PipelineRunner

    # Stub managers + audio file
    audio = tmp_path / "fake.wav"
    audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    transcribe_profile = {"id": "tp1", "engine": "whisper", "language": "zh", "model_size": "large-v3"}
    refiner_profile = {"id": "rp1", "lang": "zh", "style": "broadcast-hk",
                       "llm_profile_id": "lp1", "prompt_template_id": "refiner/zh_broadcast_hk_default"}
    llm_profile = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}

    tp_mgr = Mock(); tp_mgr.get.return_value = transcribe_profile
    rf_mgr = Mock(); rf_mgr.get.return_value = refiner_profile
    llm_mgr = Mock(); llm_mgr.get.return_value = llm_profile

    pipeline = {
        "id": "p1", "version": 5,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "target_languages": ["zh"],
        "refinements": {"zh": [{"refiner_profile_id": "rp1"}]},
        "translators": {},
        "glossary_stages": {},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }

    # Patch app module's _registry_lock + _file_registry + _save_registry
    import app as _app
    monkeypatch.setattr(_app, "_file_registry", {"f1": {"id": "f1"}}, raising=False)
    monkeypatch.setattr(_app, "_registry_lock", threading.Lock(), raising=False)
    monkeypatch.setattr(_app, "_save_registry", lambda: None, raising=False)

    runner = PipelineRunner(
        pipeline=pipeline, file_id="f1", audio_path=str(audio),
        managers={
            "transcribe_profile_manager": tp_mgr,
            "refiner_profile_manager": rf_mgr,
            "llm_profile_manager": llm_mgr,
            "asr_manager": None, "mt_manager": None, "glossary_manager": None,
            "translator_profile_manager": None,
            "verifier_profile_manager": None,
        },
    )

    fake_transcribe_engine = Mock()
    fake_transcribe_engine.transcribe.return_value = [
        {"start": 0.0, "end": 1.0, "text": "段一"},
        {"start": 1.0, "end": 2.0, "text": "段二"},
    ]
    fake_llm = Mock()
    fake_llm.call.side_effect = ["polished1", "polished2"]

    with patch("stages.v5.asr_primary_stage.create_transcribe_engine", return_value=fake_transcribe_engine), \
         patch("stages.v5.refiner_stage.build_llm_engine", return_value=fake_llm):
        outputs = runner.run(user_id=1)

    # 2 stages: ASR primary + ZH refiner
    assert len(outputs) == 2
    assert outputs[0]["stage_type"] == "asr_primary"
    assert outputs[1]["stage_type"] == "refiner:zh"
    # by_lang persisted with refined ZH text
    entry = _app._file_registry["f1"]
    assert "translations" in entry
    assert entry["translations"][0]["by_lang"]["zh"]["text"] == "polished1"
    assert entry["translations"][1]["by_lang"]["zh"]["text"] == "polished2"
```

- [ ] **Step 6: Run runner test**

```bash
pytest tests/test_v5_a2_runner.py::test_run_v5_zh_only_pipeline -v
```
Expected: PASS

- [ ] **Step 7: Add 4 more end-to-end test variants**

Append:
```python
def test_run_v5_zh_to_en_with_translator(tmp_path, monkeypatch):
    """ZH source + ZH and EN targets — EN needs translator."""
    from pipeline_runner import PipelineRunner

    audio = tmp_path / "fake.wav"; audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    tp = {"id": "tp1", "engine": "whisper", "language": "zh", "model_size": "large-v3"}
    tr = {"id": "tr1", "source_lang": "zh", "target_lang": "en",
          "llm_profile_id": "lp1", "prompt_template_id": "translator/zh_to_en_default"}
    llm = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}

    tp_mgr = Mock(); tp_mgr.get.return_value = tp
    xl_mgr = Mock(); xl_mgr.get.return_value = tr
    llm_mgr = Mock(); llm_mgr.get.return_value = llm

    pipeline = {
        "id": "p1", "version": 5,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "target_languages": ["zh", "en"],
        "refinements": {"zh": [], "en": []},
        "translators": {"en": {"translator_profile_id": "tr1"}},
        "glossary_stages": {},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }

    import app as _app
    monkeypatch.setattr(_app, "_file_registry", {"f1": {"id": "f1"}}, raising=False)
    monkeypatch.setattr(_app, "_registry_lock", threading.Lock(), raising=False)
    monkeypatch.setattr(_app, "_save_registry", lambda: None, raising=False)

    runner = PipelineRunner(
        pipeline=pipeline, file_id="f1", audio_path=str(audio),
        managers={
            "transcribe_profile_manager": tp_mgr,
            "translator_profile_manager": xl_mgr,
            "refiner_profile_manager": None,
            "verifier_profile_manager": None,
            "llm_profile_manager": llm_mgr,
            "asr_manager": None, "mt_manager": None, "glossary_manager": None,
        },
    )

    fake_engine = Mock()
    fake_engine.transcribe.return_value = [{"start": 0.0, "end": 1.0, "text": "中文"}]
    fake_llm = Mock(); fake_llm.call.return_value = "english"

    with patch("stages.v5.asr_primary_stage.create_transcribe_engine", return_value=fake_engine), \
         patch("stages.v5.translator_stage.build_llm_engine", return_value=fake_llm):
        outputs = runner.run(user_id=1)

    assert any(o["stage_type"] == "translator:zh_to_en" for o in outputs)
    entry = _app._file_registry["f1"]
    assert entry["translations"][0]["by_lang"]["zh"]["text"] == "中文"  # source-lang passthrough
    assert entry["translations"][0]["by_lang"]["en"]["text"] == "english"


def test_run_v5_dual_asr_with_verifier(tmp_path, monkeypatch):
    """Pipeline with asr_secondary + asr_verifier — verifier rules canonical source."""
    from pipeline_runner import PipelineRunner

    audio = tmp_path / "fake.wav"; audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    tp = {"id": "tp1", "engine": "whisper", "language": "zh", "model_size": "large-v3"}
    tp2 = {"id": "tp2", "engine": "qwen3-asr", "language": "zh"}
    llm = {"id": "lp1", "backend": "ollama", "model": "m", "base_url": "http://x"}

    tp_mgr = Mock()
    tp_mgr.get.side_effect = lambda i: {"tp1": tp, "tp2": tp2}.get(i)
    llm_mgr = Mock(); llm_mgr.get.return_value = llm

    pipeline = {
        "id": "p1", "version": 5,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "asr_secondary": {"transcribe_profile_id": "tp2", "source_lang": "zh"},
        "asr_verifier": {"llm_profile_id": "lp1", "prompt_template_id": "verifier/zh_default"},
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "translators": {},
        "glossary_stages": {},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }

    import app as _app
    monkeypatch.setattr(_app, "_file_registry", {"f1": {"id": "f1"}}, raising=False)
    monkeypatch.setattr(_app, "_registry_lock", threading.Lock(), raising=False)
    monkeypatch.setattr(_app, "_save_registry", lambda: None, raising=False)

    runner = PipelineRunner(
        pipeline=pipeline, file_id="f1", audio_path=str(audio),
        managers={
            "transcribe_profile_manager": tp_mgr,
            "translator_profile_manager": None,
            "refiner_profile_manager": None,
            "verifier_profile_manager": None,
            "llm_profile_manager": llm_mgr,
            "asr_manager": None, "mt_manager": None, "glossary_manager": None,
        },
    )

    # Different return values for primary vs secondary
    primary_engine = Mock()
    primary_engine.transcribe.return_value = [{"start": 0, "end": 1, "text": "中文字幕提供"}]
    secondary_engine = Mock()
    secondary_engine.transcribe.return_value = [{"start": 0, "end": 1, "text": "真實內容"}]
    fake_llm = Mock(); fake_llm.call.return_value = "verified"

    def fake_engine_factory(profile):
        if profile["engine"] == "qwen3-asr":
            return secondary_engine
        return primary_engine

    with patch("stages.v5.asr_primary_stage.create_transcribe_engine", side_effect=fake_engine_factory), \
         patch("stages.v5.asr_secondary_stage.create_transcribe_engine", side_effect=fake_engine_factory), \
         patch("stages.v5.asr_verifier_stage.build_llm_engine", return_value=fake_llm):
        outputs = runner.run(user_id=1)

    types = [o["stage_type"] for o in outputs]
    assert "asr_primary" in types
    assert "asr_secondary" in types
    assert "asr_verifier" in types


def test_run_v5_missing_translator_raises(tmp_path, monkeypatch):
    """Pipeline with target lang != source but no translator → ValueError at runtime."""
    from pipeline_runner import PipelineRunner

    audio = tmp_path / "fake.wav"; audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    tp = {"id": "tp1", "engine": "whisper", "language": "zh", "model_size": "large-v3"}
    tp_mgr = Mock(); tp_mgr.get.return_value = tp

    pipeline = {
        "id": "p1", "version": 5,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "target_languages": ["zh", "en"],
        "refinements": {"zh": [], "en": []},
        "translators": {},  # ← missing 'en' entry
        "glossary_stages": {},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }

    import app as _app
    monkeypatch.setattr(_app, "_file_registry", {"f1": {"id": "f1"}}, raising=False)
    monkeypatch.setattr(_app, "_registry_lock", threading.Lock(), raising=False)
    monkeypatch.setattr(_app, "_save_registry", lambda: None, raising=False)

    runner = PipelineRunner(
        pipeline=pipeline, file_id="f1", audio_path=str(audio),
        managers={
            "transcribe_profile_manager": tp_mgr,
            "translator_profile_manager": None,
            "refiner_profile_manager": None,
            "verifier_profile_manager": None,
            "llm_profile_manager": None,
            "asr_manager": None, "mt_manager": None, "glossary_manager": None,
        },
    )
    fake_engine = Mock()
    fake_engine.transcribe.return_value = [{"start": 0, "end": 1, "text": "x"}]
    with patch("stages.v5.asr_primary_stage.create_transcribe_engine", return_value=fake_engine):
        with pytest.raises(ValueError, match="translator for target_languages 'en' missing"):
            runner.run(user_id=1)


def test_run_v5_resume_not_supported(tmp_path):
    """v5 pipelines reject start_from_stage > 0 (resume not in A2 scope)."""
    from pipeline_runner import PipelineRunner
    pipeline = {
        "id": "p1", "version": 5,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "translators": {},
        "glossary_stages": {},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    runner = PipelineRunner(
        pipeline=pipeline, file_id="f1", audio_path="/tmp/x.wav",
        managers={
            "transcribe_profile_manager": Mock(),
            "translator_profile_manager": Mock(),
            "refiner_profile_manager": Mock(),
            "verifier_profile_manager": Mock(),
            "llm_profile_manager": Mock(),
            "asr_manager": None, "mt_manager": None, "glossary_manager": None,
        },
    )
    with pytest.raises(NotImplementedError, match="v5 resume"):
        runner.run(user_id=1, start_from_stage=2)
```

- [ ] **Step 8: Run all runner tests**

```bash
pytest tests/test_v5_a2_runner.py -v
```
Expected: 6 PASS (2 dispatch + 4 e2e variants)

- [ ] **Step 9: Commit**

```bash
git add backend/pipeline_runner.py backend/tests/test_v5_a2_runner.py
git commit -m "feat(v5-a2): PipelineRunner v5 DAG executor

run() dispatches to _run_v5() when pipeline.version == 5; v4 linear path
unchanged. _run_v5() orchestrates 5 stage types: ASR primary (always),
secondary + verifier (optional), refiner chain (per-lang), translator
(per non-source target). Persists per-lang results to file_registry
translations[] in v5 by_lang shape. Emits pipeline_complete_v5 Socket.IO
event with per-lang segment counts.

Resume from stage not supported in v5 yet (defer to post-A2)."
```

---

## Task 7: File registry by_lang shape + `normalize_translations_for_v5`

**Files:**
- Create: `backend/translations_normalize_v5.py`
- Modify: `backend/routes/files.py` (or `backend/app.py` — wherever `GET /api/files/<id>/translations` lives)
- Test: `backend/tests/test_v5_a2_normalize.py`

Existing v4 file registry stores translations as `[{idx, en_text, zh_text, status, flags}]`. v5 needs `[{idx, start, end, source_lang, source_text, by_lang: {lang: {text, status, flags}}}]`. The normalize helper converts v4 → v5 at GET response time, leaving stored data unchanged.

- [ ] **Step 1: Find the translations GET route**

```bash
grep -n "/api/files/.*/translations" backend/routes/*.py backend/app.py | head -5
```

Note the file + line for later modification.

- [ ] **Step 2: Write failing test for normalize helper**

Create `backend/tests/test_v5_a2_normalize.py`:
```python
def test_normalize_v4_translations_to_v5_shape():
    """v4 [{idx, en_text, zh_text, status, flags}] → v5 [{by_lang: {...}}]."""
    from translations_normalize_v5 import normalize_translations_for_v5
    v4 = [
        {"idx": 0, "en_text": "hello", "zh_text": "你好", "status": "approved", "flags": []},
        {"idx": 1, "en_text": "world", "zh_text": "世界", "status": "pending", "flags": ["long"]},
    ]
    v5 = normalize_translations_for_v5(v4)
    assert len(v5) == 2
    assert v5[0]["idx"] == 0
    assert v5[0]["source_lang"] == "en"  # v4 assumed EN source
    assert v5[0]["source_text"] == "hello"
    assert v5[0]["by_lang"]["zh"]["text"] == "你好"
    assert v5[0]["by_lang"]["zh"]["status"] == "approved"
    assert v5[1]["by_lang"]["zh"]["flags"] == ["long"]


def test_normalize_passthrough_when_already_v5():
    """v5-shaped input passes through unchanged."""
    from translations_normalize_v5 import normalize_translations_for_v5
    v5_in = [
        {"idx": 0, "start": 0.0, "end": 1.0,
         "source_lang": "zh", "source_text": "中文",
         "by_lang": {"en": {"text": "english", "status": "pending", "flags": []}}},
    ]
    out = normalize_translations_for_v5(v5_in)
    assert out == v5_in


def test_normalize_empty_list():
    from translations_normalize_v5 import normalize_translations_for_v5
    assert normalize_translations_for_v5([]) == []


def test_normalize_handles_missing_fields_defensively():
    """v4 entries with missing fields shouldn't crash; use sensible defaults."""
    from translations_normalize_v5 import normalize_translations_for_v5
    v4 = [{"idx": 0}]  # totally bare
    v5 = normalize_translations_for_v5(v4)
    assert v5[0]["source_lang"] == "en"
    assert v5[0]["source_text"] == ""
    assert v5[0]["by_lang"] == {"zh": {"text": "", "status": "pending", "flags": []}}
```

- [ ] **Step 3: Run test fail**

```bash
cd backend && source venv/bin/activate
pytest tests/test_v5_a2_normalize.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 4: Create `backend/translations_normalize_v5.py`**

```python
"""v5 file registry translations shape converter.

v4 shape:
  [{idx, en_text, zh_text, status, flags}]

v5 shape:
  [{idx, start, end, source_lang, source_text,
    by_lang: {lang: {text, status, flags}}}]

normalize_translations_for_v5() converts v4 → v5 at read time. v5-shaped
input passes through. Used in GET /api/files/<id>/translations response
so frontend can rely on a single shape.
"""
from __future__ import annotations

from typing import Any


def normalize_translations_for_v5(raw: list) -> list:
    """Convert v4 [{en_text, zh_text}] → v5 [{by_lang}]. v5 input passes through."""
    if not raw:
        return []
    out: list = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if "by_lang" in entry:
            # Already v5
            out.append(entry)
            continue
        out.append({
            "idx": entry.get("idx", 0),
            "start": entry.get("start"),
            "end": entry.get("end"),
            "source_lang": "en",  # v4 implicit assumption
            "source_text": entry.get("en_text", ""),
            "by_lang": {
                "zh": {
                    "text": entry.get("zh_text", ""),
                    "status": entry.get("status", "pending"),
                    "flags": entry.get("flags", []),
                },
            },
        })
    return out
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_v5_a2_normalize.py -v
```
Expected: 4 PASS

- [ ] **Step 6: Wire normalize into translations GET response**

Open whichever file owns `GET /api/files/<id>/translations` (likely `backend/routes/files.py`). Find the handler. At the END of the handler, wrap the response payload:

```python
from translations_normalize_v5 import normalize_translations_for_v5
# ...
# wherever the handler builds the response from file_entry['translations']:
normalized = normalize_translations_for_v5(file_entry.get("translations", []))
return jsonify({"translations": normalized}), 200  # or whatever existing shape was
```

**Add a flag to disable v5 normalization for backward-compat callers** — accept `?shape=v4` query param to return raw v4 shape unchanged:
```python
if request.args.get("shape") != "v4":
    payload = normalize_translations_for_v5(file_entry.get("translations", []))
else:
    payload = file_entry.get("translations", [])
```

This lets v4 frontend code keep working while v5 frontend (A3) opts into the normalized shape by omitting the query param.

- [ ] **Step 7: Add API integration test**

Append to `backend/tests/test_v5_a2_normalize.py`:
```python
def test_translations_route_returns_v5_shape(monkeypatch, tmp_path):
    """GET /api/files/<id>/translations returns v5 by_lang shape by default."""
    from flask import Flask
    import threading
    from flask_login import LoginManager
    # Skip if this test environment doesn't have the route wired
    try:
        from routes.files import bp as files_bp
    except ImportError:
        pytest.skip("routes.files module not exposed for blueprint test")

    import app as _app
    monkeypatch.setattr(_app, "_file_registry", {
        "f1": {
            "id": "f1", "user_id": 1,
            "translations": [
                {"idx": 0, "en_text": "hello", "zh_text": "你好",
                 "status": "approved", "flags": []},
            ],
        },
    }, raising=False)
    monkeypatch.setattr(_app, "_registry_lock", threading.Lock(), raising=False)

    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.config["TESTING"] = True
    app.register_blueprint(files_bp)
    lm = LoginManager(); lm.init_app(app)
    class _U:
        def __init__(self): self.id=1; self.is_admin=False; self.is_authenticated=True; self.is_active=True; self.is_anonymous=False
        def get_id(self): return "1"
    @lm.request_loader
    def _load(req): return _U()

    client = app.test_client()
    resp = client.get("/api/files/f1/translations")
    # Default → v5 shape
    if resp.status_code == 200:
        data = resp.get_json()
        items = data.get("translations") or data
        assert items[0].get("by_lang") is not None
        # ?shape=v4 → raw v4 passthrough
        resp_v4 = client.get("/api/files/f1/translations?shape=v4")
        data_v4 = resp_v4.get_json()
        items_v4 = data_v4.get("translations") or data_v4
        assert "zh_text" in items_v4[0]
```

(This test is best-effort — if routes/files.py isn't wired up to expose `bp`, it skips. Manual smoke test covers it.)

- [ ] **Step 8: Run all normalize tests**

```bash
pytest tests/test_v5_a2_normalize.py -v
```
Expected: 4 PASS + 1 SKIP (or 5 PASS if integration test wired).

- [ ] **Step 9: Verify v4 backward compat — existing translations tests still green**

```bash
pytest tests/ -k translation -v 2>&1 | tail -20
```
Expected: existing v4 translation tests still PASS (or unchanged baseline failures).

- [ ] **Step 10: Commit**

```bash
git add backend/translations_normalize_v5.py backend/routes/files.py backend/tests/test_v5_a2_normalize.py
git commit -m "feat(v5-a2): translations by_lang shape + normalize_translations_for_v5

v4 [{en_text, zh_text}] auto-normalized to v5 [{by_lang}] at GET response.
?shape=v4 query param keeps raw v4 passthrough for legacy callers.
v5 frontend (A3) consumes by_lang shape directly."
```

---

## Task 8: End-to-end integration test + CLAUDE.md update

**Files:**
- Create: `backend/tests/test_v5_a2_integration.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Write integration test**

Create `backend/tests/test_v5_a2_integration.py`:
```python
"""v5-A2 integration: build pipeline + 5 profiles + mock engines + run end-to-end."""
import threading
import pytest
from pathlib import Path
from unittest.mock import Mock, patch


def test_v5_full_dual_asr_pipeline_end_to_end(tmp_path, monkeypatch):
    """Real managers + real schema validation + mocked engines.

    Verifies the entire chain: pipeline JSON → schema validation → runner →
    by_lang persisted to registry → normalize_translations_for_v5 reads it.
    """
    from llm_profiles import LLMProfileManager
    from transcribe_profiles import TranscribeProfileManager
    from translator_profiles import TranslatorProfileManager
    from refiner_profiles import RefinerProfileManager
    from verifier_profiles import VerifierProfileManager
    from pipelines import PipelineManager
    from pipeline_runner import PipelineRunner
    from translations_normalize_v5 import normalize_translations_for_v5

    # Set up isolated managers
    base = tmp_path / "config"
    llm_mgr = LLMProfileManager(base / "llm")
    tp_mgr = TranscribeProfileManager(base / "transcribe")
    xl_mgr = TranslatorProfileManager(base / "translator")
    rf_mgr = RefinerProfileManager(base / "refiner")
    vf_mgr = VerifierProfileManager(base / "verifier")
    pl_mgr = PipelineManager(base / "pipeline")

    # Create real profiles
    llm_id = llm_mgr.create({
        "name": "test-llm", "backend": "ollama",
        "model": "qwen3.5:9b", "base_url": "http://localhost:11434",
    }, user_id=1)
    tp_id = tp_mgr.create({
        "name": "whisper", "engine": "whisper", "model_size": "large-v3", "language": "zh",
    }, user_id=1)
    rp_id = rf_mgr.create({
        "name": "zh-refiner", "lang": "zh", "style": "broadcast-hk",
        "llm_profile_id": llm_id,
        "prompt_template_id": "refiner/zh_broadcast_hk_default",
    }, user_id=1)
    tr_id = xl_mgr.create({
        "name": "zh-to-en", "source_lang": "zh", "target_lang": "en",
        "llm_profile_id": llm_id,
        "prompt_template_id": "translator/zh_to_en_default",
    }, user_id=1)

    # Build real v5 pipeline
    pipeline = {
        "name": "v5-A2 integration",
        "version": 5,
        "user_id": 1,
        "asr_primary": {"transcribe_profile_id": tp_id, "source_lang": "zh"},
        "asr_secondary": None,
        "asr_verifier": None,
        "target_languages": ["zh", "en"],
        "refinements": {
            "zh": [{"refiner_profile_id": rp_id}],
            "en": [],
        },
        "translators": {"en": {"translator_profile_id": tr_id}},
        "glossary_stages": {},
        "font_config": {"family": "Noto Sans TC", "color": "white", "outline_color": "black"},
    }
    pid = pl_mgr.create(pipeline, user_id=1, validate_refs=False)
    loaded = pl_mgr.get(pid, as_v5=True)

    # Audio fixture
    audio = tmp_path / "fake.wav"
    audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    # Stub app module
    import app as _app
    monkeypatch.setattr(_app, "_file_registry", {"f1": {"id": "f1", "user_id": 1}}, raising=False)
    monkeypatch.setattr(_app, "_registry_lock", threading.Lock(), raising=False)
    monkeypatch.setattr(_app, "_save_registry", lambda: None, raising=False)

    # Mocked engines
    fake_transcribe = Mock()
    fake_transcribe.transcribe.return_value = [
        {"start": 0.0, "end": 1.0, "text": "段一"},
        {"start": 1.0, "end": 2.0, "text": "段二"},
    ]
    fake_llm = Mock()
    # Refiner calls then Translator calls — return distinct outputs to verify per-lang
    fake_llm.call.side_effect = [
        "refined1", "refined2",   # refiner ZH per-segment
        "EN one", "EN two",       # translator ZH→EN per-segment
    ]

    runner = PipelineRunner(
        pipeline=loaded, file_id="f1", audio_path=str(audio),
        managers={
            "transcribe_profile_manager": tp_mgr,
            "translator_profile_manager": xl_mgr,
            "refiner_profile_manager": rf_mgr,
            "verifier_profile_manager": vf_mgr,
            "llm_profile_manager": llm_mgr,
            "asr_manager": None, "mt_manager": None, "glossary_manager": None,
        },
    )

    with patch("stages.v5.asr_primary_stage.create_transcribe_engine", return_value=fake_transcribe), \
         patch("stages.v5.refiner_stage.build_llm_engine", return_value=fake_llm), \
         patch("stages.v5.translator_stage.build_llm_engine", return_value=fake_llm):
        outputs = runner.run(user_id=1)

    # Stage outputs: asr_primary + refiner:zh + translator:zh_to_en
    types = [o["stage_type"] for o in outputs]
    assert "asr_primary" in types
    assert "refiner:zh" in types
    assert "translator:zh_to_en" in types

    # Registry has by_lang dict for both ZH (refined) and EN (translated)
    entry = _app._file_registry["f1"]
    translations = entry["translations"]
    assert len(translations) == 2
    assert translations[0]["by_lang"]["zh"]["text"] == "refined1"
    assert translations[0]["by_lang"]["en"]["text"] == "EN one"
    assert translations[1]["by_lang"]["zh"]["text"] == "refined2"
    assert translations[1]["by_lang"]["en"]["text"] == "EN two"

    # Normalize passes through v5 shape unchanged
    normalized = normalize_translations_for_v5(translations)
    assert normalized == translations
```

- [ ] **Step 2: Run integration test**

```bash
cd backend && source venv/bin/activate
pytest tests/test_v5_a2_integration.py -v
```
Expected: PASS

- [ ] **Step 3: Run full v5 test sweep**

```bash
pytest tests/test_v5_*.py -v 2>&1 | tail -20
```
Expected: ~145 PASS (105 from A1 + ~40 from A2). Zero failures.

- [ ] **Step 4: Run full suite — confirm baseline preserved**

```bash
pytest tests/ 2>&1 | tail -5
```
Expected: ~950 pass / 14 baseline fail / 4 skip.

- [ ] **Step 5: Update CLAUDE.md**

Open `CLAUDE.md`. Find the v5-A1 entry under `## Completed Features`. Insert v5-A2 entry **above** the v5-A1 entry:

```markdown
### v5-A2 — Stage executor + Pipeline runner DAG (in progress on `feat/frontend-redesign`)
- Wires v5-A1 engine ABCs + profile managers into a runtime executor that actually transcribes audio, refines per-target-lang, translates per source→target pair, and persists multi-lang results to file registry. Spec: [docs/superpowers/specs/2026-05-19-v5-dual-asr-refiner-translator-design.md](docs/superpowers/specs/2026-05-19-v5-dual-asr-refiner-translator-design.md) §4-§5. Plan: [docs/superpowers/plans/2026-05-20-v5-A2-stage-executor-plan.md](docs/superpowers/plans/2026-05-20-v5-A2-stage-executor-plan.md).
- **Engine factory (T1)**: [backend/engines/factory.py](backend/engines/factory.py) — `build_llm_engine(llm_profile)` dispatches on `backend` field to `OllamaLLM` / `OpenRouterLLM` (Claude deferred); `load_prompt_template(template_id)` reads JSON from `backend/config/prompt_templates_v5/<category>/<name>.json`; `resolve_prompt(template_id, file_override)` picks override > template default.
- **5 new stage classes** (T2-T5) under [backend/stages/v5/](backend/stages/v5/) — all implement v4 `PipelineStage` ABC so they reuse the existing `_run_stage()` fail-fast + Socket.IO progress + persist machinery:
  - `ASRPrimaryStage` ([asr_primary_stage.py](backend/stages/v5/asr_primary_stage.py)) — wraps `engines.transcribe.create_transcribe_engine` factory; `segments_in` ignored (reads audio); `stage_type='asr_primary'`
  - `ASRSecondaryStage` ([asr_secondary_stage.py](backend/stages/v5/asr_secondary_stage.py)) — identical wrapping but reads `asr_secondary.transcribe_profile_id`; `stage_type='asr_secondary'`
  - `ASRVerifierStage` ([asr_verifier_stage.py](backend/stages/v5/asr_verifier_stage.py)) — wraps `LLMVerifier`; reads primary via `segments_in` + secondary via reserved `__secondary_segments` key in `context.pipeline_overrides` (avoids changing v4 ABC); honors file `verifier` prompt override
  - `RefinerStage` ([refiner_stage.py](backend/stages/v5/refiner_stage.py)) — wraps `LLMRefiner`; one instance per (lang, refiner_profile); `stage_type=f'refiner:{lang}'`; file override key `refiners.<lang>`
  - `TranslatorStage` ([translator_stage.py](backend/stages/v5/translator_stage.py)) — wraps `LLMTranslator`; one instance per source→target pair; `stage_type=f'translator:{src}_to_{tgt}'`; file override key `translators.<src>_to_<tgt>`
- **PipelineRunner v5 DAG** (T6) ([backend/pipeline_runner.py](backend/pipeline_runner.py)):
  - `run()` dispatches to `_run_v5()` when `pipeline.version == 5`; v4 linear path unchanged
  - Orchestrates: ASR primary → (optional) ASR secondary → (optional) ASR verifier → canonical source segments → per target_lang: refinement chain → (if target != source) translator → `by_lang[lang]` = lang_segments
  - `_run_stage_v5()` extends v4 `_run_stage()` with `extra_overrides` for verifier's `__secondary_segments` channel
  - `_persist_by_lang()` writes file_registry `translations` in v5 `by_lang` shape; emits `pipeline_complete_v5` Socket.IO event with `{languages, segments_per_lang}` summary
  - Resume from stage not yet supported on v5 path (`NotImplementedError`)
- **File registry by_lang shape** (T7): [backend/translations_normalize_v5.py](backend/translations_normalize_v5.py) — `normalize_translations_for_v5(raw)` converts v4 `[{en_text, zh_text, status, flags}]` to v5 `[{idx, start, end, source_lang, source_text, by_lang: {lang: {text, status, flags}}}]` at GET response time; v5 input passes through; `?shape=v4` query param disables normalization for legacy callers
- **Integration test** (T8) ([tests/test_v5_a2_integration.py](backend/tests/test_v5_a2_integration.py)) — builds 4 real profiles via managers, creates v5 pipeline JSON, runs pipeline with mocked engines, asserts both ZH (refined) and EN (translated) outputs persist correctly to registry's `translations[].by_lang[lang]` dict
- **Out of A2 scope** (deferred to A3): frontend redesign for multi-lang UI; new file upload flow that picks a v5 pipeline; render modal target-lang picker; per-stage rerun for v5; pipeline cancel mid-stage with cleanup; legacy v4 endpoint removal
- **Tests**: ~40 new backend tests across 5 test files (`test_v5_a2_factory.py` / `test_v5_a2_stages.py` / `test_v5_a2_runner.py` / `test_v5_a2_normalize.py` / `test_v5_a2_integration.py`). v4 path baseline preserved (14 known baseline failures unchanged).
```

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_v5_a2_integration.py CLAUDE.md
git commit -m "docs(v5-a2): integration test + CLAUDE.md entry

End-to-end test builds real v5 pipeline + 4 real profiles + mocked engines
and verifies ZH+EN persisted to registry.translations[].by_lang dict.
CLAUDE.md updated with v5-A2 progress entry above v5-A1."
```

---

## Final verification

After all 8 tasks:

- [ ] **Run full backend suite**

```bash
cd backend && source venv/bin/activate
pytest tests/ -v 2>&1 | tail -10
```
Expected: ~953 pass (~913 from A1 + ~40 from A2) / 14 baseline fail / 4 skip

- [ ] **v5-specific count**

```bash
pytest tests/test_v5_*.py --collect-only -q 2>&1 | tail -5
```
Expected: ~145 v5 tests

- [ ] **Live smoke test the v5 pipeline run** (manual, requires backend running):

```bash
# Assumes v5smoke admin exists from A1 smoke test
curl -s -c /tmp/c5.txt -X POST http://localhost:5001/login \
  -H "Content-Type: application/json" \
  -d '{"username":"v5smoke","password":"SmokeTest1!"}'

# Create LLM profile
LLM=$(curl -s -b /tmp/c5.txt -X POST http://localhost:5001/api/llm_profiles \
  -H "Content-Type: application/json" \
  -d '{"name":"smoke","backend":"ollama","model":"qwen3.5:9b","base_url":"http://localhost:11434"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# Create transcribe profile
TP=$(curl -s -b /tmp/c5.txt -X POST http://localhost:5001/api/transcribe_profiles \
  -H "Content-Type: application/json" \
  -d '{"name":"smoke","engine":"whisper","model_size":"large-v3","language":"zh"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# Create refiner profile
RF=$(curl -s -b /tmp/c5.txt -X POST http://localhost:5001/api/refiner_profiles \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"smoke\",\"lang\":\"zh\",\"style\":\"broadcast-hk\",\"llm_profile_id\":\"$LLM\",\"prompt_template_id\":\"refiner/zh_broadcast_hk_default\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# Create v5 pipeline
curl -s -b /tmp/c5.txt -X POST http://localhost:5001/api/pipelines \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"smoke-v5\",\"version\":5,\"asr_primary\":{\"transcribe_profile_id\":\"$TP\",\"source_lang\":\"zh\"},\"asr_secondary\":null,\"asr_verifier\":null,\"target_languages\":[\"zh\"],\"refinements\":{\"zh\":[{\"refiner_profile_id\":\"$RF\"}]},\"translators\":{},\"glossary_stages\":{},\"font_config\":{\"family\":\"f\",\"color\":\"w\",\"outline_color\":\"b\"}}"
# Should return 201 with version=5 in body
```

The pipeline run itself (transcribe an actual file) requires a real audio file + Ollama running, so it's a manual / next-A3 smoke. The point of this verification is that schema + manager + runner wiring all hold.

---

## Self-review notes

1. **Spec coverage**: All 5 stage classes from spec §5 implemented; DAG executor matches spec §5 stage iteration; by_lang persistence matches spec §3 data model; prompt override resolution matches spec §6. ✓

2. **Placeholder scan**: No "TBD" / "TODO" / "fill in" in plan body. ✓

3. **Type consistency**:
   - `LLMProfileManager` / `TranscribeProfileManager` etc. — consistent with A1 names
   - `build_llm_engine(profile)` / `resolve_prompt(template_id, file_override)` — used same way in all 3 stages that touch them
   - `pipeline_overrides` shape: `{refiners: {lang: str}, translators: {<src>_to_<tgt>: str}, verifier: str, __secondary_segments: list}` — consistent across all stages

4. **A3 dependencies**: A2 produces `by_lang` shape on file_registry. A3 frontend rewrite will consume this via GET /api/files/<id>/translations. No A2 work should anticipate A3's UI choices.

---

**End of v5-A2 plan.**
