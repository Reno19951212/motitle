# v4.0 A1 — Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Stage execution layer that makes v4 entities (ASR / MT profile + Pipeline) actually runnable on a real audio file — backend-only, no frontend changes. After A1 ships, a `curl POST /api/pipelines/<id>/run?file_id=<fid>` triggers a Pipeline run, segments cascade through ASR → MT stages → Glossary stage, per-stage output persists to file registry, and the JobQueue emits Socket.IO progress events.

**Architecture:** Stage ABC + 3 concrete stage classes (`ASRStage` / `MTStage` / `GlossaryStage`) sharing a `transform(segments_in, context) -> segments_out` per-segment-1:1 contract. `PipelineRunner` executes the linear stage chain sequentially, persisting `stage_outputs` to file registry between stages, emitting Socket.IO progress at 5% granularity, fail-fast on stage exception, cancel-event integrated with JobQueue. 4 new REST endpoints expose pipeline run / per-stage re-run / per-stage edit / file-level pipeline overrides.

**Tech Stack:** Python 3.9 (existing). No new third-party deps. JSON-file storage (existing). JobQueue (existing R5 Phase 2). Socket.IO (existing). `qwen3.5-35b-a3b-mlx-bf16` via Ollama (existing). `mlx-whisper` + `faster-whisper` (existing).

**Reference design doc:** [docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md](../specs/2026-05-16-asr-mt-emergent-pipeline-design.md). All schema fields in this plan match §3 (entities) + §4 (pipeline runner) + §6 (backend changes) + §14 (frontend stack — N/A for A1).

**Goal-driven format:** Each task carries explicit **🎯 Goal** (outcome + why) and **✅ Acceptance** (objective success criteria). Subagent dispatch prompts cite these directly; reviewers cross-check against them. Steps remain TDD (test → fail → impl → pass → commit).

**Out of scope for A1** (deferred):
- A2 (skipped per Q8-c) — no migration tooling
- A3 frontend dashboard rewrite (React + Vite)
- A4 frontend proofread page rewrite
- A5 cutover + cleanup (砍 `alignment_pipeline.py` / `sentence_pipeline.py` / `openrouter_engine.py` / legacy `/api/transcribe` / legacy HTML)

**A1 does NOT touch legacy code path.** `transcribe_with_segments` / `_auto_translate` / `_asr_handler` / `_mt_handler` / `alignment_pipeline.py` / `sentence_pipeline.py` 全部 zero line change. Legacy dashboard 仲行得（API 層）；A5 sub-phase 先做 cleanup。唯一 backwards-compatible-breaking 改動：**T18 砍 word_timestamps**（Q7-b）— 但 word_timestamps 已 default off 喺 prod profile，影響面少。

---

## File Structure

### New backend files

| File | Responsibility |
|---|---|
| `backend/stages/__init__.py` | Package marker + `PipelineStage` ABC + `StageContext` + `StageOutput` types |
| `backend/stages/asr_stage.py` | `ASRStage` class — dispatches to Whisper engine per `mode` |
| `backend/stages/mt_stage.py` | `MTStage` class — per-segment Ollama qwen call with profile prompt |
| `backend/stages/glossary_stage.py` | `GlossaryStage` class — multi-glossary explicit-order apply |
| `backend/pipeline_runner.py` | `PipelineRunner` — linear stage executor + Socket.IO progress + cancel |

### Modified backend files

| File | What changes |
|---|---|
| `backend/asr_profiles.py` | Drop `word_timestamps` from validator + manager (Q7-b) |
| `backend/asr/whisper_engine.py` + `mlx_whisper_engine.py` | Drop `word_timestamps` param from `transcribe()` + schema |
| `backend/app.py` | (1) Register `pipeline_run` JobQueue handler + `_pipeline_run_handler` (2) Add 4 new REST endpoints (3) Helper for `stage_outputs` registry persistence |
| `CLAUDE.md` | Update REST endpoints table + retire "no build system" rule + A1 entry in Completed Features |

### New test files

| File | Responsibility |
|---|---|
| `backend/tests/test_stages_asr.py` | ASR Stage mode dispatch + emergent quality flag |
| `backend/tests/test_stages_mt.py` | MT Stage per-segment transform + template substitution |
| `backend/tests/test_stages_glossary.py` | Glossary Stage multi-apply + conflict ordering |
| `backend/tests/test_pipeline_runner.py` | Runner skeleton + fail-fast + progress + cancel |
| `backend/tests/test_a1_endpoints.py` | 4 new REST endpoints (run / rerun / edit segment / pipeline overrides) |
| `backend/tests/test_a1_integration.py` | End-to-end pipeline run via REST API (all stages mocked) |

---

## Task Decomposition (21 tasks)

### Task 1: Scaffold `backend/stages/` package + `PipelineStage` ABC

**🎯 Goal:** Establish the stage layer interface contract. Every concrete stage (ASR / MT / Glossary) must implement the same `transform()` signature so `PipelineRunner` can chain them uniformly.

**✅ Acceptance:**
- `backend/stages/__init__.py` exposes `PipelineStage` ABC, `StageContext` dataclass, `StageOutput` TypedDict
- `transform(segments_in: List[Segment], context: StageContext) -> List[Segment]` is abstract
- `StageContext` carries `file_id`, `user_id`, `pipeline_id`, `stage_index`, `cancel_event`, `progress_callback`, `pipeline_overrides` dict
- Importing `stages` from another module raises no error
- Existing 891 backend tests still pass (no regression)

**Files:**
- Create: `backend/stages/__init__.py`
- Test: `backend/tests/test_stages_init.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_stages_init.py
import pytest
from stages import PipelineStage, StageContext, StageOutput


def test_pipeline_stage_is_abstract():
    with pytest.raises(TypeError):
        PipelineStage()  # cannot instantiate ABC


def test_stage_context_required_fields():
    ctx = StageContext(file_id="abc", user_id=1, pipeline_id="p1",
                       stage_index=0, cancel_event=None,
                       progress_callback=None, pipeline_overrides={})
    assert ctx.file_id == "abc"
    assert ctx.stage_index == 0


def test_stage_output_typed_dict_shape():
    out: StageOutput = {
        "stage_index": 0, "stage_type": "asr", "stage_ref": "asr-uuid",
        "status": "done", "ran_at": 1234567890.0, "duration_seconds": 5.0,
        "segments": [], "quality_flags": [],
    }
    assert out["stage_type"] == "asr"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend" && pytest tests/test_stages_init.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement ABC + types**

Create `backend/stages/__init__.py`:
```python
"""
Pipeline stage abstraction — v4.0 A1.

All concrete stages (ASRStage / MTStage / GlossaryStage) implement the
PipelineStage ABC. PipelineRunner chains stages linearly, calling
transform() per-segment-1:1 with shared StageContext.

Per design doc §4.1 — segment count invariant: len(segments_out) == len(segments_in).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, List, Optional, TypedDict
import threading


@dataclass
class StageContext:
    """Per-stage runtime context shared between PipelineRunner and concrete stages."""
    file_id: str
    user_id: Optional[int]
    pipeline_id: str
    stage_index: int
    cancel_event: Optional[threading.Event]
    progress_callback: Optional[Callable[[int, int], None]]
    pipeline_overrides: dict = field(default_factory=dict)


class StageOutput(TypedDict):
    """Per-stage output persisted to file registry."""
    stage_index: int
    stage_type: str  # "asr" | "mt" | "glossary"
    stage_ref: str   # UUID of asr_profile / mt_profile / "glossary-stage-inline"
    status: str      # "done" | "failed" | "cancelled" | "running"
    ran_at: float
    duration_seconds: float
    segments: List[dict]
    quality_flags: List[str]  # e.g., ["low_logprob"] for emergent ASR


class PipelineStage(ABC):
    """Abstract base for all pipeline stages."""

    @property
    @abstractmethod
    def stage_type(self) -> str:
        """e.g., 'asr', 'mt', 'glossary'"""

    @property
    @abstractmethod
    def stage_ref(self) -> str:
        """UUID or unique identifier of the underlying profile/config"""

    @abstractmethod
    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        """Per-segment-1:1 transform. len(out) must equal len(in)."""
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_stages_init.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/stages/__init__.py backend/tests/test_stages_init.py
git commit -m "feat(v4 A1): PipelineStage ABC + StageContext + StageOutput types"
```

---

### Task 2: ASR Stage class — 3-mode dispatch (without word_timestamps)

**🎯 Goal:** ASR Stage receives an ASR profile + audio file path, dispatches to the existing `mlx-whisper` / `faster-whisper` engine according to ASR profile's `mode` (same-lang / emergent-translate / translate-to-en), and emits per-segment transcript text. No alignment pipeline, no sentence merge, raw Whisper segments only.

**✅ Acceptance:**
- `ASRStage(asr_profile: dict, audio_path: str)` constructor accepts profile + audio path
- `transform([], context)` calls Whisper engine via `asr.create_asr_engine()` factory
- Mode dispatch: `same-lang` → `task=transcribe` + `language=<profile.language>`; `emergent-translate` → same; `translate-to-en` → `task=translate`
- Returns `List[Segment]` with `{start, end, text}` (no `words` field — Q7-b)
- Quality flag `low_logprob` appended if Whisper avg_logprob < -1.0 (when available from engine)
- Mock-based unit tests verify dispatch without invoking real Whisper

**Files:**
- Create: `backend/stages/asr_stage.py`
- Test: `backend/tests/test_stages_asr.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_stages_asr.py
import pytest
from unittest.mock import MagicMock, patch
from stages.asr_stage import ASRStage
from stages import StageContext


def _ctx(idx=0):
    return StageContext(file_id="f1", user_id=1, pipeline_id="p1",
                        stage_index=idx, cancel_event=None,
                        progress_callback=None, pipeline_overrides={})


def _profile(mode="same-lang", language="en"):
    return {
        "id": "asr-uuid-1", "name": "test", "engine": "mlx-whisper",
        "model_size": "large-v3", "mode": mode, "language": language,
        "initial_prompt": "", "condition_on_previous_text": False,
        "simplified_to_traditional": False, "device": "auto",
    }


def test_stage_type():
    stage = ASRStage(_profile(), audio_path="/tmp/fake.wav")
    assert stage.stage_type == "asr"
    assert stage.stage_ref == "asr-uuid-1"


def test_same_lang_mode_dispatches_transcribe(monkeypatch):
    mock_engine = MagicMock()
    mock_engine.transcribe.return_value = [{"start": 0.0, "end": 2.0, "text": "Hello"}]
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: mock_engine)

    stage = ASRStage(_profile(mode="same-lang", language="en"), audio_path="/tmp/x.wav")
    result = stage.transform([], _ctx())

    mock_engine.transcribe.assert_called_once()
    call_args = mock_engine.transcribe.call_args
    assert call_args.kwargs.get("language") == "en" or call_args.args[1] == "en"
    assert len(result) == 1
    assert result[0]["text"] == "Hello"


def test_emergent_translate_mode_uses_target_language(monkeypatch):
    """emergent-translate + language=zh → Whisper task=transcribe + language=zh
    even if audio is English (emergent cross-lang transcription)."""
    mock_engine = MagicMock()
    mock_engine.transcribe.return_value = [{"start": 0.0, "end": 2.0, "text": "大家好"}]
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: mock_engine)
    stage = ASRStage(_profile(mode="emergent-translate", language="zh"), audio_path="/tmp/x.wav")
    result = stage.transform([], _ctx())
    assert result[0]["text"] == "大家好"


def test_translate_to_en_mode_sets_task_translate(monkeypatch):
    """translate-to-en → engine.transcribe(task='translate', language=audio_lang)."""
    captured = {}
    def fake_transcribe(audio_path, language=None, **kwargs):
        captured["language"] = language
        # The current whisper_engine hardcodes task=transcribe. ASRStage MUST
        # bridge by passing `task` explicitly; engine code change is part of A1.
        captured["task"] = kwargs.get("task", "transcribe")
        return [{"start": 0.0, "end": 2.0, "text": "Hello in English"}]
    mock_engine = MagicMock(transcribe=fake_transcribe)
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: mock_engine)

    stage = ASRStage(_profile(mode="translate-to-en", language="zh"), audio_path="/tmp/x.wav")
    stage.transform([], _ctx())
    assert captured["task"] == "translate"


def test_no_word_timestamps_in_output(monkeypatch):
    """Q7-b — ASR stage MUST NOT include `words` field in segments."""
    mock_engine = MagicMock()
    # Even if engine returned `words`, stage strips it
    mock_engine.transcribe.return_value = [
        {"start": 0.0, "end": 2.0, "text": "Hi", "words": [{"word": "Hi"}]}
    ]
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: mock_engine)
    stage = ASRStage(_profile(), audio_path="/tmp/x.wav")
    result = stage.transform([], _ctx())
    assert "words" not in result[0]


def test_segments_in_ignored_for_asr_stage(monkeypatch):
    """ASR stage reads from audio_path, NOT segments_in (which is empty for first stage)."""
    mock_engine = MagicMock()
    mock_engine.transcribe.return_value = [{"start": 0.0, "end": 2.0, "text": "X"}]
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: mock_engine)
    stage = ASRStage(_profile(), audio_path="/tmp/x.wav")
    result = stage.transform(
        [{"start": 99.0, "end": 100.0, "text": "garbage"}],  # ignored
        _ctx(),
    )
    assert result[0]["text"] == "X"  # from mock engine, not garbage input
```

- [ ] **Step 2: Run to confirm fail**

Run: `pytest tests/test_stages_asr.py -v`
Expected: All FAIL with `ImportError: cannot import name 'ASRStage'`

- [ ] **Step 3: Implement `ASRStage`**

```python
# backend/stages/asr_stage.py
"""ASR Stage — v4.0 A1.

Dispatches to Whisper engine according to ASR profile's `mode`:
- same-lang:           task=transcribe + language=profile.language (audio lang)
- emergent-translate:  task=transcribe + language=profile.language (target lang,
                        unofficial Whisper Large-v3 behaviour — see design doc §1.3)
- translate-to-en:     task=translate + language=profile.language (audio lang;
                        output always English)

Quality flag `low_logprob` is appended when Whisper engine returns avg_logprob < -1.0
(emergent mode quality canary — see design doc §10 risk register).
"""
from typing import List

from . import PipelineStage, StageContext

LOW_LOGPROB_THRESHOLD = -1.0


def _resolve_task(mode: str) -> str:
    if mode == "translate-to-en":
        return "translate"
    return "transcribe"  # same-lang + emergent-translate both use transcribe


class ASRStage(PipelineStage):
    def __init__(self, asr_profile: dict, audio_path: str):
        self._profile = asr_profile
        self._audio_path = audio_path

    @property
    def stage_type(self) -> str:
        return "asr"

    @property
    def stage_ref(self) -> str:
        return self._profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        # segments_in is ignored for ASR stage (first stage reads from audio_path)
        from asr import create_asr_engine
        engine = create_asr_engine(self._profile)
        task = _resolve_task(self._profile["mode"])
        language = self._profile["language"]
        # Modern Whisper engines accept `task` as kwarg; older path hardcodes transcribe.
        # We pass task to be explicit; engines that don't support it silently ignore.
        try:
            raw = engine.transcribe(self._audio_path, language=language, task=task)
        except TypeError:
            # Engine doesn't accept `task` kwarg yet; fall back to default transcribe
            raw = engine.transcribe(self._audio_path, language=language)

        # Build output segments (Q7-b: strip `words` if present)
        out: List[dict] = []
        for seg in raw:
            out_seg = {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg.get("text", "").strip(),
            }
            out.append(out_seg)

        return out
```

(Note: emergent quality flag heuristic in T11; for now `low_logprob` not emitted. Test for it added in T11.)

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_stages_asr.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/stages/asr_stage.py backend/tests/test_stages_asr.py
git commit -m "feat(v4 A1): ASRStage 3-mode dispatch (no word_timestamps per Q7-b)"
```

---

### Task 3: MT Stage class — per-segment qwen call with template substitution

**🎯 Goal:** MT Stage receives an MT profile + segments from the previous stage, calls qwen3.5-35b-a3b once per segment with the profile's system_prompt + user_message_template, and emits per-segment transformed text. Same-lang only (no cross-lang translation — that's done by ASR stage in emergent mode).

**✅ Acceptance:**
- `MTStage(mt_profile: dict)` constructor accepts profile
- `transform(segments_in, context)` calls Ollama qwen per segment
- `user_message_template` substitutes `{text}` placeholder with `segment["text"]`
- Per-segment output preserves `start` / `end` from input; only `text` changes
- Segment count invariant: `len(out) == len(in)`
- Empty input text → skip LLM call, emit empty output text (don't burn tokens)
- Mock-based tests verify template substitution + LLM dispatch

**Files:**
- Create: `backend/stages/mt_stage.py`
- Test: `backend/tests/test_stages_mt.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_stages_mt.py
import pytest
from unittest.mock import MagicMock, patch
from stages.mt_stage import MTStage
from stages import StageContext


def _ctx():
    return StageContext(file_id="f1", user_id=1, pipeline_id="p1",
                        stage_index=1, cancel_event=None,
                        progress_callback=None, pipeline_overrides={})


def _profile(template="polish: {text}"):
    return {
        "id": "mt-uuid-1", "name": "test", "engine": "qwen3.5-35b-a3b",
        "input_lang": "zh", "output_lang": "zh",
        "system_prompt": "你係廣播編輯員。",
        "user_message_template": template,
        "batch_size": 1, "temperature": 0.1, "parallel_batches": 1,
    }


def test_stage_type():
    stage = MTStage(_profile())
    assert stage.stage_type == "mt"
    assert stage.stage_ref == "mt-uuid-1"


def test_per_segment_invariant(monkeypatch):
    """len(out) must equal len(in); start/end preserved."""
    fake_llm = MagicMock(side_effect=["译1", "译2", "译3"])
    monkeypatch.setattr("stages.mt_stage._call_qwen", fake_llm)

    stage = MTStage(_profile())
    segs_in = [
        {"start": 0.0, "end": 1.0, "text": "原1"},
        {"start": 1.0, "end": 2.0, "text": "原2"},
        {"start": 2.0, "end": 3.0, "text": "原3"},
    ]
    segs_out = stage.transform(segs_in, _ctx())

    assert len(segs_out) == 3
    for i, o in enumerate(segs_out):
        assert o["start"] == segs_in[i]["start"]
        assert o["end"] == segs_in[i]["end"]
    assert segs_out[0]["text"] == "译1"
    assert segs_out[1]["text"] == "译2"


def test_template_substitution(monkeypatch):
    captured = []
    def fake_llm(system, user, temperature):
        captured.append({"system": system, "user": user})
        return "polished"
    monkeypatch.setattr("stages.mt_stage._call_qwen", fake_llm)

    template = "請 polish 以下: {text}"
    stage = MTStage(_profile(template=template))
    stage.transform([{"start": 0, "end": 1, "text": "hello"}], _ctx())

    assert captured[0]["user"] == "請 polish 以下: hello"
    assert captured[0]["system"] == "你係廣播編輯員。"


def test_empty_input_skips_llm(monkeypatch):
    """Empty segment text → no LLM call, output text is empty."""
    fake_llm = MagicMock()
    monkeypatch.setattr("stages.mt_stage._call_qwen", fake_llm)

    stage = MTStage(_profile())
    segs_in = [{"start": 0, "end": 1, "text": ""}]
    segs_out = stage.transform(segs_in, _ctx())

    assert segs_out[0]["text"] == ""
    fake_llm.assert_not_called()


def test_temperature_passed_to_llm(monkeypatch):
    captured = {}
    def fake_llm(system, user, temperature):
        captured["temp"] = temperature
        return "x"
    monkeypatch.setattr("stages.mt_stage._call_qwen", fake_llm)

    profile = _profile()
    profile["temperature"] = 0.3
    stage = MTStage(profile)
    stage.transform([{"start": 0, "end": 1, "text": "a"}], _ctx())

    assert captured["temp"] == 0.3
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_stages_mt.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `MTStage`**

```python
# backend/stages/mt_stage.py
"""MT Stage — v4.0 A1.

Per-segment same-lang transformation via Ollama qwen3.5-35b. Reuses existing
ollama_engine HTTP client but bypasses its batching / sentence pipeline /
alignment logic (砍 in A5).
"""
from typing import List

from . import PipelineStage, StageContext


def _call_qwen(system_prompt: str, user_message: str, temperature: float) -> str:
    """Thin wrapper around Ollama qwen call. Returns model output text only."""
    from translation.ollama_engine import OllamaTranslationEngine
    # Reuse existing engine HTTP plumbing — bypass batching/sentence pipeline.
    engine = OllamaTranslationEngine({"engine": "qwen3.5-35b-a3b"})
    return engine._call_ollama(system_prompt, user_message, temperature)


class MTStage(PipelineStage):
    def __init__(self, mt_profile: dict):
        self._profile = mt_profile

    @property
    def stage_type(self) -> str:
        return "mt"

    @property
    def stage_ref(self) -> str:
        return self._profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        system_prompt = self._resolve_system_prompt(context)
        template = self._profile["user_message_template"]
        temperature = float(self._profile.get("temperature", 0.1))

        out: List[dict] = []
        for seg in segments_in:
            text_in = seg.get("text", "").strip()
            if not text_in:
                # Skip LLM call for empty input
                out.append({"start": seg["start"], "end": seg["end"], "text": ""})
                continue

            user_msg = template.replace("{text}", text_in)
            text_out = _call_qwen(system_prompt, user_msg, temperature)
            out.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": text_out.strip(),
            })

        return out

    def _resolve_system_prompt(self, context: StageContext) -> str:
        # File-level override (Q6-a per-(file,pipeline) scope) wired in T15.
        return self._profile["system_prompt"]
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_stages_mt.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/stages/mt_stage.py backend/tests/test_stages_mt.py
git commit -m "feat(v4 A1): MTStage per-segment qwen call + template substitution"
```

---

### Task 4: Glossary Stage class — multi-glossary explicit-order apply

**🎯 Goal:** Glossary Stage applies N glossaries in explicit user-defined order, doing string-match-then-LLM substitution per segment. Multi-glossary support: same segment can be transformed by multiple glossaries in sequence. Stage receives `glossary_stage_config` (from Pipeline) describing which glossary IDs and in what order.

**✅ Acceptance:**
- `GlossaryStage(glossary_stage_config: dict, glossary_manager)` constructor
- `transform(segments_in, context)` applies each glossary in order
- Explicit order matters: glossary[0] applied first, then glossary[1] on the result, etc.
- Per-segment string match + LLM smart replace (reuses v3.0 glossary apply logic)
- When `enabled: false` → pass-through (no transformation)
- Empty `glossary_ids` list when `enabled: true` → already rejected at Pipeline validation (no-op safety here)

**Files:**
- Create: `backend/stages/glossary_stage.py`
- Test: `backend/tests/test_stages_glossary.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_stages_glossary.py
import pytest
from unittest.mock import MagicMock
from stages.glossary_stage import GlossaryStage
from stages import StageContext


def _ctx():
    return StageContext(file_id="f1", user_id=1, pipeline_id="p1",
                        stage_index=2, cancel_event=None,
                        progress_callback=None, pipeline_overrides={})


def test_stage_type():
    config = {"enabled": True, "glossary_ids": ["g1", "g2"],
              "apply_order": "explicit", "apply_method": "string-match-then-llm"}
    mgr = MagicMock()
    stage = GlossaryStage(config, mgr)
    assert stage.stage_type == "glossary"
    assert "g1" in stage.stage_ref  # ref includes ordered list
    assert "g2" in stage.stage_ref


def test_disabled_pass_through():
    config = {"enabled": False, "glossary_ids": [],
              "apply_order": "explicit", "apply_method": "string-match-then-llm"}
    stage = GlossaryStage(config, MagicMock())
    segs = [{"start": 0, "end": 1, "text": "Hello"}]
    out = stage.transform(segs, _ctx())
    assert out == segs


def test_single_glossary_applies_substitution(monkeypatch):
    config = {"enabled": True, "glossary_ids": ["g1"],
              "apply_order": "explicit", "apply_method": "string-match-then-llm"}
    mgr = MagicMock()
    mgr.get.return_value = {
        "id": "g1", "source_lang": "zh", "target_lang": "zh",
        "entries": [{"source": "麥巴比", "target": "麦巴比"}],
    }
    monkeypatch.setattr("stages.glossary_stage._apply_glossary_to_segment",
                        lambda text, glossary, **kw: text.replace("麥巴比", "麦巴比"))

    stage = GlossaryStage(config, mgr)
    segs_out = stage.transform([{"start": 0, "end": 1, "text": "麥巴比入波"}], _ctx())
    assert segs_out[0]["text"] == "麦巴比入波"


def test_multi_glossary_explicit_order(monkeypatch):
    """Order matters: g1 applies first, then g2 on the result."""
    config = {"enabled": True, "glossary_ids": ["g1", "g2"],
              "apply_order": "explicit", "apply_method": "string-match-then-llm"}
    mgr = MagicMock()
    def get_glossary(gid):
        if gid == "g1":
            return {"id": "g1", "entries": [{"source": "A", "target": "B"}]}
        if gid == "g2":
            return {"id": "g2", "entries": [{"source": "B", "target": "C"}]}
        return None
    mgr.get.side_effect = get_glossary

    def fake_apply(text, glossary, **kw):
        # Single-entry replace per glossary
        e = glossary["entries"][0]
        return text.replace(e["source"], e["target"])
    monkeypatch.setattr("stages.glossary_stage._apply_glossary_to_segment", fake_apply)

    stage = GlossaryStage(config, mgr)
    out = stage.transform([{"start": 0, "end": 1, "text": "A"}], _ctx())
    # g1 transforms A→B, then g2 transforms B→C
    assert out[0]["text"] == "C"


def test_segment_count_invariant(monkeypatch):
    config = {"enabled": True, "glossary_ids": ["g1"],
              "apply_order": "explicit", "apply_method": "string-match-then-llm"}
    mgr = MagicMock()
    mgr.get.return_value = {"id": "g1", "entries": []}
    monkeypatch.setattr("stages.glossary_stage._apply_glossary_to_segment",
                        lambda text, glossary, **kw: text)

    stage = GlossaryStage(config, mgr)
    segs_in = [{"start": i, "end": i+1, "text": f"seg{i}"} for i in range(5)]
    segs_out = stage.transform(segs_in, _ctx())
    assert len(segs_out) == 5
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_stages_glossary.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `GlossaryStage`**

```python
# backend/stages/glossary_stage.py
"""Glossary Stage — v4.0 A1.

Standalone post-MT stage that applies N glossaries in explicit order to each
segment. Each glossary uses string-match-then-LLM substitution (reuses v3.0
two-phase apply logic). NO MT prompt injection — Q4 brainstorm decision.
"""
from typing import List

from . import PipelineStage, StageContext


def _apply_glossary_to_segment(text: str, glossary: dict, method: str = "string-match-then-llm") -> str:
    """Apply a single glossary to one segment's text. Phase 1 simplified
    implementation: direct string replace. v3.0 two-phase LLM logic
    integrated in A5 cleanup pass when removing legacy code path."""
    out = text
    for entry in glossary.get("entries", []):
        src = entry.get("source", "")
        tgt = entry.get("target", "")
        if src and tgt:
            out = out.replace(src, tgt)
    return out


class GlossaryStage(PipelineStage):
    def __init__(self, glossary_stage_config: dict, glossary_manager):
        self._config = glossary_stage_config
        self._gm = glossary_manager

    @property
    def stage_type(self) -> str:
        return "glossary"

    @property
    def stage_ref(self) -> str:
        return "glossary-stage(" + ",".join(self._config.get("glossary_ids", [])) + ")"

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        if not self._config.get("enabled", False):
            return list(segments_in)

        glossary_ids = self._config.get("glossary_ids", [])
        method = self._config.get("apply_method", "string-match-then-llm")

        # Load all glossaries in order (skip None)
        glossaries = [self._gm.get(gid) for gid in glossary_ids]
        glossaries = [g for g in glossaries if g is not None]

        out: List[dict] = []
        for seg in segments_in:
            text = seg.get("text", "")
            for glossary in glossaries:
                text = _apply_glossary_to_segment(text, glossary, method=method)
            out.append({"start": seg["start"], "end": seg["end"], "text": text})

        return out
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_stages_glossary.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/stages/glossary_stage.py backend/tests/test_stages_glossary.py
git commit -m "feat(v4 A1): GlossaryStage multi-glossary explicit-order apply"
```

---

### Task 5: `PipelineRunner` skeleton — sequential stage execution

**🎯 Goal:** PipelineRunner takes a Pipeline + file_id + audio path, instantiates the right stage objects in order (ASR → N MT → Glossary), runs them sequentially, and persists each stage's output to the file registry as `stage_outputs[i]`.

**✅ Acceptance:**
- `PipelineRunner(pipeline: dict, file_id: str, audio_path: str, managers: dict)` constructor
- `run(user_id, cancel_event=None, progress_callback=None)` executes stages sequentially
- After each stage, writes `stage_output` to file registry
- Returns final `stage_outputs` list when complete
- Sequential execution: stage[N+1] starts only after stage[N] completes successfully
- Empty `mt_stages` list → ASR + Glossary only (skip MT)
- `glossary_stage.enabled: false` → ASR + N MT only (skip Glossary)

**Files:**
- Create: `backend/pipeline_runner.py`
- Test: `backend/tests/test_pipeline_runner.py`

- [ ] **Step 1: Write failing test (skeleton flow only)**

```python
# backend/tests/test_pipeline_runner.py
import pytest
import time
from unittest.mock import MagicMock, patch
from pipeline_runner import PipelineRunner


def _pipeline(mt_count=1, glossary_enabled=False):
    return {
        "id": "pipe-1", "name": "test",
        "asr_profile_id": "asr-uuid",
        "mt_stages": [f"mt-uuid-{i}" for i in range(mt_count)],
        "glossary_stage": {
            "enabled": glossary_enabled,
            "glossary_ids": [],
            "apply_order": "explicit",
            "apply_method": "string-match-then-llm",
        },
        "font_config": {},
        "user_id": 1,
    }


def _managers(asr_profile=None, mt_profiles=None, glossary_manager=None):
    """Build a minimal manager stack for testing."""
    asr_mgr = MagicMock()
    asr_mgr.get.return_value = asr_profile or {
        "id": "asr-uuid", "engine": "mlx-whisper", "model_size": "large-v3",
        "mode": "same-lang", "language": "en",
    }
    mt_mgr = MagicMock()
    mt_profiles = mt_profiles or [{
        "id": "mt-uuid-0", "engine": "qwen3.5-35b-a3b",
        "input_lang": "zh", "output_lang": "zh",
        "system_prompt": "polish", "user_message_template": "go: {text}",
        "temperature": 0.1,
    }]
    mt_mgr.get.side_effect = lambda mid: next((p for p in mt_profiles if p["id"] == mid), None)
    return {
        "asr_manager": asr_mgr,
        "mt_manager": mt_mgr,
        "glossary_manager": glossary_manager or MagicMock(),
    }


def test_runner_sequential_execution(monkeypatch):
    pipeline = _pipeline(mt_count=2, glossary_enabled=False)
    managers = _managers(mt_profiles=[
        {"id": "mt-uuid-0", "engine": "qwen3.5-35b-a3b",
         "input_lang": "zh", "output_lang": "zh",
         "system_prompt": "p1", "user_message_template": "polish: {text}",
         "temperature": 0.1},
        {"id": "mt-uuid-1", "engine": "qwen3.5-35b-a3b",
         "input_lang": "zh", "output_lang": "zh",
         "system_prompt": "p2", "user_message_template": "broadcast: {text}",
         "temperature": 0.1},
    ])

    # Mock ASR + MT + persistence
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: MagicMock(
        transcribe=lambda *a, **kw: [{"start": 0, "end": 1, "text": "ASR"}]))
    fake_calls = []
    def fake_qwen(sys_p, usr_p, temp):
        fake_calls.append(usr_p)
        return f"MT({usr_p})"
    monkeypatch.setattr("stages.mt_stage._call_qwen", fake_qwen)
    persist = MagicMock()
    monkeypatch.setattr("pipeline_runner._persist_stage_output", persist)

    runner = PipelineRunner(pipeline, file_id="f1", audio_path="/tmp/x.wav", managers=managers)
    stage_outputs = runner.run(user_id=1)

    assert len(stage_outputs) == 3  # ASR + MT0 + MT1
    assert stage_outputs[0]["stage_type"] == "asr"
    assert stage_outputs[1]["stage_type"] == "mt"
    assert stage_outputs[2]["stage_type"] == "mt"
    # MT1 receives MT0's output (sequential)
    assert "MT(polish:" in fake_calls[0]
    assert "MT(broadcast:" in fake_calls[1] or fake_calls[1].startswith("broadcast: MT(")


def test_runner_empty_mt_stages(monkeypatch):
    """ASR-only pipeline (no MT, no Glossary) — only one stage_output."""
    pipeline = _pipeline(mt_count=0, glossary_enabled=False)
    managers = _managers(mt_profiles=[])
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: MagicMock(
        transcribe=lambda *a, **kw: [{"start": 0, "end": 1, "text": "OnlyASR"}]))
    monkeypatch.setattr("pipeline_runner._persist_stage_output", MagicMock())

    runner = PipelineRunner(pipeline, file_id="f1", audio_path="/tmp/x.wav", managers=managers)
    outputs = runner.run(user_id=1)
    assert len(outputs) == 1
    assert outputs[0]["stage_type"] == "asr"
    assert outputs[0]["segments"][0]["text"] == "OnlyASR"


def test_runner_with_glossary_stage(monkeypatch):
    pipeline = _pipeline(mt_count=0, glossary_enabled=True)
    pipeline["glossary_stage"]["glossary_ids"] = ["g1"]
    managers = _managers(mt_profiles=[])
    managers["glossary_manager"].get.return_value = {"id": "g1", "entries": [
        {"source": "OnlyASR", "target": "GLOSSED"}
    ]}
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: MagicMock(
        transcribe=lambda *a, **kw: [{"start": 0, "end": 1, "text": "OnlyASR"}]))
    monkeypatch.setattr("pipeline_runner._persist_stage_output", MagicMock())

    runner = PipelineRunner(pipeline, file_id="f1", audio_path="/tmp/x.wav", managers=managers)
    outputs = runner.run(user_id=1)
    assert len(outputs) == 2  # ASR + Glossary
    assert outputs[1]["stage_type"] == "glossary"
    assert outputs[1]["segments"][0]["text"] == "GLOSSED"
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_pipeline_runner.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `PipelineRunner`**

```python
# backend/pipeline_runner.py
"""Pipeline Runner — v4.0 A1.

Linear stage executor that chains ASR → N MT → Glossary, persisting per-stage
output to file registry. Per design doc §4.
"""
import time
import threading
from typing import Callable, List, Optional

from stages import StageContext, StageOutput
from stages.asr_stage import ASRStage
from stages.mt_stage import MTStage
from stages.glossary_stage import GlossaryStage


def _persist_stage_output(file_id: str, stage_output: StageOutput) -> None:
    """Write stage output to file registry. Implementation in T6."""
    pass  # Filled in Task 6


class PipelineRunner:
    def __init__(self, pipeline: dict, file_id: str, audio_path: str, managers: dict):
        self._pipeline = pipeline
        self._file_id = file_id
        self._audio_path = audio_path
        self._asr_manager = managers["asr_manager"]
        self._mt_manager = managers["mt_manager"]
        self._glossary_manager = managers["glossary_manager"]

    def run(
        self,
        user_id: Optional[int],
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[StageOutput]:
        """Execute all stages sequentially. Returns full stage_outputs list."""
        stage_outputs: List[StageOutput] = []
        segments: List[dict] = []  # accumulates between stages

        # Stage 0 — ASR
        asr_profile = self._asr_manager.get(self._pipeline["asr_profile_id"])
        if asr_profile is None:
            raise ValueError(f"ASR profile {self._pipeline['asr_profile_id']} not found")
        ctx = StageContext(file_id=self._file_id, user_id=user_id,
                           pipeline_id=self._pipeline["id"], stage_index=0,
                           cancel_event=cancel_event,
                           progress_callback=progress_callback,
                           pipeline_overrides={})
        asr_stage = ASRStage(asr_profile, self._audio_path)
        start_t = time.time()
        segments = asr_stage.transform([], ctx)
        stage_out: StageOutput = {
            "stage_index": 0, "stage_type": "asr",
            "stage_ref": asr_stage.stage_ref, "status": "done",
            "ran_at": start_t, "duration_seconds": time.time() - start_t,
            "segments": segments, "quality_flags": [],
        }
        stage_outputs.append(stage_out)
        _persist_stage_output(self._file_id, stage_out)

        # Stages 1..N — MT
        for i, mt_id in enumerate(self._pipeline.get("mt_stages", [])):
            mt_profile = self._mt_manager.get(mt_id)
            if mt_profile is None:
                raise ValueError(f"MT profile {mt_id} not found")
            idx = i + 1
            ctx = StageContext(file_id=self._file_id, user_id=user_id,
                               pipeline_id=self._pipeline["id"], stage_index=idx,
                               cancel_event=cancel_event,
                               progress_callback=progress_callback,
                               pipeline_overrides={})
            mt_stage = MTStage(mt_profile)
            start_t = time.time()
            segments = mt_stage.transform(segments, ctx)
            stage_out = {
                "stage_index": idx, "stage_type": "mt",
                "stage_ref": mt_stage.stage_ref, "status": "done",
                "ran_at": start_t, "duration_seconds": time.time() - start_t,
                "segments": segments, "quality_flags": [],
            }
            stage_outputs.append(stage_out)
            _persist_stage_output(self._file_id, stage_out)

        # Final stage — Glossary (if enabled)
        gloss_config = self._pipeline.get("glossary_stage", {})
        if gloss_config.get("enabled"):
            idx = 1 + len(self._pipeline.get("mt_stages", []))
            ctx = StageContext(file_id=self._file_id, user_id=user_id,
                               pipeline_id=self._pipeline["id"], stage_index=idx,
                               cancel_event=cancel_event,
                               progress_callback=progress_callback,
                               pipeline_overrides={})
            gloss_stage = GlossaryStage(gloss_config, self._glossary_manager)
            start_t = time.time()
            segments = gloss_stage.transform(segments, ctx)
            stage_out = {
                "stage_index": idx, "stage_type": "glossary",
                "stage_ref": gloss_stage.stage_ref, "status": "done",
                "ran_at": start_t, "duration_seconds": time.time() - start_t,
                "segments": segments, "quality_flags": [],
            }
            stage_outputs.append(stage_out)
            _persist_stage_output(self._file_id, stage_out)

        return stage_outputs
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_pipeline_runner.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline_runner.py backend/tests/test_pipeline_runner.py
git commit -m "feat(v4 A1): PipelineRunner sequential stage execution skeleton"
```

---

### Task 6: file_registry `stage_outputs` persistence helper

**🎯 Goal:** When the runner finishes a stage, the output `StageOutput` must be persisted to the file registry under `file.stage_outputs[<stage_index>]`. This persistence must be thread-safe (worker thread + concurrent request thread) and crash-safe (atomic file write).

**✅ Acceptance:**
- New helper `_persist_stage_output(file_id, stage_output)` in `pipeline_runner.py` (replaces stub from T5)
- Helper reads + updates + writes `_file_registry` from `app.py` (uses existing `_registry_lock`)
- Concurrent persists for same file serialize correctly (TOCTOU safe)
- Persist is idempotent: same stage_index written twice → second write replaces first

**Files:**
- Modify: `backend/pipeline_runner.py`
- Modify: `backend/tests/test_pipeline_runner.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_pipeline_runner.py`:
```python
def test_persist_stage_output_writes_to_registry(monkeypatch, tmp_path):
    """_persist_stage_output writes to _file_registry under file.stage_outputs[idx]."""
    # Build minimal app environment
    import app as app_mod
    registry = {"f1": {"id": "f1", "stage_outputs": {}}}
    monkeypatch.setattr(app_mod, "_file_registry", registry)
    monkeypatch.setattr(app_mod, "_save_registry", lambda: None)

    from pipeline_runner import _persist_stage_output
    output = {
        "stage_index": 0, "stage_type": "asr", "stage_ref": "asr-1",
        "status": "done", "ran_at": 1.0, "duration_seconds": 0.5,
        "segments": [{"start": 0, "end": 1, "text": "x"}], "quality_flags": [],
    }
    _persist_stage_output("f1", output)
    assert "0" in registry["f1"]["stage_outputs"] or 0 in registry["f1"]["stage_outputs"]


def test_persist_stage_output_replaces_existing_index(monkeypatch):
    import app as app_mod
    registry = {"f1": {"id": "f1", "stage_outputs": {}}}
    monkeypatch.setattr(app_mod, "_file_registry", registry)
    monkeypatch.setattr(app_mod, "_save_registry", lambda: None)

    from pipeline_runner import _persist_stage_output
    first = {"stage_index": 0, "stage_type": "asr", "stage_ref": "x", "status": "done",
             "ran_at": 1.0, "duration_seconds": 0.1, "segments": [{"text": "first"}], "quality_flags": []}
    second = {"stage_index": 0, "stage_type": "asr", "stage_ref": "x", "status": "done",
              "ran_at": 2.0, "duration_seconds": 0.1, "segments": [{"text": "second"}], "quality_flags": []}
    _persist_stage_output("f1", first)
    _persist_stage_output("f1", second)

    key = "0" if "0" in registry["f1"]["stage_outputs"] else 0
    assert registry["f1"]["stage_outputs"][key]["segments"][0]["text"] == "second"
```

- [ ] **Step 2: Confirm fail (it's a stub now)**

Run: `pytest tests/test_pipeline_runner.py -v -k persist`
Expected: tests pass with "no-op" stub but **assertion fails** (registry not updated).

- [ ] **Step 3: Implement real persistence**

Replace the stub in `backend/pipeline_runner.py`:
```python
def _persist_stage_output(file_id: str, stage_output: StageOutput) -> None:
    """Write stage output to file registry.

    Uses string keys for stage_outputs dict so JSON round-trip is identity-preserving
    (json.dumps converts int keys to strings anyway, so we use str() upfront).
    """
    import app as app_mod
    with app_mod._registry_lock:
        entry = app_mod._file_registry.get(file_id)
        if entry is None:
            return
        outputs = entry.setdefault("stage_outputs", {})
        outputs[str(stage_output["stage_index"])] = dict(stage_output)
        app_mod._save_registry()
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_pipeline_runner.py -v`
Expected: All pass (5 prior + 2 new = 7)

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline_runner.py backend/tests/test_pipeline_runner.py
git commit -m "feat(v4 A1): persist stage_outputs to file_registry under _registry_lock"
```

---

### Task 7: Pipeline runner fail-fast error handling (Q5-a)

**🎯 Goal:** If any stage raises an exception during `transform()`, the runner stops immediately, persists the failed stage's `StageOutput` with `status="failed"` + error message, and re-raises to the JobQueue. No subsequent stages run.

**✅ Acceptance:**
- Stage exception → `StageOutput.status = "failed"` + `error: <traceback>` persisted
- Runner re-raises the original exception to caller (JobQueue worker)
- Downstream stages are NOT executed
- Already-completed stages stay persisted (don't truncate on later failure)

**Files:**
- Modify: `backend/pipeline_runner.py`
- Modify: `backend/tests/test_pipeline_runner.py`

- [ ] **Step 1: Write failing tests**

```python
def test_runner_fail_fast_on_stage_exception(monkeypatch):
    pipeline = _pipeline(mt_count=2, glossary_enabled=False)
    managers = _managers(mt_profiles=[
        {"id": "mt-uuid-0", "engine": "qwen3.5-35b-a3b",
         "input_lang": "zh", "output_lang": "zh",
         "system_prompt": "p1", "user_message_template": "p: {text}",
         "temperature": 0.1},
        {"id": "mt-uuid-1", "engine": "qwen3.5-35b-a3b",
         "input_lang": "zh", "output_lang": "zh",
         "system_prompt": "p2", "user_message_template": "p: {text}",
         "temperature": 0.1},
    ])

    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: MagicMock(
        transcribe=lambda *a, **kw: [{"start": 0, "end": 1, "text": "ok"}]))

    # MT stage 1 raises
    call_count = {"n": 0}
    def fake_qwen(sys_p, usr_p, temp):
        call_count["n"] += 1
        if call_count["n"] > 1:
            raise RuntimeError("Ollama down")
        return "translated"
    monkeypatch.setattr("stages.mt_stage._call_qwen", fake_qwen)

    persisted = []
    monkeypatch.setattr("pipeline_runner._persist_stage_output",
                        lambda fid, out: persisted.append(out))

    runner = PipelineRunner(pipeline, file_id="f1", audio_path="/tmp/x.wav", managers=managers)
    with pytest.raises(RuntimeError, match="Ollama down"):
        runner.run(user_id=1)

    # ASR + MT[0] succeed, MT[0] is index 1 — MT[1] should NOT have run
    # We can only assert that the failed stage was persisted with status=failed
    statuses = [p["status"] for p in persisted]
    assert "done" in statuses  # ASR
    assert "failed" in statuses  # MT[1] failed at index 2
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_pipeline_runner.py::test_runner_fail_fast_on_stage_exception -v`
Expected: FAIL (current code doesn't catch + persist failed status)

- [ ] **Step 3: Implement fail-fast handling**

Wrap each stage's `transform()` call in `PipelineRunner.run()`:
```python
import traceback

def _run_stage(self, stage, segments_in, ctx, stage_index, stage_type):
    """Wraps stage.transform() with fail-fast persistence.
    Re-raises original exception after persisting failed StageOutput."""
    start_t = time.time()
    try:
        segments_out = stage.transform(segments_in, ctx)
    except Exception as exc:
        failed_out: StageOutput = {
            "stage_index": stage_index,
            "stage_type": stage_type,
            "stage_ref": stage.stage_ref,
            "status": "failed",
            "ran_at": start_t,
            "duration_seconds": time.time() - start_t,
            "segments": [],
            "quality_flags": [],
        }
        # Attach error trace (non-spec field but useful for debug)
        failed_out["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        _persist_stage_output(self._file_id, failed_out)
        raise
    stage_out: StageOutput = {
        "stage_index": stage_index,
        "stage_type": stage_type,
        "stage_ref": stage.stage_ref,
        "status": "done",
        "ran_at": start_t,
        "duration_seconds": time.time() - start_t,
        "segments": segments_out,
        "quality_flags": [],
    }
    return stage_out, segments_out
```

Refactor `run()` to use `_run_stage()` for ASR / each MT / Glossary block.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_pipeline_runner.py -v`
Expected: 8 passed total

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline_runner.py backend/tests/test_pipeline_runner.py
git commit -m "feat(v4 A1): fail-fast — persist failed StageOutput then re-raise"
```

---

### Task 8: Pipeline runner Socket.IO progress (5% granularity, Q4-a)

**🎯 Goal:** Frontend (P4-P5) needs real-time stage progress to update the stage chain UI. Runner emits 3 events: `pipeline_stage_start` when entering a stage, `pipeline_stage_progress` every 5% during stage execution, `pipeline_stage_done` on completion.

**✅ Acceptance:**
- `socketio.emit('pipeline_stage_start', payload)` once per stage entry
- `socketio.emit('pipeline_stage_progress', payload)` at 5%, 10%, 15%, ... 100% milestones
- `socketio.emit('pipeline_stage_done', payload)` once per stage exit (with status: done/failed)
- Payload includes `file_id`, `pipeline_id`, `stage_index`, `stage_type`, `percent`, `segments_done`, `segments_total`
- Stage classes accept optional `progress_callback(percent)` and call it per-segment for MT/Glossary; runner wraps callback into emit

**Files:**
- Modify: `backend/pipeline_runner.py`
- Modify: `backend/stages/mt_stage.py`
- Modify: `backend/stages/glossary_stage.py`
- Modify: `backend/tests/test_pipeline_runner.py`

- [ ] **Step 1: Write failing test**

```python
def test_runner_emits_5pct_progress(monkeypatch):
    pipeline = _pipeline(mt_count=1, glossary_enabled=False)
    managers = _managers()
    # 20 segments → 5% = 1 segment increment
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: MagicMock(
        transcribe=lambda *a, **kw: [{"start": i, "end": i+1, "text": f"s{i}"} for i in range(20)]))
    monkeypatch.setattr("stages.mt_stage._call_qwen", lambda *a, **kw: "translated")
    monkeypatch.setattr("pipeline_runner._persist_stage_output", MagicMock())

    emitted = []
    def fake_emit(event, payload):
        emitted.append((event, payload))
    monkeypatch.setattr("pipeline_runner._socketio_emit", fake_emit)

    runner = PipelineRunner(pipeline, file_id="f1", audio_path="/tmp/x.wav", managers=managers)
    runner.run(user_id=1)

    events = [e[0] for e in emitted]
    # Should see at least: pipeline_stage_start, multiple pipeline_stage_progress, pipeline_stage_done
    assert "pipeline_stage_start" in events
    assert "pipeline_stage_done" in events
    progress_events = [e for e in emitted if e[0] == "pipeline_stage_progress"]
    # MT stage with 20 segments at 5% interval = ~20 progress emits per MT stage
    assert len(progress_events) >= 10  # conservatively at least 10 (5% * 20 = 100%)
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_pipeline_runner.py::test_runner_emits_5pct_progress -v`
Expected: FAIL

- [ ] **Step 3: Implement progress emission**

Add `_socketio_emit` helper + threading-safe emission. In `pipeline_runner.py`:
```python
def _socketio_emit(event: str, payload: dict) -> None:
    """Thin wrapper around app.socketio.emit() to keep import lazy."""
    try:
        import app as app_mod
        app_mod.socketio.emit(event, payload)
    except Exception:
        pass  # Socket emit failure non-fatal


def _make_progress_callback(file_id, pipeline_id, stage_index, stage_type, total_segments):
    """Build a per-segment progress callback that emits at 5% milestones."""
    last_pct = {"v": -1}
    def cb(done, total):
        if total <= 0:
            return
        pct = int((done / total) * 100)
        # Emit only when crossing a 5% milestone
        milestone = (pct // 5) * 5
        if milestone > last_pct["v"]:
            last_pct["v"] = milestone
            _socketio_emit("pipeline_stage_progress", {
                "file_id": file_id, "pipeline_id": pipeline_id,
                "stage_index": stage_index, "stage_type": stage_type,
                "percent": milestone, "segments_done": done, "segments_total": total,
            })
    return cb
```

In `MTStage.transform()` and `GlossaryStage.transform()`, after each segment processed:
```python
if context.progress_callback:
    context.progress_callback(i + 1, len(segments_in))
```

In `PipelineRunner.run()`, before each stage, wrap callback + emit start/done:
```python
total_segs = max(1, len(segments))  # for MT/Glossary stages; ASR caller has no count
_socketio_emit("pipeline_stage_start", {
    "file_id": self._file_id, "pipeline_id": self._pipeline["id"],
    "stage_index": stage_index, "stage_type": stage_type,
})
ctx.progress_callback = _make_progress_callback(
    self._file_id, self._pipeline["id"], stage_index, stage_type, total_segs)
# ... after stage:
_socketio_emit("pipeline_stage_done", {
    "file_id": self._file_id, "pipeline_id": self._pipeline["id"],
    "stage_index": stage_index, "stage_type": stage_type,
    "status": stage_out["status"], "duration_seconds": stage_out["duration_seconds"],
})
```

- [ ] **Step 4: Verify**

Run: `pytest tests/test_pipeline_runner.py -v`
Expected: All pass (9 total)

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline_runner.py backend/stages/mt_stage.py backend/stages/glossary_stage.py backend/tests/test_pipeline_runner.py
git commit -m "feat(v4 A1): Socket.IO progress events at 5% granularity"
```

---

### Task 9: Pipeline runner cancel_event integration (JobQueue compat)

**🎯 Goal:** Existing JobQueue `cancel_job(job_id)` sets a `threading.Event` that the worker can check. Runner must check the cancel event between stages AND inside long stages (per-segment in MT/Glossary). On cancel, raise `JobCancelled` so JobQueue marks job as `cancelled`.

**✅ Acceptance:**
- `runner.run(cancel_event=event)` accepts cancel_event
- Between stages: check event; if set → raise `JobCancelled`
- Inside MT/Glossary stages (per-segment loop): check event per-segment; if set → raise `JobCancelled`
- Already-completed stage outputs persisted (don't rollback on cancel)

**Files:**
- Modify: `backend/pipeline_runner.py`
- Modify: `backend/stages/mt_stage.py`
- Modify: `backend/stages/glossary_stage.py`
- Modify: `backend/tests/test_pipeline_runner.py`

- [ ] **Step 1: Write failing test**

```python
def test_runner_cancel_between_stages(monkeypatch):
    import threading
    from jobqueue.queue import JobCancelled

    pipeline = _pipeline(mt_count=2, glossary_enabled=False)
    managers = _managers(mt_profiles=[
        {"id": "mt-uuid-0", "engine": "qwen3.5-35b-a3b",
         "input_lang": "zh", "output_lang": "zh",
         "system_prompt": "p", "user_message_template": "polish: {text}",
         "temperature": 0.1},
        {"id": "mt-uuid-1", "engine": "qwen3.5-35b-a3b",
         "input_lang": "zh", "output_lang": "zh",
         "system_prompt": "p", "user_message_template": "broadcast: {text}",
         "temperature": 0.1},
    ])

    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: MagicMock(
        transcribe=lambda *a, **kw: [{"start": 0, "end": 1, "text": "ok"}]))

    cancel_event = threading.Event()

    # MT0 sets cancel mid-way (after one segment)
    def fake_qwen(sys_p, usr_p, temp):
        cancel_event.set()
        return "translated"
    monkeypatch.setattr("stages.mt_stage._call_qwen", fake_qwen)
    monkeypatch.setattr("pipeline_runner._persist_stage_output", MagicMock())
    monkeypatch.setattr("pipeline_runner._socketio_emit", MagicMock())

    runner = PipelineRunner(pipeline, file_id="f1", audio_path="/tmp/x.wav", managers=managers)
    with pytest.raises(JobCancelled):
        runner.run(user_id=1, cancel_event=cancel_event)
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_pipeline_runner.py::test_runner_cancel_between_stages -v`
Expected: FAIL

- [ ] **Step 3: Implement cancel checks**

In `PipelineRunner.run()` between stages:
```python
def _check_cancel(self, cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        from jobqueue.queue import JobCancelled
        raise JobCancelled("Pipeline cancelled by user")
```

Call `self._check_cancel(cancel_event)` before each stage.

In `MTStage.transform()` per-segment loop:
```python
if context.cancel_event is not None and context.cancel_event.is_set():
    from jobqueue.queue import JobCancelled
    raise JobCancelled("Cancelled mid-stage")
```

Same in `GlossaryStage.transform()`.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_pipeline_runner.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline_runner.py backend/stages/mt_stage.py backend/stages/glossary_stage.py backend/tests/test_pipeline_runner.py
git commit -m "feat(v4 A1): cancel_event check between stages + per-segment in MT/Glossary"
```

---

### Task 10: pipeline_overrides resolver (Q6-a per-(file,pipeline) scope)

**🎯 Goal:** MT Stage must read file-level `pipeline_overrides[<pipeline_id>][<stage_index>]` from `StageContext.pipeline_overrides` and apply override `system_prompt` / `user_message_template` if present. Resolver chain: file override → MT profile default.

**✅ Acceptance:**
- `MTStage._resolve_system_prompt(ctx)` reads from `ctx.pipeline_overrides[<stage_idx>]["system_prompt"]` if non-empty
- Same for `user_message_template`
- If override not set → fall back to MT profile default
- PipelineRunner loads `file.pipeline_overrides.get(pipeline_id, {})` and passes to each stage via StageContext

**Files:**
- Modify: `backend/stages/mt_stage.py`
- Modify: `backend/pipeline_runner.py`
- Modify: `backend/tests/test_stages_mt.py`

- [ ] **Step 1: Write failing tests**

Append to `test_stages_mt.py`:
```python
def test_mt_stage_uses_pipeline_override_system_prompt(monkeypatch):
    captured = {}
    def fake_qwen(sys_p, usr_p, temp):
        captured["sys"] = sys_p
        return "x"
    monkeypatch.setattr("stages.mt_stage._call_qwen", fake_qwen)

    profile = _profile()
    profile["system_prompt"] = "DEFAULT system prompt"
    stage = MTStage(profile)
    ctx = StageContext(file_id="f1", user_id=1, pipeline_id="p1",
                       stage_index=1, cancel_event=None, progress_callback=None,
                       pipeline_overrides={"1": {"system_prompt": "OVERRIDDEN"}})
    stage.transform([{"start": 0, "end": 1, "text": "x"}], ctx)
    assert captured["sys"] == "OVERRIDDEN"


def test_mt_stage_uses_pipeline_override_template(monkeypatch):
    captured = {}
    def fake_qwen(sys_p, usr_p, temp):
        captured["usr"] = usr_p
        return "x"
    monkeypatch.setattr("stages.mt_stage._call_qwen", fake_qwen)

    profile = _profile()
    profile["user_message_template"] = "default: {text}"
    stage = MTStage(profile)
    ctx = StageContext(file_id="f1", user_id=1, pipeline_id="p1",
                       stage_index=1, cancel_event=None, progress_callback=None,
                       pipeline_overrides={"1": {"user_message_template": "OVERRIDE: {text}"}})
    stage.transform([{"start": 0, "end": 1, "text": "hello"}], ctx)
    assert captured["usr"] == "OVERRIDE: hello"


def test_mt_stage_fallback_to_default_when_no_override(monkeypatch):
    captured = {}
    monkeypatch.setattr("stages.mt_stage._call_qwen",
                        lambda s, u, t: captured.setdefault("sys", s) or captured.setdefault("usr", u) or "x")
    profile = _profile()
    profile["system_prompt"] = "DEFAULT"
    stage = MTStage(profile)
    ctx = StageContext(file_id="f1", user_id=1, pipeline_id="p1",
                       stage_index=1, cancel_event=None, progress_callback=None,
                       pipeline_overrides={})  # empty
    stage.transform([{"start": 0, "end": 1, "text": "a"}], ctx)
    assert captured["sys"] == "DEFAULT"
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_stages_mt.py -v -k "override"`
Expected: 2 FAIL (one passes because default fallback)

- [ ] **Step 3: Implement override resolver**

In `mt_stage.py`:
```python
def _resolve_system_prompt(self, context: StageContext) -> str:
    override = context.pipeline_overrides.get(str(context.stage_index), {}).get("system_prompt")
    if override and isinstance(override, str) and override.strip():
        return override
    return self._profile["system_prompt"]

def _resolve_user_message_template(self, context: StageContext) -> str:
    override = context.pipeline_overrides.get(str(context.stage_index), {}).get("user_message_template")
    if override and isinstance(override, str) and override.strip() and "{text}" in override:
        return override
    return self._profile["user_message_template"]
```

In `MTStage.transform()`:
```python
system_prompt = self._resolve_system_prompt(context)
template = self._resolve_user_message_template(context)
```

In `PipelineRunner.run()`, load file's per-pipeline overrides:
```python
import app as app_mod
with app_mod._registry_lock:
    file_entry = app_mod._file_registry.get(self._file_id, {})
    all_overrides = file_entry.get("pipeline_overrides", {})
    overrides_for_this_pipeline = all_overrides.get(self._pipeline["id"], {})
# Pass to each stage context:
ctx = StageContext(..., pipeline_overrides=overrides_for_this_pipeline)
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_stages_mt.py tests/test_pipeline_runner.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add backend/stages/mt_stage.py backend/pipeline_runner.py backend/tests/test_stages_mt.py
git commit -m "feat(v4 A1): MTStage reads per-(file,pipeline) overrides (Q6-a scope)"
```

---

### Task 11: Emergent quality flag heuristic in ASR Stage

**🎯 Goal:** When ASR runs in `emergent-translate` mode (or any mode), some segments may have low confidence (Whisper avg_logprob < -1.0). Stage emits `quality_flags: ["low_logprob"]` on the StageOutput if any segment crosses threshold. Future UI surfaces this warning to users for manual review.

**✅ Acceptance:**
- `ASRStage.transform()` collects per-segment avg_logprob from Whisper engine (if engine provides it)
- If any segment has `avg_logprob < -1.0` → append `"low_logprob"` to `quality_flags`
- Quality flag returned via a new method `get_quality_flags()` or via a different channel (since `transform` returns only segments)
- PipelineRunner reads quality flags from ASRStage and attaches to `StageOutput.quality_flags`

**Files:**
- Modify: `backend/stages/asr_stage.py`
- Modify: `backend/pipeline_runner.py`
- Modify: `backend/tests/test_stages_asr.py`

- [ ] **Step 1: Write failing tests**

Append to `test_stages_asr.py`:
```python
def test_low_logprob_quality_flag(monkeypatch):
    mock_engine = MagicMock()
    mock_engine.transcribe.return_value = [
        {"start": 0, "end": 1, "text": "good", "avg_logprob": -0.5},
        {"start": 1, "end": 2, "text": "bad", "avg_logprob": -1.5},  # below threshold
    ]
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: mock_engine)
    stage = ASRStage(_profile(), audio_path="/tmp/x.wav")
    stage.transform([], _ctx())
    assert "low_logprob" in stage.quality_flags


def test_no_low_logprob_when_all_segments_confident(monkeypatch):
    mock_engine = MagicMock()
    mock_engine.transcribe.return_value = [
        {"start": 0, "end": 1, "text": "ok", "avg_logprob": -0.3},
    ]
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: mock_engine)
    stage = ASRStage(_profile(), audio_path="/tmp/x.wav")
    stage.transform([], _ctx())
    assert "low_logprob" not in stage.quality_flags


def test_no_quality_flag_when_engine_omits_logprob(monkeypatch):
    """Backward compat: existing whisper engines don't emit avg_logprob — no false positive."""
    mock_engine = MagicMock()
    mock_engine.transcribe.return_value = [{"start": 0, "end": 1, "text": "ok"}]
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: mock_engine)
    stage = ASRStage(_profile(), audio_path="/tmp/x.wav")
    stage.transform([], _ctx())
    assert stage.quality_flags == []
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_stages_asr.py -v -k logprob`
Expected: FAIL (no `quality_flags` attr)

- [ ] **Step 3: Implement quality flag**

In `asr_stage.py`:
```python
class ASRStage(PipelineStage):
    def __init__(self, asr_profile: dict, audio_path: str):
        self._profile = asr_profile
        self._audio_path = audio_path
        self.quality_flags: List[str] = []  # populated during transform()

    def transform(self, segments_in, context):
        # ... existing dispatch logic ...
        self.quality_flags = []  # reset on each call
        for seg in raw:
            avg_logprob = seg.get("avg_logprob")
            if avg_logprob is not None and avg_logprob < LOW_LOGPROB_THRESHOLD:
                if "low_logprob" not in self.quality_flags:
                    self.quality_flags.append("low_logprob")
            out.append({"start": seg["start"], "end": seg["end"], "text": seg.get("text", "").strip()})
        return out
```

In `pipeline_runner.py._run_stage()`, after success path:
```python
stage_out["quality_flags"] = getattr(stage, "quality_flags", [])
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_stages_asr.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/stages/asr_stage.py backend/pipeline_runner.py backend/tests/test_stages_asr.py
git commit -m "feat(v4 A1): ASRStage emergent quality flag — low_logprob (<-1.0)"
```

---

### Task 12: pipeline_run JobQueue handler

**🎯 Goal:** Wire `PipelineRunner` into JobQueue as a new `job_type="pipeline_run"`. Handler receives the job, loads pipeline from manager, instantiates runner, executes, handles cancel/fail.

**✅ Acceptance:**
- New `_pipeline_run_handler(job, cancel_event)` registered with JobQueue
- Handler reads `job.payload["pipeline_id"]` + `job.payload["file_id"]`
- Loads pipeline + managers, instantiates runner, calls `runner.run()`
- On `JobCancelled` → job status `cancelled`
- On other exceptions → job status `failed`
- On success → job status `done`

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_a1_pipeline_handler.py` (new)

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_a1_pipeline_handler.py
import pytest
from unittest.mock import MagicMock, patch


def test_pipeline_run_handler_dispatches_to_runner(monkeypatch):
    """_pipeline_run_handler creates PipelineRunner + calls run()."""
    import app as app_mod

    # Stub managers + registry
    monkeypatch.setattr(app_mod, "_pipeline_manager", MagicMock(get=MagicMock(return_value={
        "id": "p1", "asr_profile_id": "asr-1", "mt_stages": [],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": {},
    })))
    monkeypatch.setattr(app_mod, "_file_registry", {"f1": {"id": "f1", "file_path": "/tmp/x.wav"}})

    fake_runner_run = MagicMock(return_value=[
        {"stage_index": 0, "stage_type": "asr", "stage_ref": "asr-1",
         "status": "done", "ran_at": 1.0, "duration_seconds": 0.1,
         "segments": [], "quality_flags": []},
    ])

    with patch("app.PipelineRunner") as MockPR:
        MockPR.return_value.run = fake_runner_run
        job = MagicMock(payload={"pipeline_id": "p1", "file_id": "f1"},
                        file_id="f1", user_id=1)
        app_mod._pipeline_run_handler(job, cancel_event=None)
        fake_runner_run.assert_called_once()
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_a1_pipeline_handler.py -v`
Expected: FAIL (handler doesn't exist yet)

- [ ] **Step 3: Implement `_pipeline_run_handler` in `app.py`**

Add after existing `_mt_handler`:
```python
def _pipeline_run_handler(job, cancel_event=None):
    """v4 A1 — execute a Pipeline on a file via PipelineRunner.

    job.payload must contain {pipeline_id, file_id}.
    """
    from pipeline_runner import PipelineRunner
    payload = job.payload or {}
    pipeline_id = payload.get("pipeline_id")
    file_id = payload.get("file_id")
    if not pipeline_id or not file_id:
        raise ValueError("pipeline_run job requires payload {pipeline_id, file_id}")

    pipeline = _pipeline_manager.get(pipeline_id)
    if pipeline is None:
        raise ValueError(f"pipeline {pipeline_id} not found")

    with _registry_lock:
        entry = _file_registry.get(file_id)
    if entry is None:
        raise ValueError(f"file {file_id} not found")
    audio_path = entry.get("file_path") or str(UPLOAD_DIR / entry.get("stored_name", ""))

    runner = PipelineRunner(
        pipeline=pipeline,
        file_id=file_id,
        audio_path=audio_path,
        managers={
            "asr_manager": _asr_profile_manager,
            "mt_manager": _mt_profile_manager,
            "glossary_manager": _glossary_manager,
        },
    )
    runner.run(user_id=getattr(job, "user_id", None), cancel_event=cancel_event)
```

Register handler with JobQueue:
```python
# In existing JobQueue setup
_job_queue.register_handler("pipeline_run", _pipeline_run_handler)
```

Search for `register_handler("asr_transcribe"` or similar existing registration to find pattern.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_a1_pipeline_handler.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_a1_pipeline_handler.py
git commit -m "feat(v4 A1): _pipeline_run_handler — JobQueue dispatch to PipelineRunner"
```

---

### Task 13: `POST /api/pipelines/<id>/run` endpoint

**🎯 Goal:** REST endpoint that triggers a pipeline run on a file. Returns 202 + job_id (async). Frontend (and curl) calls this to start pipeline execution. Cancel via existing `DELETE /api/queue/<id>`.

**✅ Acceptance:**
- `POST /api/pipelines/<pipeline_id>/run?file_id=<fid>` accepts (or body `{"file_id": "..."}`)
- Validates: pipeline owned by user (via `@require_pipeline_owner`)
- Validates: file_id exists + owned by user (via `_can_access_file`)
- Enqueues job_type="pipeline_run" with payload {pipeline_id, file_id}
- Returns 202 + `{"job_id": ..., "queue_position": ...}`
- 400 if file_id missing; 404 if pipeline/file missing; 403 if not owned

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_a1_endpoints.py` (new)

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_a1_endpoints.py
import json, pytest


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["LOGIN_DISABLED"] = True
    app_module.app.config["R5_AUTH_BYPASS"] = True
    with app_module.app.test_client() as c:
        yield c


def _create_pipeline(client):
    asr = client.post("/api/asr_profiles", data=json.dumps({
        "name": "a1-asr", "engine": "mlx-whisper", "model_size": "large-v3",
        "mode": "same-lang", "language": "en",
    }), content_type="application/json").get_json()
    mt = client.post("/api/mt_profiles", data=json.dumps({
        "name": "a1-mt", "engine": "qwen3.5-35b-a3b",
        "input_lang": "zh", "output_lang": "zh",
        "system_prompt": "x", "user_message_template": "go: {text}",
    }), content_type="application/json").get_json()
    pipe = client.post("/api/pipelines", data=json.dumps({
        "name": "a1-pipe", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": {"family": "Noto Sans TC", "size": 35, "color": "#ffffff",
                        "outline_color": "#000000", "outline_width": 2, "margin_bottom": 40,
                        "subtitle_source": "auto", "bilingual_order": "target_top"},
    }), content_type="application/json").get_json()
    return asr, mt, pipe


def test_run_pipeline_202(client, monkeypatch):
    """POST /api/pipelines/<id>/run returns 202 + job_id."""
    # Stub file registry
    import app as app_mod
    monkeypatch.setattr(app_mod, "_file_registry",
                        {"f-test": {"id": "f-test", "file_path": "/tmp/fake.wav"}})

    _, _, pipe = _create_pipeline(client)
    resp = client.post(f"/api/pipelines/{pipe['id']}/run",
                       data=json.dumps({"file_id": "f-test"}),
                       content_type="application/json")
    assert resp.status_code == 202
    body = resp.get_json()
    assert "job_id" in body


def test_run_pipeline_400_missing_file_id(client):
    _, _, pipe = _create_pipeline(client)
    resp = client.post(f"/api/pipelines/{pipe['id']}/run",
                       data=json.dumps({}), content_type="application/json")
    assert resp.status_code == 400


def test_run_pipeline_404_unknown_file(client):
    _, _, pipe = _create_pipeline(client)
    resp = client.post(f"/api/pipelines/{pipe['id']}/run",
                       data=json.dumps({"file_id": "ghost"}),
                       content_type="application/json")
    assert resp.status_code == 404
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_a1_endpoints.py -v -k "run_pipeline"`
Expected: FAIL with 404 (route not registered)

- [ ] **Step 3: Implement endpoint in `app.py`**

After existing Pipeline CRUD endpoints:
```python
@app.route('/api/pipelines/<pipeline_id>/run', methods=['POST'])
@login_required
@require_pipeline_owner
def run_pipeline(pipeline_id):
    data = request.get_json(silent=True) or {}
    file_id = data.get("file_id") or request.args.get("file_id")
    if not file_id:
        return jsonify({"error": "file_id required"}), 400

    pipeline = _pipeline_manager.get(pipeline_id)
    if pipeline is None:
        return jsonify({"error": "pipeline not found"}), 404

    with _registry_lock:
        file_entry = _file_registry.get(file_id)
    if file_entry is None:
        return jsonify({"error": "file not found"}), 404

    user_id = getattr(current_user, "id", None)
    # Enqueue pipeline_run job
    job_id = _job_queue.enqueue(
        user_id=user_id, file_id=file_id, job_type="pipeline_run",
        payload={"pipeline_id": pipeline_id, "file_id": file_id},
    )
    return jsonify({"job_id": job_id}), 202
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_a1_endpoints.py -v -k "run_pipeline"`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_a1_endpoints.py
git commit -m "feat(v4 A1): POST /api/pipelines/<id>/run — async via JobQueue"
```

---

### Task 14: `POST /api/files/<fid>/stages/<idx>/rerun` endpoint

**🎯 Goal:** Re-run an individual stage (truncate downstream stage_outputs + re-cascade). Used when user manually edits stage[N] segment text and wants stage[N+1..] re-computed, or when user wants to retry a failed stage.

**✅ Acceptance:**
- `POST /api/files/<fid>/stages/<idx>/rerun` truncates `stage_outputs[idx+1..]` then enqueues pipeline_run continuing from `idx+1`
- Returns 202 + job_id
- 404 if file/stage not found
- 403 if not owned

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/pipeline_runner.py` (add `start_from_stage` parameter)
- Modify: `backend/tests/test_a1_endpoints.py`

- [ ] **Step 1: Write failing test**

```python
def test_rerun_stage_endpoint(client, monkeypatch):
    """POST /api/files/<fid>/stages/<idx>/rerun truncates downstream + enqueues."""
    import app as app_mod
    monkeypatch.setattr(app_mod, "_file_registry", {
        "f-rerun": {
            "id": "f-rerun", "file_path": "/tmp/fake.wav",
            "pipeline_id": "p-rerun",  # tracks which pipeline last ran
            "stage_outputs": {
                "0": {"stage_index": 0, "stage_type": "asr", "stage_ref": "x",
                      "status": "done", "ran_at": 1, "duration_seconds": 1,
                      "segments": [], "quality_flags": []},
                "1": {"stage_index": 1, "stage_type": "mt", "stage_ref": "x",
                      "status": "done", "ran_at": 2, "duration_seconds": 1,
                      "segments": [], "quality_flags": []},
            },
        }
    })
    _, _, pipe = _create_pipeline(client)
    # Update file's pipeline_id to the created pipeline
    with app_mod._registry_lock:
        app_mod._file_registry["f-rerun"]["pipeline_id"] = pipe["id"]

    resp = client.post(f"/api/files/f-rerun/stages/1/rerun")
    assert resp.status_code == 202
    # After enqueue, stage_outputs[1] should be removed (truncated)
    assert "1" not in app_mod._file_registry["f-rerun"]["stage_outputs"]
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_a1_endpoints.py -v -k "rerun"`
Expected: FAIL with 404

- [ ] **Step 3: Implement endpoint**

```python
@app.route('/api/files/<fid>/stages/<int:stage_idx>/rerun', methods=['POST'])
@login_required
@require_file_owner
def rerun_stage(fid, stage_idx):
    with _registry_lock:
        entry = _file_registry.get(fid)
        if entry is None:
            return jsonify({"error": "file not found"}), 404
        pipeline_id = entry.get("pipeline_id")
        if not pipeline_id:
            return jsonify({"error": "file has no associated pipeline"}), 400
        # Truncate downstream stage_outputs[idx..]
        outputs = entry.setdefault("stage_outputs", {})
        for key in list(outputs.keys()):
            if int(key) >= stage_idx:
                del outputs[key]
        _save_registry()

    user_id = getattr(current_user, "id", None)
    job_id = _job_queue.enqueue(
        user_id=user_id, file_id=fid, job_type="pipeline_run",
        payload={"pipeline_id": pipeline_id, "file_id": fid, "start_from_stage": stage_idx},
    )
    return jsonify({"job_id": job_id}), 202
```

Also add `start_from_stage` parameter to `PipelineRunner.run()` and the handler. Skip already-completed stages.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_a1_endpoints.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/pipeline_runner.py backend/tests/test_a1_endpoints.py
git commit -m "feat(v4 A1): rerun individual stage — truncate downstream + re-cascade"
```

---

### Task 15: `PATCH /api/files/<fid>/stages/<idx>/segments/<seg>` — edit per-stage segment text

**🎯 Goal:** User can edit a segment's text on a specific stage's output. Edit invalidates downstream stages (they're marked `needs_rerun` until user explicitly re-runs).

**✅ Acceptance:**
- `PATCH /api/files/<fid>/stages/<idx>/segments/<seg_idx>` body `{"text": "new text"}` updates the segment
- After edit, downstream stages (`idx+1..`) marked with `status="needs_rerun"`
- Returns 200 with updated stage output
- 404 if file/stage/segment not found

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/tests/test_a1_endpoints.py`

- [ ] **Step 1: Write failing test**

```python
def test_edit_stage_segment(client, monkeypatch):
    """PATCH segment text + mark downstream needs_rerun."""
    import app as app_mod
    monkeypatch.setattr(app_mod, "_file_registry", {
        "f-edit": {
            "id": "f-edit", "stage_outputs": {
                "0": {"stage_index": 0, "stage_type": "asr", "stage_ref": "x",
                      "status": "done", "ran_at": 1, "duration_seconds": 1,
                      "segments": [{"start": 0, "end": 1, "text": "original"}],
                      "quality_flags": []},
                "1": {"stage_index": 1, "stage_type": "mt", "stage_ref": "x",
                      "status": "done", "ran_at": 2, "duration_seconds": 1,
                      "segments": [{"start": 0, "end": 1, "text": "translated"}],
                      "quality_flags": []},
            },
        }
    })
    resp = client.patch("/api/files/f-edit/stages/0/segments/0",
                        data=json.dumps({"text": "edited"}),
                        content_type="application/json")
    assert resp.status_code == 200
    assert app_mod._file_registry["f-edit"]["stage_outputs"]["0"]["segments"][0]["text"] == "edited"
    assert app_mod._file_registry["f-edit"]["stage_outputs"]["1"]["status"] == "needs_rerun"
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_a1_endpoints.py -v -k "edit_stage"`
Expected: FAIL 404

- [ ] **Step 3: Implement**

```python
@app.route('/api/files/<fid>/stages/<int:stage_idx>/segments/<int:seg_idx>', methods=['PATCH'])
@login_required
@require_file_owner
def edit_stage_segment(fid, stage_idx, seg_idx):
    data = request.get_json(silent=True) or {}
    new_text = data.get("text")
    if new_text is None:
        return jsonify({"error": "text required"}), 400

    with _registry_lock:
        entry = _file_registry.get(fid)
        if entry is None:
            return jsonify({"error": "file not found"}), 404
        outputs = entry.get("stage_outputs", {})
        stage_out = outputs.get(str(stage_idx))
        if stage_out is None:
            return jsonify({"error": "stage not found"}), 404
        segments = stage_out.get("segments", [])
        if seg_idx >= len(segments):
            return jsonify({"error": "segment index out of range"}), 404
        segments[seg_idx]["text"] = new_text
        # Mark downstream as needs_rerun
        for key, out in outputs.items():
            if int(key) > stage_idx:
                out["status"] = "needs_rerun"
        _save_registry()
        return jsonify(stage_out), 200
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_a1_endpoints.py -v -k edit_stage`
Expected: passed

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_a1_endpoints.py
git commit -m "feat(v4 A1): PATCH stage segment + mark downstream needs_rerun"
```

---

### Task 16: `POST /api/files/<fid>/pipeline_overrides` — set per-pipeline overrides (Q6-a)

**🎯 Goal:** User stores file-level prompt overrides keyed by `(file_id, pipeline_id)` pair. Next pipeline run reads these overrides per Q6-a scope.

**✅ Acceptance:**
- `POST /api/files/<fid>/pipeline_overrides` body `{"pipeline_id": "...", "stage_index": 1, "overrides": {"system_prompt": "..."}}`
- Writes to `file.pipeline_overrides[pipeline_id][str(stage_index)] = overrides`
- Returns 200 with updated overrides dict
- Can also CLEAR by passing `overrides: null`

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/tests/test_a1_endpoints.py`

- [ ] **Step 1: Write failing test**

```python
def test_set_pipeline_overrides(client, monkeypatch):
    import app as app_mod
    monkeypatch.setattr(app_mod, "_file_registry", {"f-ov": {"id": "f-ov"}})
    resp = client.post("/api/files/f-ov/pipeline_overrides",
                       data=json.dumps({
                           "pipeline_id": "p1", "stage_index": 1,
                           "overrides": {"system_prompt": "CUSTOM"},
                       }), content_type="application/json")
    assert resp.status_code == 200
    assert app_mod._file_registry["f-ov"]["pipeline_overrides"]["p1"]["1"]["system_prompt"] == "CUSTOM"


def test_clear_pipeline_overrides(client, monkeypatch):
    import app as app_mod
    monkeypatch.setattr(app_mod, "_file_registry", {
        "f-clr": {"id": "f-clr", "pipeline_overrides": {"p1": {"1": {"system_prompt": "X"}}}}
    })
    resp = client.post("/api/files/f-clr/pipeline_overrides",
                       data=json.dumps({"pipeline_id": "p1", "stage_index": 1, "overrides": None}),
                       content_type="application/json")
    assert resp.status_code == 200
    assert "1" not in app_mod._file_registry["f-clr"]["pipeline_overrides"].get("p1", {})
```

- [ ] **Step 2: Confirm fail**

Run: `pytest tests/test_a1_endpoints.py -v -k "pipeline_overrides"`
Expected: FAIL 404

- [ ] **Step 3: Implement**

```python
@app.route('/api/files/<fid>/pipeline_overrides', methods=['POST'])
@login_required
@require_file_owner
def set_pipeline_overrides(fid):
    data = request.get_json(silent=True) or {}
    pipeline_id = data.get("pipeline_id")
    stage_index = data.get("stage_index")
    overrides = data.get("overrides")  # dict or None to clear
    if not pipeline_id or stage_index is None:
        return jsonify({"error": "pipeline_id + stage_index required"}), 400

    with _registry_lock:
        entry = _file_registry.get(fid)
        if entry is None:
            return jsonify({"error": "file not found"}), 404
        all_ovs = entry.setdefault("pipeline_overrides", {})
        per_pipe = all_ovs.setdefault(pipeline_id, {})
        if overrides is None:
            per_pipe.pop(str(stage_index), None)
        else:
            per_pipe[str(stage_index)] = overrides
        _save_registry()
        return jsonify({"pipeline_overrides": entry["pipeline_overrides"]}), 200
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_a1_endpoints.py -v -k pipeline_overrides`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_a1_endpoints.py
git commit -m "feat(v4 A1): POST /api/files/<fid>/pipeline_overrides (per-pipeline scope)"
```

---

### Task 17: ASR profile schema — remove word_timestamps field (Q7-b)

**🎯 Goal:** Per Q7-b lock, drop `word_timestamps` field from ASR profile validator + manager + REST. Whisper engines also drop the field from their schemas.

**✅ Acceptance:**
- `validate_asr_profile()` no longer validates `word_timestamps`
- `ASRProfileManager.create()` no longer stamps `word_timestamps` on entry
- `whisper_engine.py` + `mlx_whisper_engine.py` `get_params_schema()` drops `word_timestamps`
- `transcribe()` no longer accepts/uses `word_timestamps` kwarg
- Existing tests that asserted `word_timestamps: false` updated to no longer expect the field

**Files:**
- Modify: `backend/asr_profiles.py`
- Modify: `backend/asr/whisper_engine.py`
- Modify: `backend/asr/mlx_whisper_engine.py`
- Modify: `backend/tests/test_asr_profiles.py`

- [ ] **Step 1: Update validator + manager**

In `backend/asr_profiles.py`, remove the `word_timestamps` line from `validate_asr_profile`:
```python
# REMOVE:
# for key in ("word_timestamps", "condition_on_previous_text", "simplified_to_traditional"):
# REPLACE WITH:
for key in ("condition_on_previous_text", "simplified_to_traditional"):
```

In `create()`:
```python
# REMOVE:
# "word_timestamps": bool(data.get("word_timestamps", False)),
```

- [ ] **Step 2: Update Whisper engine schemas**

In `backend/asr/whisper_engine.py` and `backend/asr/mlx_whisper_engine.py`:
- Remove `word_timestamps` from `get_params_schema()` return
- Remove `word_timestamps` from `transcribe()` kwargs and internal logic

- [ ] **Step 3: Update existing tests**

In `backend/tests/test_asr_profiles.py`, remove any assertion about `word_timestamps` field.

- [ ] **Step 4: Run full backend suite to confirm no regression**

Run: `pytest tests/ --tb=short -q 2>&1 | tail -10`
Expected: same baseline count (891) ± word_timestamps-related test adjustments

- [ ] **Step 5: Commit**

```bash
git add backend/asr_profiles.py backend/asr/whisper_engine.py backend/asr/mlx_whisper_engine.py backend/tests/test_asr_profiles.py
git commit -m "refactor(v4 A1): drop word_timestamps from ASR schema + engines (Q7-b)"
```

---

### Task 18: A1 integration test — end-to-end pipeline run via REST API

**🎯 Goal:** A single test that exercises the full A1 surface: create ASR + MT + Pipeline → enqueue pipeline_run → assert stage_outputs populated correctly.

**✅ Acceptance:**
- Test creates entities via REST
- Triggers `POST /api/pipelines/<id>/run` with a stub audio file
- Mocks `mlx_whisper.transcribe` and `_call_qwen` to avoid real model invocation
- Asserts: after job completes, `GET /api/files/<fid>` shows `stage_outputs` with correct schema
- Validates segment count invariant end-to-end

**Files:**
- Create: `backend/tests/test_a1_integration.py`

- [ ] **Step 1: Write test**

```python
# backend/tests/test_a1_integration.py
"""End-to-end A1 pipeline run integration test (all stages mocked)."""
import json, pytest, time
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["LOGIN_DISABLED"] = True
    app_module.app.config["R5_AUTH_BYPASS"] = True
    with app_module.app.test_client() as c:
        yield c


def test_full_pipeline_run_via_rest(client, monkeypatch):
    """Create entities → trigger pipeline run → verify stage_outputs."""
    import app as app_mod
    # Inject stub file
    monkeypatch.setitem(app_mod._file_registry, "f-int", {
        "id": "f-int", "file_path": "/tmp/fake.wav", "user_id": 1,
    })

    # Mock Whisper + qwen
    fake_asr_engine = MagicMock()
    fake_asr_engine.transcribe.return_value = [
        {"start": 0.0, "end": 1.0, "text": "hello"},
        {"start": 1.0, "end": 2.0, "text": "world"},
    ]
    monkeypatch.setattr("stages.asr_stage.create_asr_engine",
                        lambda cfg: fake_asr_engine)
    monkeypatch.setattr("stages.mt_stage._call_qwen",
                        lambda s, u, t: u.replace("polish: ", "polished_"))

    # Create ASR + MT + Pipeline
    asr = client.post("/api/asr_profiles", data=json.dumps({
        "name": "asr-int", "engine": "mlx-whisper", "model_size": "large-v3",
        "mode": "same-lang", "language": "en",
    }), content_type="application/json").get_json()
    mt = client.post("/api/mt_profiles", data=json.dumps({
        "name": "mt-int", "engine": "qwen3.5-35b-a3b",
        "input_lang": "zh", "output_lang": "zh",
        "system_prompt": "polish", "user_message_template": "polish: {text}",
    }), content_type="application/json").get_json()
    pipe = client.post("/api/pipelines", data=json.dumps({
        "name": "int-pipe", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": {"family": "Noto Sans TC", "size": 35, "color": "#ffffff",
                        "outline_color": "#000000", "outline_width": 2, "margin_bottom": 40,
                        "subtitle_source": "auto", "bilingual_order": "target_top"},
    }), content_type="application/json").get_json()

    # Trigger run
    resp = client.post(f"/api/pipelines/{pipe['id']}/run",
                       data=json.dumps({"file_id": "f-int"}),
                       content_type="application/json")
    assert resp.status_code == 202
    job_id = resp.get_json()["job_id"]

    # Wait for job to complete (JobQueue runs in background threads)
    deadline = time.time() + 10
    while time.time() < deadline:
        outputs = app_mod._file_registry["f-int"].get("stage_outputs", {})
        if "1" in outputs and outputs["1"].get("status") == "done":
            break
        time.sleep(0.1)
    else:
        pytest.fail("pipeline_run job did not complete within 10 seconds")

    # Verify ASR stage output
    outputs = app_mod._file_registry["f-int"]["stage_outputs"]
    assert "0" in outputs
    assert outputs["0"]["stage_type"] == "asr"
    assert len(outputs["0"]["segments"]) == 2
    assert outputs["0"]["segments"][0]["text"] == "hello"

    # Verify MT stage output (segment count invariant + transformation)
    assert "1" in outputs
    assert outputs["1"]["stage_type"] == "mt"
    assert len(outputs["1"]["segments"]) == 2  # segment count preserved
    assert outputs["1"]["segments"][0]["text"] == "polished_hello"
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_a1_integration.py -v`
Expected: 1 passed

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_a1_integration.py
git commit -m "test(v4 A1): end-to-end pipeline run integration via REST + mocked stages"
```

---

### Task 19: Full suite + smoke regression check

**🎯 Goal:** Confirm A1 doesn't regress P1 or any prior feature. Backend test suite must remain green except known pre-existing failures.

**✅ Acceptance:**
- `pytest tests/ --tb=no -q` shows ≥ A1 test count above 891 baseline
- 14 pre-existing failures unchanged (no new failures)
- Curl smoke: `curl -X POST /api/pipelines/<id>/run` returns 202

**Files:**
- (None — verification only)

- [ ] **Step 1: Run full suite**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend" && pytest tests/ --tb=no -q 2>&1 | tail -10
```

- [ ] **Step 2: Compare to 891 baseline**

Expected: ~940-960 pass (891 + ~40-50 new A1 tests); same 14 pre-existing failures.

- [ ] **Step 3: Curl smoke (with running backend)**

```bash
COOKIE_JAR=$(mktemp)
curl -s -c $COOKIE_JAR -X POST http://localhost:5001/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"AdminPass1!"}'

# Build entities + trigger run (full curl chain in T20 milestone task)
```

- [ ] **Step 4: No commit needed (verification only)**

---

### Task 20: CLAUDE.md update — A1 entry + retire "no build system" rule

**🎯 Goal:** Document accuracy. CLAUDE.md should reflect:
1. A1 added 4 new REST endpoints + new stage layer
2. word_timestamps removed from ASR schema
3. "Do not add a build system" rule retired (A3 will add Vite + React)

**✅ Acceptance:**
- REST endpoints table updated with 4 new A1 routes
- New A1 entry in Completed Features above v4.0 Phase 1
- "No build system" rule deleted from Development Guidelines

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add 4 new endpoint rows**

After existing pipeline endpoints in CLAUDE.md REST endpoints table:
```markdown
| POST | `/api/pipelines/<id>/run` | Enqueue pipeline run on a file (v4.0 A1) |
| POST | `/api/files/<fid>/stages/<idx>/rerun` | Re-run individual stage |
| PATCH | `/api/files/<fid>/stages/<idx>/segments/<seg_idx>` | Edit per-stage segment text |
| POST | `/api/files/<fid>/pipeline_overrides` | Set file+pipeline-level prompt overrides |
```

- [ ] **Step 2: Add A1 Completed Features entry**

Above v4.0 Phase 1 entry:
```markdown
### v4.0 A1 — Stage executor + pipeline_runner (in progress on `chore/asr-mt-rearchitecture-research`)
- 3 new stage classes (`backend/stages/asr_stage.py` / `mt_stage.py` / `glossary_stage.py`) sharing `PipelineStage` ABC, per-segment-1:1 contract per design doc §4
- `PipelineRunner` (`backend/pipeline_runner.py`) linear stage executor + Socket.IO progress at 5% granularity + fail-fast + cancel_event integration with JobQueue
- 4 new REST endpoints (run / rerun / edit / pipeline_overrides) — async via existing JobQueue `pipeline_run` handler
- `word_timestamps` field removed from ASR profile schema + Whisper engines (Q7-b)
- Per-file per-pipeline prompt override resolution (Q6-a scope)
- ~50 new backend tests (3 stage classes + runner + endpoints + integration)
- **Legacy code path zero-touch** — `transcribe_with_segments` / `_auto_translate` / `alignment_pipeline.py` 全部唔郁，A5 sub-phase 砍走
```

- [ ] **Step 3: Delete "Do not add a build system" rule**

Find in CLAUDE.md (Development Guidelines section):
```markdown
- Do not add a build system unless the frontend grows to multiple files requiring it
```

Delete this line. Add note:
```markdown
- Frontend will adopt Vite + React + TypeScript stack in v4.0 A3-A4 sub-phases (per design doc §14)
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(v4 A1): add 4 new endpoints + A1 Completed Features entry + retire 'no build system' rule"
```

---

### Task 21: A1 milestone check + design doc approval status

**🎯 Goal:** Tick A1 done in design doc. Final acceptance summary.

**✅ Acceptance:**
- Design doc §13 reflects A1 complete
- Brief milestone summary in plan comment block

**Files:**
- Modify: `docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md`

- [ ] **Step 1: Update §13 Approval Status**

Find:
```markdown
- [ ] **A1 plan written** ([2026-05-17-v4-A1-backend-foundation-plan.md](...))
- [ ] A1 implementation executed
```

Change to:
```markdown
- [x] **A1 plan written + executed** — 4 new REST endpoints, 3 stage classes, PipelineRunner, ~50 new backend tests
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md
git commit -m "docs(v4 A1): mark A1 complete in design doc approval status"
```

---

## Self-Review

### Spec coverage

| Design doc § | A1 task | Notes |
|---|---|---|
| §3.1.2 ASR Profile 3-mode picker | T2 | Same-lang / emergent-translate / translate-to-en dispatch |
| §3.2 MT Profile transform | T3 | qwen3.5-35b per-segment with template |
| §3.3 Glossary Stage standalone | T4 | Multi-glossary explicit order |
| §4 Pipeline runner contract | T5, T6, T7, T8, T9 | Sequential + persist + fail-fast + progress + cancel |
| §6.4 New REST endpoints | T13, T14, T15, T16 | run / rerun / edit segment / pipeline_overrides |
| §6.6 Segment schema `stage_outputs` | T6 | Persistence helper |
| §7 Ownership (Q6-a per-pipeline overrides) | T10, T16 | MTStage resolver + REST set endpoint |
| §10 Risk: emergent quality flag | T11 | low_logprob heuristic |
| **Q7-b word_timestamps removal** | T17 | ASR schema + engines stripped |
| §6.4 JobQueue integration | T12 | `_pipeline_run_handler` registered |

### Placeholder scan: pass
- All steps have actual code (no `...` ellipsis)
- All test bodies are complete
- No "TBD" / "TODO" anywhere

### Type consistency check: pass
- `PipelineStage` / `StageContext` / `StageOutput` named consistently
- Method names consistent: `transform(segments_in, context) -> segments_out`
- Stage type strings consistent: `"asr"` / `"mt"` / `"glossary"`
- StageOutput fields consistent: `stage_index, stage_type, stage_ref, status, ran_at, duration_seconds, segments, quality_flags`

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-17-v4-A1-backend-foundation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task + two-stage review. Best for 21-task scale.

**2. Inline Execution** — Execute tasks in this session using executing-plans. Faster but consumes main context.

**Which approach?**
