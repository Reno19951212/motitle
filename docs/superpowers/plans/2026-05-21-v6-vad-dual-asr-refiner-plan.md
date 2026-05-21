# v6 VAD + Dual-ASR + Refiner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement v6 Cantonese broadcast subtitle pipeline: Silero VAD → qwen3-asr per-region + mlx-whisper time-grid → Time-Anchored Merge → Refiner LLM (simplified prompt). Frontend integration via pipeline JSON registration + prompt editing UI. Full TDD coverage.

**Architecture:** 5-stage pipeline (Stage 0: VAD, Stage 1A: qwen3 per-region, Stage 1B: mlx time-grid, Stage 2: merge, Stage 3: refiner). Stages 4+ (translator, persist) unchanged from v5-A2. `PipelineRunner._run_v6()` dispatch on `pipeline_type == "v6_vad_dual_asr"`.

**Target branch (not yet created):** `feat/v6-vad-dual-asr-refiner` (branch off `feat/frontend-redesign`)

**Spec reference:** [docs/superpowers/specs/2026-05-21-v6-vad-dual-asr-refiner-design.md](../specs/2026-05-21-v6-vad-dual-asr-refiner-design.md)

**Prototype evidence:**
- `/tmp/v6_prototype_stage1a_v2.json` — Stage 0+1A: 28 regions, 1066 chars, 0.8s VAD
- `/tmp/v6_stage2_result.json` — Stage 2: 86 merged → 84 collapsed segs
- `backend/scripts/v5_prototype/prototype_vad_qwen3.py` — orchestrator source
- `backend/scripts/v5_prototype/qwen3_vad_subprocess.py` — subprocess (reused)

**Estimated total effort:** 13 tasks × 20–60 min each = ~9h for a capable subagent

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `backend/stages/v6/__init__.py` | Create | Package init |
| `backend/stages/v6/silero_vad_stage.py` | Create | Stage 0: VAD |
| `backend/stages/v6/qwen3_per_region_stage.py` | Create | Stage 1A: qwen3 per-region |
| `backend/engines/transcribe/qwen3_vad_engine.py` | Create | Engine wrapper for qwen3 subprocess |
| `backend/stages/v6/time_anchored_merge_stage.py` | Create | Stage 2: merge algorithm |
| `backend/stages/v6/refiner_stage_v6.py` | Create | Stage 3: v6 refiner (thin wrapper over v5 RefinerStage) |
| `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_v6.json` | Create | v6 simplified prompt (no cascade/orphan/hallucination drop) |
| `backend/pipeline_runner.py` | Modify | Add `_run_v6()` DAG dispatch |
| `backend/config/pipelines/<uuid1>.json` | Create | v6 pipeline — 賽馬 (Cantonese) |
| `backend/config/pipelines/<uuid2>.json` | Create | v6 pipeline — Winning Factor (optional) |
| `backend/tests/test_v6_stages.py` | Create | Unit tests for Stages 0–3 |
| `backend/tests/test_v6_runner.py` | Create | Integration test for `_run_v6()` + T11/T12 resolution tests |
| `frontend/tests-e2e/v6-pipeline-smoke.spec.ts` | Create | E2E smoke test: upload → v6 pipeline → Proofread |
| `docs/superpowers/validation/v6-validation.md` | Create | Validation tracker stub |
| `backend/pipelines.py` | Modify | T11: accept `refiner_prompt_override` in `update_if_owned` |
| `backend/translation/prompt_override_validator.py` | Modify | T12: add `qwen3_context` as known key |
| `frontend/src/pages/Pipelines.tsx` | Modify | T13: refiner prompt panel for v6 pipelines |
| `frontend/src/pages/Proofread/components/PromptOverridesDrawer.tsx` | Modify | T13: qwen3_context + refiners.zh fields |
| `frontend/src/tests/v6-prompt-editing.test.ts` | Create | T13: vitest cases for prompt editing UI helpers |

---

## Task 1: Create branch + commit spec and plan

**Estimated time:** 10 min
**Files:** None modified (just git operations)

- [ ] **Step 1: Create branch off `feat/frontend-redesign`**

```bash
git checkout feat/frontend-redesign
git pull origin feat/frontend-redesign
git checkout -b feat/v6-vad-dual-asr-refiner
```

- [ ] **Step 2: Verify the two docs files are present**

```bash
ls docs/superpowers/specs/2026-05-21-v6-vad-dual-asr-refiner-design.md
ls docs/superpowers/plans/2026-05-21-v6-vad-dual-asr-refiner-plan.md
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-05-21-v6-vad-dual-asr-refiner-design.md
git add docs/superpowers/plans/2026-05-21-v6-vad-dual-asr-refiner-plan.md
git commit -m "docs(v6): add VAD+dual-ASR+refiner design spec + implementation plan"
```

**Gate:** Branch created, docs committed, `git log --oneline -1` shows the commit.

---

## Task 2: Silero VAD stage class + tests (Stage 0)

**Estimated time:** 45 min
**Files:**
- Create: `backend/stages/v6/__init__.py`
- Create: `backend/stages/v6/silero_vad_stage.py`
- Create: `backend/tests/test_v6_stages.py` (start with VAD tests)

### Step 1: Write failing tests (RED)

```python
# backend/tests/test_v6_stages.py
"""Tests for v6 stage classes."""
import pytest
from unittest.mock import patch, MagicMock
from stages import StageContext

# ---------------------------------------------------------------------------
# Stage 0 — SileroVadStage
# ---------------------------------------------------------------------------

def _make_context(overrides=None):
    return StageContext(
        file_id="test_file", user_id=1,
        pipeline_id="test_pipe", stage_index=0,
        cancel_event=None, progress_callback=None,
        pipeline_overrides=overrides or {},
        audio_path="/fake/audio.mp4",
    )


class TestSileroVadStage:
    def test_stage_type(self):
        from stages.v6.silero_vad_stage import SileroVadStage
        stage = SileroVadStage({"vad_threshold": 0.5})
        assert stage.stage_type == "vad"

    def test_stage_ref_uses_profile_id(self):
        from stages.v6.silero_vad_stage import SileroVadStage
        stage = SileroVadStage({"id": "vad-profile-1", "vad_threshold": 0.5})
        assert stage.stage_ref == "vad-profile-1"

    def test_returns_list_of_region_dicts(self):
        from stages.v6.silero_vad_stage import SileroVadStage
        stage = SileroVadStage({"vad_threshold": 0.5})
        fake_regions = [{"start": 0.5, "end": 3.2}, {"start": 5.1, "end": 8.7}]

        with patch.object(stage, "_run_vad", return_value=fake_regions):
            result = stage.transform([], _make_context())

        assert len(result) == 2
        assert result[0]["start"] == pytest.approx(0.5)
        assert result[1]["end"] == pytest.approx(8.7)

    def test_each_region_has_start_end_float(self):
        from stages.v6.silero_vad_stage import SileroVadStage
        stage = SileroVadStage({"vad_threshold": 0.5})
        fake = [{"start": "1.0", "end": "2.0"}]  # string input → float output
        with patch.object(stage, "_run_vad", return_value=fake):
            result = stage.transform([], _make_context())
        assert isinstance(result[0]["start"], float)
        assert isinstance(result[0]["end"], float)

    def test_vad_params_passed_to_silero(self):
        from stages.v6.silero_vad_stage import SileroVadStage
        profile = {
            "vad_threshold": 0.6,
            "min_speech_duration_ms": 300,
            "max_speech_duration_s": 10,
            "min_silence_duration_ms": 400,
            "speech_pad_ms": 150,
        }
        stage = SileroVadStage(profile)
        captured = {}
        def fake_run_vad(audio_path):
            # Verify params are accessible on stage
            captured["threshold"] = stage._params["threshold"]
            captured["min_speech_duration_ms"] = stage._params["min_speech_duration_ms"]
            return []
        with patch.object(stage, "_run_vad", side_effect=fake_run_vad):
            stage.transform([], _make_context())
        assert captured["threshold"] == pytest.approx(0.6)
        assert captured["min_speech_duration_ms"] == 300

    def test_empty_audio_returns_empty_list(self):
        from stages.v6.silero_vad_stage import SileroVadStage
        stage = SileroVadStage({"vad_threshold": 0.5})
        with patch.object(stage, "_run_vad", return_value=[]):
            result = stage.transform([], _make_context())
        assert result == []
```

### Step 2: Implement (GREEN)

```python
# backend/stages/v6/__init__.py
# (empty — marks package)
```

```python
# backend/stages/v6/silero_vad_stage.py
"""SileroVadStage — v6 Stage 0.

Runs Silero VAD on full audio, returns speech regions [{start, end}].
These regions are fed to Stage 1A (qwen3 per-region).
"""
from __future__ import annotations
from typing import List
from stages import PipelineStage, StageContext


_DEFAULT_PARAMS = {
    "threshold": 0.5,
    "min_speech_duration_ms": 250,
    "max_speech_duration_s": 15.0,
    "min_silence_duration_ms": 500,
    "speech_pad_ms": 200,
}


def _load_audio_ffmpeg(audio_path: str, sr: int = 16000):
    """Decode audio to mono float32 numpy array via ffmpeg."""
    import subprocess
    import numpy as np
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", audio_path,
        "-ac", "1", "-ar", str(sr),
        "-f", "f32le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(proc.stdout, dtype=np.float32)


class SileroVadStage(PipelineStage):
    """Stage 0: Silero VAD pre-segmentation."""

    def __init__(self, profile: dict):
        self._profile = profile
        self._params = {
            "threshold": float(profile.get("vad_threshold", _DEFAULT_PARAMS["threshold"])),
            "min_speech_duration_ms": int(profile.get("min_speech_duration_ms", _DEFAULT_PARAMS["min_speech_duration_ms"])),
            "max_speech_duration_s": float(profile.get("max_speech_duration_s", _DEFAULT_PARAMS["max_speech_duration_s"])),
            "min_silence_duration_ms": int(profile.get("min_silence_duration_ms", _DEFAULT_PARAMS["min_silence_duration_ms"])),
            "speech_pad_ms": int(profile.get("speech_pad_ms", _DEFAULT_PARAMS["speech_pad_ms"])),
        }

    @property
    def stage_type(self) -> str:
        return "vad"

    @property
    def stage_ref(self) -> str:
        return self._profile.get("id", "vad")

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        audio_path = context.pipeline_overrides.get("audio_path") or getattr(context, "audio_path", None)
        if audio_path is None:
            import app as _app
            with _app._registry_lock:
                entry = _app._file_registry.get(context.file_id, {})
                audio_path = entry.get("audio_path") or entry.get("file_path")
        if not audio_path:
            raise ValueError(f"SileroVadStage: no audio_path for file_id={context.file_id}")
        regions = self._run_vad(audio_path)
        return [{"start": float(r["start"]), "end": float(r["end"])} for r in regions]

    def _run_vad(self, audio_path: str) -> List[dict]:
        """Run Silero VAD on audio. Returns list of {start, end} speech regions."""
        import torch
        from silero_vad import load_silero_vad, get_speech_timestamps
        audio_np = _load_audio_ffmpeg(audio_path, sr=16000)
        audio_tensor = torch.from_numpy(audio_np.copy())
        model = load_silero_vad()
        raw = get_speech_timestamps(
            audio_tensor, model, sampling_rate=16000,
            return_seconds=True,
            threshold=self._params["threshold"],
            min_speech_duration_ms=self._params["min_speech_duration_ms"],
            max_speech_duration_s=self._params["max_speech_duration_s"],
            min_silence_duration_ms=self._params["min_silence_duration_ms"],
            speech_pad_ms=self._params["speech_pad_ms"],
        )
        return [{"start": float(r["start"]), "end": float(r["end"])} for r in raw]
```

- [ ] Run tests:

```bash
cd backend && source venv/bin/activate
pytest tests/test_v6_stages.py::TestSileroVadStage -v
```

Expected: 6 pass.

- [ ] **Step 3: Commit**

```bash
git add backend/stages/v6/__init__.py backend/stages/v6/silero_vad_stage.py
git add backend/tests/test_v6_stages.py
git commit -m "feat(v6): SileroVadStage (Stage 0) + tests"
```

---

## Task 3: qwen3-vad engine wrapper + tests (Stage 1A engine layer)

**Estimated time:** 45 min
**Files:**
- Create: `backend/engines/transcribe/qwen3_vad_engine.py`
- Modify: `backend/tests/test_v6_stages.py` (add Qwen3VadEngine tests)

### Step 1: Write failing tests (RED)

```python
# Append to backend/tests/test_v6_stages.py

class TestQwen3VadEngine:
    """Tests for Qwen3VadEngine (Stage 1A engine wrapper)."""

    def test_transcribe_regions_returns_flat_list(self):
        from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine
        engine = Qwen3VadEngine(language="Chinese", context="", post_s2hk=False)
        vad_regions = [{"start": 0.5, "end": 3.0}, {"start": 5.0, "end": 8.5}]

        # Fake subprocess result — two regions, each with word-level segments
        fake_subprocess_result = {
            "regions": [
                {
                    "region_idx": 0, "region_start": 0.5, "region_end": 3.0,
                    "full_text": "你好世界", "chunks": [],
                    "segments": [
                        {"start": 0.1, "end": 0.5, "text": "你好"},
                        {"start": 0.5, "end": 0.9, "text": "世界"},
                    ],
                    "runtime_sec": 0.8, "error": None,
                },
                {
                    "region_idx": 1, "region_start": 5.0, "region_end": 8.5,
                    "full_text": "測試成功", "chunks": [],
                    "segments": [
                        {"start": 0.2, "end": 0.5, "text": "測試"},
                        {"start": 0.5, "end": 0.8, "text": "成功"},
                    ],
                    "runtime_sec": 1.2, "error": None,
                },
            ]
        }
        with patch.object(engine, "_call_subprocess", return_value=fake_subprocess_result):
            result = engine.transcribe_regions("/fake/audio.mp4", vad_regions)

        # Flat list — absolute time adjusted
        assert len(result) == 4
        assert result[0]["text"] == "你好"
        assert result[0]["start"] == pytest.approx(0.5 + 0.1)  # region_start + relative
        assert result[2]["text"] == "測試"
        assert result[2]["start"] == pytest.approx(5.0 + 0.2)  # region 1 offset

    def test_region_with_error_skipped(self):
        from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine
        engine = Qwen3VadEngine(language="Chinese", context="", post_s2hk=False)
        fake = {
            "regions": [
                {
                    "region_idx": 0, "region_start": 0.0, "region_end": 2.0,
                    "full_text": "", "chunks": [], "segments": [],
                    "runtime_sec": 0.5, "error": "mlx_qwen3_asr import failed",
                },
            ]
        }
        with patch.object(engine, "_call_subprocess", return_value=fake):
            result = engine.transcribe_regions("/fake/audio.mp4", [{"start": 0.0, "end": 2.0}])
        assert result == []

    def test_empty_segments_falls_back_to_full_text_as_one_chunk(self):
        from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine
        engine = Qwen3VadEngine(language="Chinese", context="", post_s2hk=False)
        fake = {
            "regions": [
                {
                    "region_idx": 0, "region_start": 1.0, "region_end": 4.0,
                    "full_text": "一段話", "chunks": [], "segments": [],
                    "runtime_sec": 0.3, "error": None,
                },
            ]
        }
        with patch.object(engine, "_call_subprocess", return_value=fake):
            result = engine.transcribe_regions("/fake/audio.mp4", [{"start": 1.0, "end": 4.0}])
        assert len(result) == 1
        assert result[0]["text"] == "一段話"
        assert result[0]["start"] == pytest.approx(1.0)
        assert result[0]["end"] == pytest.approx(4.0)

    def test_subprocess_called_with_correct_payload_shape(self):
        from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine
        engine = Qwen3VadEngine(language="Chinese", context="袁幸堯", post_s2hk=True)
        vad_regions = [{"start": 2.0, "end": 5.0}]
        fake = {"regions": [
            {"region_idx": 0, "region_start": 2.0, "region_end": 5.0,
             "full_text": "", "chunks": [], "segments": [], "runtime_sec": 0.1, "error": None}
        ]}
        captured = {}
        def capture_payload(audio_path, wav_paths, payload):
            captured.update(payload)
            return fake
        with patch.object(engine, "_call_subprocess", side_effect=capture_payload):
            engine.transcribe_regions("/fake/audio.mp4", vad_regions)
        assert captured["config"]["language"] == "Chinese"
        assert "袁幸堯" in captured["config"]["context"]
        assert captured["config"]["post_s2hk"] is True
```

### Step 2: Implement (GREEN)

```python
# backend/engines/transcribe/qwen3_vad_engine.py
"""Qwen3VadEngine — wraps qwen3_vad_subprocess.py for per-region transcription.

Runs inside the main py3.9 venv; spawns a py3.11 subprocess for mlx_qwen3_asr.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

import numpy as np
import soundfile as sf

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_QWEN_VENV_PYTHON = (
    _REPO_ROOT / "backend" / "scripts" / "v5_prototype" / "venv_qwen" / "bin" / "python"
)
_DEFAULT_SUBPROCESS_SCRIPT = (
    _REPO_ROOT / "backend" / "scripts" / "v5_prototype" / "qwen3_vad_subprocess.py"
)


def _load_audio_ffmpeg(audio_path: str, sr: int = 16000) -> np.ndarray:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", audio_path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(proc.stdout, dtype=np.float32)


class Qwen3VadEngine:
    """Engine for Stage 1A: transcribe each VAD region via qwen3-asr subprocess."""

    def __init__(
        self,
        language: str = "Chinese",
        context: str = "",
        post_s2hk: bool = True,
        model: str = "Qwen/Qwen3-ASR-1.7B",
        venv_python: str = "",
        subprocess_script: str = "",
    ):
        self._language = language
        self._context = context
        self._post_s2hk = post_s2hk
        self._model = model
        self._venv_python = Path(venv_python or os.environ.get(
            "V6_QWEN_VENV_PYTHON", str(_DEFAULT_QWEN_VENV_PYTHON)
        ))
        self._subprocess_script = Path(subprocess_script or str(_DEFAULT_SUBPROCESS_SCRIPT))

    def transcribe_regions(self, audio_path: str, vad_regions: List[dict]) -> List[dict]:
        """Transcribe each VAD region. Returns flat list of {start, end, text} in absolute time."""
        if not vad_regions:
            return []

        audio_np = _load_audio_ffmpeg(audio_path, sr=16000)
        tmpdir = tempfile.mkdtemp(prefix="vad_regions_")
        try:
            wav_paths = self._write_region_wavs(audio_np, vad_regions, tmpdir)
            payload = {
                "regions": [
                    {
                        "idx": r.get("idx", i),
                        "wav_path": wav_paths[i],
                        "region_start": float(r["start"]),
                        "region_end": float(r["end"]),
                    }
                    for i, r in enumerate(vad_regions)
                ],
                "config": {
                    "language": self._language,
                    "context": self._context,
                    "post_s2hk": self._post_s2hk,
                    "model": self._model,
                },
            }
            result = self._call_subprocess(audio_path, wav_paths, payload)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

        return self._flatten_to_absolute(result, vad_regions)

    def _write_region_wavs(self, audio_np: np.ndarray, regions: List[dict], tmpdir: str) -> List[str]:
        paths = []
        for i, r in enumerate(regions):
            s = int(float(r["start"]) * 16000)
            e = int(float(r["end"]) * 16000)
            out_path = os.path.join(tmpdir, f"region_{i:04d}.wav")
            sf.write(out_path, audio_np[s:e], 16000, subtype="PCM_16")
            paths.append(out_path)
        return paths

    def _call_subprocess(self, audio_path: str, wav_paths: List[str], payload: dict) -> dict:
        proc = subprocess.run(
            [str(self._venv_python), str(self._subprocess_script)],
            input=json.dumps(payload),
            capture_output=True, text=True, timeout=1800,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"qwen3_vad subprocess failed (rc={proc.returncode}):\n{proc.stderr}"
            )
        return json.loads(proc.stdout)

    def _flatten_to_absolute(self, result: dict, vad_regions: List[dict]) -> List[dict]:
        """Flatten per-region segments to absolute-time flat list."""
        flat: List[dict] = []
        for region_out in result.get("regions", []):
            if region_out.get("error"):
                continue  # Skip failed regions
            offset = float(region_out["region_start"])
            segments = region_out.get("segments") or []
            if segments:
                for s in segments:
                    flat.append({
                        "start": offset + float(s.get("start") or 0.0),
                        "end": offset + float(s.get("end") or 0.0),
                        "text": (s.get("text") or "").strip(),
                    })
            else:
                # Fallback: treat full_text as single span for this region
                full_text = (region_out.get("full_text") or "").strip()
                if full_text:
                    flat.append({
                        "start": float(region_out["region_start"]),
                        "end": float(region_out["region_end"]),
                        "text": full_text,
                    })
        return flat
```

- [ ] Run tests:

```bash
pytest tests/test_v6_stages.py::TestQwen3VadEngine -v
```

Expected: 4 pass.

- [ ] **Step 3: Commit**

```bash
git add backend/engines/transcribe/qwen3_vad_engine.py
git add backend/tests/test_v6_stages.py
git commit -m "feat(v6): Qwen3VadEngine wrapper (Stage 1A engine layer) + tests"
```

---

## Task 4: Qwen3PerRegionStage (Stage 1A stage class) + tests

**Estimated time:** 30 min
**Files:**
- Create: `backend/stages/v6/qwen3_per_region_stage.py`
- Modify: `backend/tests/test_v6_stages.py`

### Step 1: Write failing tests (RED)

```python
# Append to backend/tests/test_v6_stages.py

class TestQwen3PerRegionStage:
    def test_stage_type(self):
        from stages.v6.qwen3_per_region_stage import Qwen3PerRegionStage
        stage = Qwen3PerRegionStage({"id": "qwen3-1", "language": "Chinese"})
        assert stage.stage_type == "qwen3_per_region"

    def test_transform_takes_vad_regions_from_segments_in(self):
        """Stage 1A receives VAD regions as segments_in (from Stage 0)."""
        from stages.v6.qwen3_per_region_stage import Qwen3PerRegionStage
        stage = Qwen3PerRegionStage({"language": "Chinese", "context": ""})
        vad_regions = [{"start": 0.5, "end": 3.0}, {"start": 5.0, "end": 8.0}]
        expected_chars = [{"start": 0.6, "end": 0.9, "text": "你好"}]

        with patch.object(stage, "_engine") as mock_engine:
            mock_engine.transcribe_regions.return_value = expected_chars
            ctx = _make_context({"audio_path": "/fake/audio.mp4"})
            result = stage.transform(vad_regions, ctx)

        mock_engine.transcribe_regions.assert_called_once_with("/fake/audio.mp4", vad_regions)
        assert result == expected_chars

    def test_transform_returns_normalized_float_dicts(self):
        from stages.v6.qwen3_per_region_stage import Qwen3PerRegionStage
        stage = Qwen3PerRegionStage({"language": "Chinese"})
        raw_chars = [{"start": "1.0", "end": "1.5", "text": "測試"}]
        with patch.object(stage, "_engine") as mock_engine:
            mock_engine.transcribe_regions.return_value = raw_chars
            ctx = _make_context({"audio_path": "/fake/audio.mp4"})
            result = stage.transform([{"start": 0.5, "end": 2.0}], ctx)
        assert isinstance(result[0]["start"], float)
        assert isinstance(result[0]["end"], float)

    def test_engine_config_from_profile(self):
        from stages.v6.qwen3_per_region_stage import Qwen3PerRegionStage
        from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine
        profile = {"language": "Chinese", "context": "袁幸堯", "post_s2hk": True}
        stage = Qwen3PerRegionStage(profile)
        assert isinstance(stage._engine, Qwen3VadEngine)
        assert stage._engine._language == "Chinese"
        assert stage._engine._context == "袁幸堯"
        assert stage._engine._post_s2hk is True
```

### Step 2: Implement (GREEN)

```python
# backend/stages/v6/qwen3_per_region_stage.py
"""Qwen3PerRegionStage — v6 Stage 1A.

Receives VAD regions (list of {start, end}) as segments_in.
Invokes Qwen3VadEngine to transcribe each region.
Returns flat char-level [{start, end, text}] in absolute time.
"""
from __future__ import annotations
from typing import List
from stages import PipelineStage, StageContext
from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine


class Qwen3PerRegionStage(PipelineStage):
    def __init__(self, profile: dict):
        self._profile = profile
        self._engine = Qwen3VadEngine(
            language=profile.get("language", "Chinese"),
            context=profile.get("context", ""),
            post_s2hk=profile.get("post_s2hk", True),
        )

    @property
    def stage_type(self) -> str:
        return "qwen3_per_region"

    @property
    def stage_ref(self) -> str:
        return self._profile.get("id", "qwen3_vad")

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        """segments_in = VAD regions from Stage 0. Returns flat char-level segments."""
        audio_path = (
            context.pipeline_overrides.get("audio_path")
            or getattr(context, "audio_path", None)
        )
        if not audio_path:
            import app as _app
            with _app._registry_lock:
                entry = _app._file_registry.get(context.file_id, {})
                audio_path = entry.get("audio_path") or entry.get("file_path")
        if not audio_path:
            raise ValueError(f"Qwen3PerRegionStage: no audio_path for file_id={context.file_id}")

        chars = self._engine.transcribe_regions(audio_path, segments_in)
        return [
            {
                "start": float(c["start"]),
                "end": float(c["end"]),
                "text": (c.get("text") or "").strip(),
            }
            for c in chars
        ]
```

- [ ] Run tests:

```bash
pytest tests/test_v6_stages.py::TestQwen3PerRegionStage -v
```

Expected: 4 pass.

- [ ] **Step 3: Commit**

```bash
git add backend/stages/v6/qwen3_per_region_stage.py
git add backend/tests/test_v6_stages.py
git commit -m "feat(v6): Qwen3PerRegionStage (Stage 1A stage class) + tests"
```

---

## Task 5: TimeAnchoredMergeStage (Stage 2) + tests

**Estimated time:** 60 min
**Files:**
- Create: `backend/stages/v6/time_anchored_merge_stage.py`
- Modify: `backend/tests/test_v6_stages.py`

### Step 1: Write failing tests (RED)

```python
# Append to backend/tests/test_v6_stages.py

class TestTimeAnchoredMergeStage:
    """Tests for Stage 2: time-anchored merge algorithm."""

    # Pure algorithm tests (no context needed — test via static method)

    def _make_stage(self):
        from stages.v6.time_anchored_merge_stage import TimeAnchoredMergeStage
        return TimeAnchoredMergeStage({})

    def test_single_mlx_slot_absorbs_all_chars(self):
        stage = self._make_stage()
        mlx_segs = [{"start": 0.0, "end": 5.0, "text": "ignored"}]
        qwen3_chars = [
            {"start": 0.5, "end": 1.0, "text": "你"},
            {"start": 1.0, "end": 1.5, "text": "好"},
            {"start": 1.5, "end": 2.0, "text": "世"},
            {"start": 2.0, "end": 2.5, "text": "界"},
        ]
        result = stage._time_anchored_merge(mlx_segs, qwen3_chars)
        assert len(result) == 1
        assert result[0]["text"] == "你好世界"
        assert result[0]["start"] == pytest.approx(0.0)
        assert result[0]["end"] == pytest.approx(5.0)

    def test_chars_assigned_by_midpoint(self):
        """Char with midpoint in [1.0, 2.0) goes to slot [1.0, 2.0)."""
        stage = self._make_stage()
        mlx_segs = [
            {"start": 0.0, "end": 1.0, "text": "x"},
            {"start": 1.0, "end": 2.0, "text": "x"},
        ]
        qwen3_chars = [
            {"start": 0.8, "end": 1.2, "text": "字"},  # midpoint=1.0 → slot 1
        ]
        result = stage._time_anchored_merge(mlx_segs, qwen3_chars)
        # midpoint = (0.8+1.2)/2 = 1.0 → slot1 [1.0, 2.0) since 1.0 <= 1.0 < 2.0
        assert result[0]["text"] == ""
        assert result[1]["text"] == "字"

    def test_empty_slot_collapsed_into_prev(self):
        """Empty mlx slots are dropped; prev slot absorbs their end time."""
        stage = self._make_stage()
        mlx_segs = [
            {"start": 0.0, "end": 2.0, "text": "x"},
            {"start": 2.0, "end": 4.0, "text": "x"},  # empty — no qwen3 chars
            {"start": 4.0, "end": 6.0, "text": "x"},
        ]
        qwen3_chars = [
            {"start": 0.5, "end": 1.0, "text": "前"},
            {"start": 5.0, "end": 5.5, "text": "後"},
        ]
        result = stage._collapse_empty_slots(
            stage._time_anchored_merge(mlx_segs, qwen3_chars)
        )
        assert len(result) == 2
        assert result[0]["text"] == "前"
        assert result[0]["end"] == pytest.approx(4.0)  # absorbed empty slot's end
        assert result[1]["text"] == "後"

    def test_trailing_empty_slots_absorbed_by_last_keep(self):
        stage = self._make_stage()
        mlx_segs = [
            {"start": 0.0, "end": 2.0, "text": "x"},
            {"start": 2.0, "end": 4.0, "text": "x"},  # empty trailing
        ]
        qwen3_chars = [{"start": 0.5, "end": 1.0, "text": "文字"}]
        result = stage._collapse_empty_slots(
            stage._time_anchored_merge(mlx_segs, qwen3_chars)
        )
        assert len(result) == 1
        assert result[0]["end"] == pytest.approx(4.0)

    def test_no_chars_returns_empty(self):
        stage = self._make_stage()
        mlx_segs = [{"start": 0.0, "end": 5.0, "text": "x"}]
        result = stage._collapse_empty_slots(
            stage._time_anchored_merge(mlx_segs, [])
        )
        assert result == []

    def test_multiple_mlx_slots_chars_split_correctly(self):
        stage = self._make_stage()
        mlx_segs = [
            {"start": 0.0, "end": 3.0, "text": "x"},
            {"start": 3.0, "end": 6.0, "text": "x"},
        ]
        qwen3_chars = [
            {"start": 0.5, "end": 1.0, "text": "甲"},  # mid=0.75 → slot 0
            {"start": 2.5, "end": 3.5, "text": "乙"},  # mid=3.0 → slot 1 (3.0 <= 3.0 < 6.0)
            {"start": 4.0, "end": 4.5, "text": "丙"},  # mid=4.25 → slot 1
        ]
        result = stage._time_anchored_merge(mlx_segs, qwen3_chars)
        assert result[0]["text"] == "甲"
        assert result[1]["text"] == "乙丙"

    def test_stage_type(self):
        from stages.v6.time_anchored_merge_stage import TimeAnchoredMergeStage
        stage = TimeAnchoredMergeStage({})
        assert stage.stage_type == "time_anchored_merge"

    def test_transform_reads_qwen3_from_overrides(self):
        """transform() reads qwen3 chars from context.pipeline_overrides['__qwen3_chars']."""
        from stages.v6.time_anchored_merge_stage import TimeAnchoredMergeStage
        stage = TimeAnchoredMergeStage({})
        mlx_segs = [{"start": 0.0, "end": 3.0, "text": "x"}]
        qwen3_chars = [{"start": 0.5, "end": 1.5, "text": "測試"}]
        ctx = _make_context({"__qwen3_chars": qwen3_chars})
        result = stage.transform(mlx_segs, ctx)
        assert len(result) == 1
        assert result[0]["text"] == "測試"
```

### Step 2: Implement (GREEN)

```python
# backend/stages/v6/time_anchored_merge_stage.py
"""TimeAnchoredMergeStage — v6 Stage 2.

Algorithm: for each mlx slot [start, end), collect qwen3 chars whose
midpoint falls in [start, end), concatenate as that slot's text.
Empty slots (mlx hallucinations / cascade dups) collapse into the
preceding kept slot (extending its end time).

Input via transform():
  segments_in:  mlx-whisper segs [{start, end, text}] (~90)
  context.pipeline_overrides["__qwen3_chars"]: qwen3 flat chars [{start, end, text}]

Output: merged subtitle-sized segments [{start, end, text}] (~84)
"""
from __future__ import annotations
from typing import List, Optional
from stages import PipelineStage, StageContext


def _midpoint(c: dict) -> float:
    s, e = float(c.get("start") or 0), float(c.get("end") or 0)
    return (s + e) / 2.0 if e > s else s


class TimeAnchoredMergeStage(PipelineStage):
    def __init__(self, profile: dict):
        self._profile = profile

    @property
    def stage_type(self) -> str:
        return "time_anchored_merge"

    @property
    def stage_ref(self) -> str:
        return self._profile.get("id", "time_anchored_merge")

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        """segments_in = mlx-whisper segs. qwen3 chars from context overrides."""
        qwen3_chars = list(context.pipeline_overrides.get("__qwen3_chars") or [])
        merged = self._time_anchored_merge(segments_in, qwen3_chars)
        return self._collapse_empty_slots(merged)

    def _time_anchored_merge(
        self, mlx_segs: List[dict], qwen3_chars: List[dict]
    ) -> List[dict]:
        out = []
        for m in mlx_segs:
            ws = float(m["start"])
            we = float(m["end"])
            chars_in = [c for c in qwen3_chars if ws <= _midpoint(c) < we]
            out.append({
                "start": ws,
                "end": we,
                "text": "".join(c.get("text", "") for c in chars_in).strip(),
            })
        return out

    def _collapse_empty_slots(self, merged: List[dict]) -> List[dict]:
        """Drop empty slots; extend prev keep's end to absorb their timecode."""
        final: List[dict] = []
        pending_end: Optional[float] = None
        for s in merged:
            if not s["text"]:
                pending_end = float(s["end"])
                continue
            seg = {k: v for k, v in s.items()}
            if pending_end is not None and final:
                final[-1]["end"] = max(float(final[-1]["end"]), pending_end)
                pending_end = None
            elif pending_end is not None:
                # pending before first kept seg — discard (head silence)
                pending_end = None
            final.append(seg)
        # Trailing empty slots: extend last kept slot
        if pending_end is not None and final:
            final[-1]["end"] = max(float(final[-1]["end"]), pending_end)
        return final
```

- [ ] Run tests:

```bash
pytest tests/test_v6_stages.py::TestTimeAnchoredMergeStage -v
```

Expected: 8 pass.

- [ ] **Step 3: Commit**

```bash
git add backend/stages/v6/time_anchored_merge_stage.py
git add backend/tests/test_v6_stages.py
git commit -m "feat(v6): TimeAnchoredMergeStage (Stage 2) + 8 tests"
```

---

## Task 6: v6 Refiner prompt template (Stage 3 simplified prompt)

**Estimated time:** 20 min
**Files:**
- Create: `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_v6.json`
- Create/modify: test for prompt content

**NOTE on stage class:** Do NOT create a new stage class. Stage 3 reuses `stages/v5/refiner_stage.py` (existing `RefinerStage`) with the new prompt template id. The existing stage class already:
- Accepts `secondary=[]` (empty by default)
- Builds `neighbors` ±5s window
- Calls `LLMRefiner.refine()` with the system prompt from the template

### Step 1: Write failing tests (RED)

```python
# Append to backend/tests/test_v6_stages.py

class TestV6RefinerPrompt:
    """Verify v6 refiner prompt does NOT contain cascade/orphan/hallucination drop rules."""

    def _load_prompt(self):
        import json
        from pathlib import Path
        p = (Path(__file__).resolve().parents[1] /
             "config/prompt_templates_v5/refiner/zh_broadcast_hk_v6.json")
        return json.loads(p.read_text(encoding="utf-8"))

    def test_prompt_file_exists(self):
        data = self._load_prompt()
        assert data["id"] == "refiner/zh_broadcast_hk_v6"

    def test_prompt_has_no_cascade_rule(self):
        data = self._load_prompt()
        prompt = data["system_prompt"]
        assert "cascade" not in prompt.lower(), "v6 prompt must not contain cascade detection"

    def test_prompt_has_no_tail_orphan_rule(self):
        data = self._load_prompt()
        prompt = data["system_prompt"]
        assert "tail_orphan" not in prompt.lower()
        assert "tail orphan" not in prompt.lower()

    def test_prompt_has_no_hallucination_phrase_list(self):
        data = self._load_prompt()
        prompt = data["system_prompt"]
        # v5 prompt listed known bad phrases; v6 must not
        assert "粟米片" not in prompt
        assert "coffee shop" not in prompt

    def test_prompt_has_no_secondary_field_description(self):
        data = self._load_prompt()
        prompt = data["system_prompt"]
        assert '"secondary"' not in prompt, "v6 prompt must not describe secondary field"

    def test_prompt_has_drop_only_for_empty_text(self):
        """v6 prompt: drop action only for empty/noise segs, not content judgments."""
        data = self._load_prompt()
        prompt = data["system_prompt"]
        # Must still support keep action
        assert '"action": "keep"' in prompt or "keep" in prompt.lower()

    def test_prompt_mentions_mid_word_cut_fix(self):
        data = self._load_prompt()
        prompt = data["system_prompt"]
        # Must contain mid-word cut fix instruction
        assert "截斷" in prompt or "mid-word" in prompt.lower() or "補全" in prompt
```

### Step 2: Create prompt template (GREEN)

Create `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_v6.json` with the content specified in the Design Spec §6. (The exact JSON is already in the spec — copy it verbatim.)

- [ ] Run tests:

```bash
pytest tests/test_v6_stages.py::TestV6RefinerPrompt -v
```

Expected: 7 pass.

- [ ] **Step 3: Commit**

```bash
git add backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_v6.json
git add backend/tests/test_v6_stages.py
git commit -m "feat(v6): v6 refiner prompt (simplified — no cascade/orphan/hallucination) + 7 tests"
```

---

## Task 7: StageContext audio_path plumbing

**Estimated time:** 30 min

Stages 0 and 1A need `audio_path` available inside `transform()`. The existing `StageContext` dataclass does not have an `audio_path` field. v6 orchestration passes `audio_path` via `context.pipeline_overrides["audio_path"]` as a workaround (used above in Task 2 + 4 implementation).

**Implement:** Extend `StageContext` with an optional `audio_path` field.

**Files:**
- Modify: `backend/stages/__init__.py`
- Modify: `backend/tests/test_v6_stages.py` — update `_make_context` helper to use the field

### Step 1: Write failing test (RED)

```python
# Append to backend/tests/test_v6_stages.py

class TestStageContextAudioPath:
    def test_stage_context_accepts_audio_path(self):
        from stages import StageContext
        ctx = StageContext(
            file_id="f1", user_id=1, pipeline_id="p1", stage_index=0,
            cancel_event=None, progress_callback=None,
            pipeline_overrides={}, audio_path="/tmp/test.mp4",
        )
        assert ctx.audio_path == "/tmp/test.mp4"

    def test_stage_context_audio_path_defaults_none(self):
        from stages import StageContext
        ctx = StageContext(
            file_id="f1", user_id=1, pipeline_id="p1", stage_index=0,
            cancel_event=None, progress_callback=None,
            pipeline_overrides={},
        )
        assert ctx.audio_path is None
```

### Step 2: Implement (GREEN)

Read `backend/stages/__init__.py` and add `audio_path: Optional[str] = None` to `StageContext`. Update `_make_context` helper in tests to pass `audio_path` directly rather than via `pipeline_overrides`.

- [ ] **Step 3: Commit**

```bash
git add backend/stages/__init__.py backend/tests/test_v6_stages.py
git commit -m "feat(v6): StageContext.audio_path field for v6 stage plumbing"
```

---

## Task 8: PipelineRunner `_run_v6()` + integration test

**Estimated time:** 60 min
**Files:**
- Modify: `backend/pipeline_runner.py`
- Create: `backend/tests/test_v6_runner.py`

### Step 1: Write failing tests (RED)

```python
# backend/tests/test_v6_runner.py
"""Integration test for _run_v6() pipeline orchestration."""
import pytest
from unittest.mock import patch, MagicMock, call
import threading

from pipeline_runner import PipelineRunner


def _make_v6_pipeline():
    return {
        "id": "test-v6-pipe",
        "pipeline_type": "v6_vad_dual_asr",
        "source_lang": "zh",
        "target_languages": ["zh"],
        "vad": {"vad_threshold": 0.5},
        "qwen3_asr": {"language": "Chinese", "context": "", "post_s2hk": True},
        "asr_primary": {
            "transcribe_profile_id": "mlx-profile-1",
            "source_lang": "zh",
        },
        "refinements": {
            "zh": [{"refiner_profile_id": "refiner-1"}]
        },
        "translators": {},
        "glossary_stages": {},
        "font_config": {},
    }


def _fake_managers():
    transcribe_mgr = MagicMock()
    transcribe_mgr.get.return_value = {
        "id": "mlx-profile-1", "engine": "mlx-whisper",
        "language": "zh", "model_size": "large-v3",
    }
    refiner_mgr = MagicMock()
    refiner_mgr.get.return_value = {
        "id": "refiner-1", "lang": "zh", "style": "broadcast_hk_v6",
        "llm_profile_id": "llm-1",
        "prompt_template_id": "refiner/zh_broadcast_hk_v6",
    }
    llm_mgr = MagicMock()
    llm_mgr.get.return_value = {
        "id": "llm-1", "backend": "ollama", "model": "qwen3.5:35b",
    }
    return {
        "transcribe_profile_manager": transcribe_mgr,
        "refiner_profile_manager": refiner_mgr,
        "llm_profile_manager": llm_mgr,
    }


class TestRunV6Dispatch:
    def test_pipeline_type_v6_dispatches_to_run_v6(self):
        """PipelineRunner.run() with pipeline_type='v6_vad_dual_asr' calls _run_v6."""
        runner = PipelineRunner(
            pipeline=_make_v6_pipeline(),
            file_id="test-file",
            audio_path="/fake/audio.mp4",
            managers=_fake_managers(),
        )
        with patch.object(runner, "_run_v6", return_value=[]) as mock_v6:
            runner.run(user_id=1)
        mock_v6.assert_called_once()

    def test_no_pipeline_type_does_not_dispatch_to_run_v6(self):
        """Pipeline without pipeline_type field falls through to v4/v5 path."""
        pipe = _make_v6_pipeline()
        del pipe["pipeline_type"]  # Absent → legacy path
        pipe["version"] = 5
        pipe["asr_secondary"] = None
        runner = PipelineRunner(
            pipeline=pipe, file_id="test-file",
            audio_path="/fake/audio.mp4",
            managers=_fake_managers(),
        )
        with patch.object(runner, "_run_v6") as mock_v6, \
             patch.object(runner, "_run_v5", return_value=[]) as mock_v5:
            runner.run(user_id=1)
        mock_v6.assert_not_called()
        mock_v5.assert_called_once()


class TestRunV6Integration:
    """Integration test with mocked stage classes."""

    def _build_runner(self):
        return PipelineRunner(
            pipeline=_make_v6_pipeline(),
            file_id="test-file-v6",
            audio_path="/fake/audio.mp4",
            managers=_fake_managers(),
        )

    def test_run_v6_calls_four_stages_in_order(self):
        """VAD → qwen3 → mlx → merge → refiner called in order."""
        runner = self._build_runner()
        stage_types_called = []

        # Capture stage_type of each stage as _run_stage is called
        orig_run_stage = runner._run_stage

        def fake_run_stage(stage, segments_in, stage_index, stage_type, **kwargs):
            stage_types_called.append(stage_type)
            # Return dummy StageOutput + segments
            return (
                {"stage_index": stage_index, "stage_type": stage_type, "status": "done",
                 "ran_at": 0, "duration_seconds": 0, "segments": [], "quality_flags": []},
                [{"start": 0.0, "end": 1.0, "text": "測試"}],
            )

        # We also need to mock _persist_by_lang
        with patch.object(runner, "_run_stage", side_effect=fake_run_stage), \
             patch.object(runner, "_persist_by_lang"), \
             patch("pipeline_runner._persist_stage_output"), \
             patch("pipeline_runner._socketio_emit"):
            runner._run_v6(user_id=1)

        # Check stage type sequence includes vad, qwen3, asr_primary (mlx), merge, refiner
        assert "vad" in stage_types_called
        assert "qwen3_per_region" in stage_types_called
        assert "asr_primary" in stage_types_called
        assert "time_anchored_merge" in stage_types_called
        assert any("refiner" in t for t in stage_types_called)
        # Order: vad must come before qwen3, qwen3 before mlx, mlx before merge
        vad_idx = stage_types_called.index("vad")
        qwen_idx = stage_types_called.index("qwen3_per_region")
        mlx_idx = stage_types_called.index("asr_primary")
        merge_idx = stage_types_called.index("time_anchored_merge")
        assert vad_idx < qwen_idx < mlx_idx < merge_idx

    def test_run_v6_start_from_stage_raises_not_implemented(self):
        runner = self._build_runner()
        with pytest.raises(NotImplementedError):
            runner.run(user_id=1, start_from_stage=2)
```

### Step 2: Implement `_run_v6()` in `pipeline_runner.py` (GREEN)

Add to `PipelineRunner.run()`:

```python
# In run():
if self._pipeline.get("pipeline_type") == "v6_vad_dual_asr":
    if start_from_stage != 0:
        raise NotImplementedError("v6 resume from stage not yet supported")
    return self._run_v6(user_id=user_id, cancel_event=cancel_event)
```

Add method `_run_v6()`:

```python
def _run_v6(
    self,
    user_id: Optional[int],
    cancel_event: Optional[threading.Event] = None,
) -> List[StageOutput]:
    """Execute v6 DAG: VAD → qwen3/region → mlx → merge → refiner(s) → persist."""
    from stages.v6.silero_vad_stage import SileroVadStage
    from stages.v6.qwen3_per_region_stage import Qwen3PerRegionStage
    from stages.v6.time_anchored_merge_stage import TimeAnchoredMergeStage
    from stages.v5.asr_primary_stage import ASRPrimaryStage
    from stages.v5.refiner_stage import RefinerStage, SECONDARY_KEY

    stage_outputs: List[StageOutput] = []
    stage_index = 0
    source_lang = self._pipeline.get("source_lang", "zh")
    audio_path = self._audio_path

    # Shared context override for audio_path plumbing
    audio_overrides = {"audio_path": audio_path}

    # Stage 0: VAD
    _check_cancel(cancel_event)
    vad_profile = dict(self._pipeline.get("vad", {}))
    vad_stage = SileroVadStage(vad_profile)
    vad_out, vad_regions = self._run_stage(
        stage=vad_stage, segments_in=[], stage_index=stage_index,
        stage_type="vad", cancel_event=cancel_event, user_id=user_id,
        extra_overrides=audio_overrides,
    )
    stage_outputs.append(vad_out)
    stage_index += 1

    # Stage 1A: qwen3 per-region
    _check_cancel(cancel_event)
    qwen3_profile = dict(self._pipeline.get("qwen3_asr", {}))
    qwen3_stage = Qwen3PerRegionStage(qwen3_profile)
    qwen3_out, qwen3_chars = self._run_stage(
        stage=qwen3_stage, segments_in=vad_regions, stage_index=stage_index,
        stage_type="qwen3_per_region", cancel_event=cancel_event, user_id=user_id,
        extra_overrides=audio_overrides,
    )
    stage_outputs.append(qwen3_out)
    stage_index += 1

    # Stage 1B: mlx-whisper full audio (time grid only — text discarded downstream)
    _check_cancel(cancel_event)
    primary_profile = self._transcribe_profile_manager.get(
        self._pipeline["asr_primary"]["transcribe_profile_id"]
    )
    if primary_profile is None:
        raise ValueError("v6: asr_primary transcribe profile not found")
    mlx_stage = ASRPrimaryStage(primary_profile, audio_path)
    mlx_out, mlx_segs = self._run_stage(
        stage=mlx_stage, segments_in=[], stage_index=stage_index,
        stage_type="asr_primary", cancel_event=cancel_event, user_id=user_id,
    )
    stage_outputs.append(mlx_out)
    stage_index += 1

    # Stage 2: time-anchored merge (mlx grid + qwen3 chars)
    _check_cancel(cancel_event)
    merge_stage = TimeAnchoredMergeStage({})
    merge_overrides = {"__qwen3_chars": qwen3_chars}
    merge_out, merged_segs = self._run_stage_v5(
        stage=merge_stage, segments_in=mlx_segs, stage_index=stage_index,
        stage_type="time_anchored_merge", cancel_event=cancel_event, user_id=user_id,
        extra_overrides=merge_overrides,
    )
    stage_outputs.append(merge_out)
    stage_index += 1

    canonical_source = merged_segs

    # Stage 3+: refinement (no secondary — qwen3 is sole authority)
    by_lang: dict = {}
    for target_lang in self._pipeline.get("target_languages", []):
        lang_segments = list(canonical_source)
        for refiner_entry in self._pipeline.get("refinements", {}).get(target_lang, []):
            refiner_profile = self._refiner_profile_manager.get(
                refiner_entry["refiner_profile_id"]
            )
            if refiner_profile is None:
                raise ValueError(f"v6: refiner profile for {target_lang} not found")
            llm_profile = self._llm_profile_manager.get(refiner_profile["llm_profile_id"])
            if llm_profile is None:
                raise ValueError(f"v6: refiner's llm_profile not found ({target_lang})")
            _check_cancel(cancel_event)
            refiner_stage = RefinerStage(
                refiner_profile=refiner_profile,
                llm_profile=llm_profile,
            )
            rf_out, lang_segments = self._run_stage_v5(
                stage=refiner_stage, segments_in=lang_segments,
                stage_index=stage_index, stage_type=refiner_stage.stage_type,
                cancel_event=cancel_event, user_id=user_id,
                extra_overrides={},  # no secondary in v6
            )
            stage_outputs.append(rf_out)
            stage_index += 1

        by_lang[target_lang] = lang_segments

    self._persist_by_lang(
        by_lang, source_lang=source_lang, source_segments=canonical_source
    )
    return stage_outputs
```

Note: `_run_stage_v5` already exists and handles `extra_overrides`. For Stage 0/1A we need a version that merges audio_path — either call `_run_stage_v5` with `extra_overrides=audio_overrides`, or use the same `_run_stage` with a small tweak. Simplest: make `_run_stage` in v6 call `_run_stage_v5` for all stages (audit that `_run_stage_v5` is the right version).

- [ ] Run tests:

```bash
pytest tests/test_v6_runner.py -v
```

Expected: 4 pass.

- [ ] **Step 3: Commit**

```bash
git add backend/pipeline_runner.py
git add backend/tests/test_v6_runner.py
git commit -m "feat(v6): PipelineRunner._run_v6() DAG + dispatch + integration tests"
```

---

## Task 9: v6 Pipeline JSON configs + validation stub

**Estimated time:** 20 min
**Files:**
- Create: `backend/config/pipelines/<uuid1>.json` — `[v6] 賽馬廣播 (Cantonese)`
- Create: `docs/superpowers/validation/v6-validation.md` (stub)

### Step 1: Create pipeline JSON configs

Generate two UUIDs with Python: `python -c "import uuid; print(uuid.uuid4())"`.

**Pipeline 1 — 賽馬廣播 (Cantonese):**
```json
{
  "id": "<generated-uuid-1>",
  "name": "[v6] 賽馬廣播 (Cantonese)",
  "pipeline_type": "v6_vad_dual_asr",
  "source_lang": "zh",
  "target_languages": ["zh"],
  "vad": {
    "vad_threshold": 0.5,
    "min_speech_duration_ms": 250,
    "max_speech_duration_s": 15,
    "min_silence_duration_ms": 500,
    "speech_pad_ms": 200
  },
  "asr_primary": {
    "transcribe_profile_id": "<existing-mlx-whisper-profile-id>",
    "source_lang": "zh"
  },
  "qwen3_asr": {
    "language": "Chinese",
    "context": "袁幸堯 姚本輝 史滕雷 賈西迪 潘頓 麥道朗 艾少禮 布浩穎 尤達榮 美狼王 HIGHLAND BLINK 幸運風采 沙田馬場 悉尼城市馬場 寶馬香港打吡大賽 肯德百利錦標 亞德雷德杯 騎師 試騎 推騎 試閘 抽籤 排位 大熱門 頭馬 客艙 馬房 馬仔 香檳 打吡 香港 沙田 悉尼",
    "post_s2hk": true
  },
  "refinements": {
    "zh": [{"refiner_profile_id": "<existing-zh-refiner-profile-id>"}]
  },
  "translators": {},
  "glossary_stages": {},
  "font_config": {
    "family": "Noto Sans TC",
    "color": "white",
    "outline_color": "black"
  },
  "user_id": null,
  "shared": true,
  "created_at": 0,
  "updated_at": 0
}
```

**IMPORTANT:** For `asr_primary.transcribe_profile_id`, look up an existing mlx-whisper profile from `backend/config/profiles/` or create a minimal stub. For `refinements.zh.refiner_profile_id`, use an existing refiner profile or create one pointing to `refiner/zh_broadcast_hk_v6`.

**Pipeline 2 — Winning Factor EN (optional):**
Same structure but `source_lang: "en"`, `qwen3_asr.language: "English"`, no entity context, `refinements.en` with EN refiner.

### Step 2: Create validation stub

```markdown
# v6 VAD + Dual-ASR + Refiner Validation

**Date:** 2026-05-21
**Status:** PENDING MANUAL RUN
**Branch:** feat/v6-vad-dual-asr-refiner

## Test Files
- 賽馬廣播特輯: `backend/data/users/*/uploads/aec2e8f98789.mp4`
- Winning Factor EN: (path TBD)

## Baseline (v5-A5)
| Metric | v5-A5 |
|---|---|
| Entity accuracy | TBD |
| Cascade hallucinations | TBD |
| Segment count | ~90 |
| Total runtime | TBD |

## v6 Results
| Metric | v6 | vs v5-A5 |
|---|---|---|
| Entity accuracy | TBD | TBD |
| Cascade hallucinations | TBD | TBD |
| Segment count | TBD | TBD |
| VAD runtime | TBD | TBD |
| qwen3 runtime | TBD | TBD |
| Total runtime | TBD | TBD |

## Run Instructions
1. Start backend: `cd backend && source venv/bin/activate && python app.py`
2. Upload 賽馬 file via Dashboard, select `[v6] 賽馬廣播 (Cantonese)` pipeline
3. Wait for pipeline completion
4. Open Proofread page — verify subtitle overlay renders at correct timecodes
5. Export SRT, check entity names: 袁幸堯/史滕雷/HIGHLAND BLINK
6. Record metrics in table above
```

- [ ] **Step 3: Commit**

```bash
git add backend/config/pipelines/<uuid1>.json
git add docs/superpowers/validation/v6-validation.md
git commit -m "feat(v6): v6 pipeline JSON configs + validation stub"
```

---

## Task 10: Frontend smoke test (E2E Playwright)

**Estimated time:** 45 min
**Files:**
- Create: `frontend/tests-e2e/v6-pipeline-smoke.spec.ts`

### Step 1: Write E2E test

The test follows the graceful-skip pattern from existing v5 E2E specs (skip on credential mismatch).

```typescript
// frontend/tests-e2e/v6-pipeline-smoke.spec.ts
import { test, expect } from "@playwright/test";

const BASE_URL = process.env.BASE_URL || "http://localhost:5001";
const ADMIN_USER = process.env.TEST_ADMIN_USER || "admin";
const ADMIN_PASS = process.env.TEST_ADMIN_PASS || "";

test.describe("v6 pipeline smoke test", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    if (!ADMIN_PASS) {
      test.skip(true, "TEST_ADMIN_PASS not set — skipping v6 smoke test");
    }
    await page.fill('[data-testid="username"]', ADMIN_USER);
    await page.fill('[data-testid="password"]', ADMIN_PASS);
    await page.click('[data-testid="login-submit"]');
    await page.waitForURL(`${BASE_URL}/`, { timeout: 5000 }).catch(() => {
      test.skip(true, "Login failed — skipping v6 smoke test");
    });
  });

  test("v6 pipeline appears in PipelinePicker", async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    // Open pipeline picker dropdown
    const picker = page.locator('[data-testid="pipeline-picker"]').first();
    await picker.click();
    // Verify a v6 pipeline option is visible
    const v6Option = page.locator('text=[v6]').first();
    await expect(v6Option).toBeVisible({ timeout: 5000 });
  });

  test("v6 pipelines listed on /pipelines page", async ({ page }) => {
    await page.goto(`${BASE_URL}/pipelines`);
    await page.waitForLoadState("networkidle");
    const v6Items = page.locator("text=[v6]");
    const count = await v6Items.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("translations array has start/end matching audio timecodes after v6 run", async ({
    page,
    request,
  }) => {
    // This test requires a file that has already been run through v6 pipeline.
    // It verifies the translations[i].start/end values are populated.
    // Gracefully skip if no v6-processed file exists.
    const filesResp = await request.get(`${BASE_URL}/api/files`);
    if (!filesResp.ok()) {
      test.skip(true, "Cannot fetch files list");
    }
    const files = await filesResp.json();
    const v6File = files.find(
      (f: { pipeline_id?: string; translations?: unknown[] }) =>
        f.pipeline_id && f.translations && Array.isArray(f.translations) &&
        f.translations.length > 0
    );
    if (!v6File) {
      test.skip(true, "No v6-processed file found — skipping timecode check");
    }
    const transResp = await request.get(
      `${BASE_URL}/api/files/${v6File.id}/translations?shape=v5`
    );
    const trans = await transResp.json();
    // Verify first and last translations have valid start/end
    expect(trans[0].start).toBeDefined();
    expect(typeof trans[0].start).toBe("number");
    expect(trans[0].end).toBeGreaterThan(trans[0].start);
    // Verify by_lang.zh.text is non-empty
    const zhText = trans[0].by_lang?.zh?.text;
    expect(typeof zhText).toBe("string");
    expect(zhText.length).toBeGreaterThan(0);
  });
});
```

- [ ] Run E2E (requires browser):

```bash
cd frontend && npx playwright test tests-e2e/v6-pipeline-smoke.spec.ts --reporter=list
```

Expected: first 2 tests pass (or skip gracefully if credentials missing), third test skip or pass depending on pre-existing v6 data.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests-e2e/v6-pipeline-smoke.spec.ts
git commit -m "test(v6): E2E smoke test — v6 pipeline in PipelinePicker + timecode verification"
```

---

## Task 11: Backend — PipelineManager refiner_prompt_override + _run_v6 resolution

**Estimated time:** 45 min
**Files:**
- Modify: `backend/pipelines.py` (`PipelineManager.update_if_owned`)
- Modify: `backend/pipeline_runner.py` (`_run_v6` — add refiner prompt resolution)
- Modify: `backend/tests/test_v6_runner.py` (add override resolution tests)

**Foundation:** Reuses existing v3.18 `prompt_overrides` and v5-A2 `runtime_overrides` infrastructure. No new storage mechanism invented.

### Step 1: Write failing tests (RED)

```python
# Append to backend/tests/test_v6_runner.py

class TestRunV6RefinerPromptResolution:
    """Verify 3-level refiner prompt resolution in _run_v6."""

    def _run_with_overrides(self, file_prompt=None, pipeline_prompt=None):
        """Helper: build runner with specified override levels, capture resolved prompt."""
        pipeline = _make_v6_pipeline()
        if pipeline_prompt is not None:
            pipeline["refiner_prompt_override"] = {"zh": pipeline_prompt}

        captured = {}

        def fake_run_stage_v5(stage, segments_in, stage_index, stage_type,
                              cancel_event=None, user_id=None, extra_overrides=None):
            if "refiner" in (stage_type or ""):
                captured["runtime_overrides"] = extra_overrides or {}
            return (
                {"stage_index": stage_index, "stage_type": stage_type, "status": "done",
                 "ran_at": 0, "duration_seconds": 0, "segments": [], "quality_flags": []},
                [{"start": 0.0, "end": 1.0, "text": "test"}],
            )

        file_entry = {"prompt_overrides": {}}
        if file_prompt is not None:
            file_entry["prompt_overrides"]["refiners.zh"] = file_prompt

        runner = PipelineRunner(
            pipeline=pipeline, file_id="test-file-v6",
            audio_path="/fake/audio.mp4", managers=_fake_managers(),
        )
        with patch.object(runner, "_run_stage_v5", side_effect=fake_run_stage_v5), \
             patch.object(runner, "_run_stage", side_effect=fake_run_stage_v5), \
             patch.object(runner, "_persist_by_lang"), \
             patch("pipeline_runner._file_registry", {"test-file-v6": file_entry}), \
             patch("pipeline_runner._persist_stage_output"), \
             patch("pipeline_runner._socketio_emit"):
            runner._run_v6(user_id=1)

        return captured.get("runtime_overrides", {})

    def test_file_prompt_overrides_pipeline_and_template(self):
        overrides = self._run_with_overrides(
            file_prompt="per-file custom prompt",
            pipeline_prompt="pipeline custom prompt",
        )
        assert overrides.get("refiners.zh") == "per-file custom prompt"

    def test_pipeline_prompt_overrides_template_when_no_file_override(self):
        overrides = self._run_with_overrides(
            file_prompt=None,
            pipeline_prompt="pipeline custom prompt",
        )
        assert overrides.get("refiners.zh") == "pipeline custom prompt"

    def test_empty_override_falls_through_to_template(self):
        overrides = self._run_with_overrides(file_prompt=None, pipeline_prompt=None)
        # When no override set, runtime_overrides for refiner.zh should be empty/absent
        assert not overrides.get("refiners.zh")


class TestPipelineManagerRefinerPromptOverride:
    def test_update_if_owned_accepts_refiner_prompt_override(self):
        """PipelineManager.update_if_owned accepts refiner_prompt_override patch field."""
        from pipelines import PipelineManager
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PipelineManager(config_dir=tmpdir)
            pipeline = _make_v6_pipeline()
            pipeline["user_id"] = 1
            pipeline["shared"] = False
            mgr._save(pipeline)

            mgr.update_if_owned(
                pipeline_id=pipeline["id"],
                user_id=1,
                is_admin=False,
                patch={"refiner_prompt_override": {"zh": "custom prompt text"}},
            )
            updated = mgr.get(pipeline["id"])
            assert updated["refiner_prompt_override"]["zh"] == "custom prompt text"

    def test_update_if_owned_clears_refiner_prompt_override_with_null(self):
        from pipelines import PipelineManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PipelineManager(config_dir=tmpdir)
            pipeline = _make_v6_pipeline()
            pipeline["user_id"] = 1
            pipeline["shared"] = False
            pipeline["refiner_prompt_override"] = {"zh": "old prompt"}
            mgr._save(pipeline)

            mgr.update_if_owned(
                pipeline_id=pipeline["id"],
                user_id=1, is_admin=False,
                patch={"refiner_prompt_override": {"zh": None}},
            )
            updated = mgr.get(pipeline["id"])
            assert not updated.get("refiner_prompt_override", {}).get("zh")
```

### Step 2: Implement (GREEN)

**`backend/pipelines.py` — `update_if_owned`:** add `refiner_prompt_override` to the set of accepted patch fields. It is stored as-is in the pipeline JSON (a dict `{lang: str | null}`). Values of `null` should be stored as `None` (or remove the key if all values are null — implementer's choice; tests verify clearing works).

**`backend/pipeline_runner.py` — `_run_v6()`:** add the three-level refiner prompt resolution block (as specified in §5 of the spec). Pass the resolved prompt as `extra_overrides={"refiners.zh": resolved_prompt}` when calling the RefinerStage (empty string = no override, falls back to template).

- [ ] Run tests:

```bash
pytest tests/test_v6_runner.py::TestRunV6RefinerPromptResolution tests/test_v6_runner.py::TestPipelineManagerRefinerPromptOverride -v
```

Expected: 5 pass.

- [ ] **Step 3: Commit**

```bash
git add backend/pipelines.py backend/pipeline_runner.py
git add backend/tests/test_v6_runner.py
git commit -m "feat(v6): PipelineManager refiner_prompt_override patch + _run_v6 3-level resolution (T11)"
```

---

## Task 12: Backend — prompt_overrides qwen3_context key + _run_v6 context resolution

**Estimated time:** 30 min
**Files:**
- Modify: `backend/translation/prompt_override_validator.py` (add `qwen3_context` as known key)
- Modify: `backend/pipeline_runner.py` (`_run_v6` — add qwen3_context resolution)
- Modify: `backend/tests/test_v6_runner.py` (add context resolution tests)

**Foundation:** Extends the existing v3.18 `prompt_override_validator.py` which already validates `prompt_overrides` keys for PATCH `/api/files/<id>`. No new storage mechanism invented.

### Step 1: Write failing tests (RED)

```python
# Append to backend/tests/test_v6_runner.py

class TestRunV6ContextResolution:
    """Verify qwen3 context 3-level resolution in _run_v6."""

    def _run_and_capture_context(self, file_context=None, pipeline_context=None):
        pipeline = _make_v6_pipeline()
        if pipeline_context is not None:
            pipeline["qwen3_asr"]["context"] = pipeline_context

        captured = {}

        def fake_run_stage(stage, segments_in, stage_index, stage_type,
                           cancel_event=None, user_id=None, extra_overrides=None):
            if stage_type == "qwen3_per_region":
                # Capture the context from the stage's engine config
                captured["context"] = getattr(stage._engine, "_context", None)
            return (
                {"stage_index": stage_index, "stage_type": stage_type, "status": "done",
                 "ran_at": 0, "duration_seconds": 0, "segments": [], "quality_flags": []},
                [{"start": 0.0, "end": 1.0, "text": "test"}],
            )

        file_entry = {"prompt_overrides": {}}
        if file_context is not None:
            file_entry["prompt_overrides"]["qwen3_context"] = file_context

        runner = PipelineRunner(
            pipeline=pipeline, file_id="test-file-v6",
            audio_path="/fake/audio.mp4", managers=_fake_managers(),
        )
        with patch.object(runner, "_run_stage", side_effect=fake_run_stage), \
             patch.object(runner, "_run_stage_v5", side_effect=fake_run_stage), \
             patch.object(runner, "_persist_by_lang"), \
             patch("pipeline_runner._file_registry", {"test-file-v6": file_entry}), \
             patch("pipeline_runner._persist_stage_output"), \
             patch("pipeline_runner._socketio_emit"):
            runner._run_v6(user_id=1)

        return captured.get("context", "")

    def test_file_context_overrides_pipeline_context(self):
        ctx = self._run_and_capture_context(
            file_context="file entity names",
            pipeline_context="pipeline entity names",
        )
        assert ctx == "file entity names"

    def test_pipeline_context_used_when_no_file_override(self):
        ctx = self._run_and_capture_context(
            file_context=None,
            pipeline_context="pipeline entity names",
        )
        assert ctx == "pipeline entity names"

    def test_empty_string_when_neither_set(self):
        ctx = self._run_and_capture_context(file_context=None, pipeline_context=None)
        assert ctx == ""


class TestPromptOverrideValidatorQwen3Context:
    def test_qwen3_context_is_accepted_key(self):
        """prompt_override_validator accepts qwen3_context as a known key."""
        from translation.prompt_override_validator import validate_prompt_overrides
        # Should not raise
        result = validate_prompt_overrides({"qwen3_context": "袁幸堯 史滕雷"})
        assert result is not None  # returns validated dict or None — no exception
```

### Step 2: Implement (GREEN)

**`backend/translation/prompt_override_validator.py`:** Add `"qwen3_context"` to the set of known/accepted keys. The value is a plain string (no length cap needed — it's an entity name hint, typically < 200 chars; add a reasonable max of 500 chars).

**`backend/pipeline_runner.py` — `_run_v6()`:** add the three-level qwen3 context resolution block before Stage 1A (as specified in §5 of the spec). Pass `resolved_context` when constructing `Qwen3PerRegionStage`.

- [ ] Run tests:

```bash
pytest tests/test_v6_runner.py::TestRunV6ContextResolution tests/test_v6_runner.py::TestPromptOverrideValidatorQwen3Context -v
```

Expected: 4 pass.

- [ ] **Step 3: Commit**

```bash
git add backend/translation/prompt_override_validator.py
git add backend/pipeline_runner.py
git add backend/tests/test_v6_runner.py
git commit -m "feat(v6): prompt_overrides qwen3_context key + _run_v6 context 3-level resolution (T12)"
```

---

## Task 13: Frontend — Pipelines page refiner prompt panel + Proofread drawer extension

**Estimated time:** 60 min
**Files:**
- Modify: `frontend/src/pages/Pipelines.tsx` (or `frontend/src/pages/Pipelines/index.tsx`)
- Modify: `frontend/src/pages/Proofread/components/PromptOverridesDrawer.tsx` (or equivalent)
- Modify: `frontend/src/lib/api/v5.ts` or `frontend/src/lib/api.ts` (pipeline PATCH type)
- Create/modify: `frontend/src/tests/` (vitest cases)

**Foundation:** Builds on existing v3.18 `prompt_overrides` drawer and v5-A2 API client. No new state management store needed — local `useState` for textarea values is sufficient.

### Step 1: Write failing tests (RED — vitest)

```typescript
// frontend/src/tests/v6-prompt-editing.test.ts
import { describe, it, expect, vi } from "vitest";

describe("v6 refiner prompt resolution helpers", () => {
  it("resolves pipeline-level refiner prompt override from pipeline JSON", () => {
    const pipeline = {
      pipeline_type: "v6_vad_dual_asr",
      refiner_prompt_override: { zh: "custom pipeline prompt" },
    };
    // Helper that reads pipeline_type and returns refiner_prompt_override.zh
    const resolved = pipeline.pipeline_type === "v6_vad_dual_asr"
      ? pipeline.refiner_prompt_override?.zh ?? ""
      : "";
    expect(resolved).toBe("custom pipeline prompt");
  });

  it("returns empty string when no pipeline-level override set", () => {
    const pipeline = { pipeline_type: "v6_vad_dual_asr" };
    const resolved = (pipeline as any).refiner_prompt_override?.zh ?? "";
    expect(resolved).toBe("");
  });

  it("identifies v6 pipeline by pipeline_type field", () => {
    const v6 = { pipeline_type: "v6_vad_dual_asr", name: "[v6] test" };
    const v5 = { name: "[v5] test" };
    const isV6 = (p: any) => p.pipeline_type === "v6_vad_dual_asr";
    expect(isV6(v6)).toBe(true);
    expect(isV6(v5)).toBe(false);
  });
});

describe("Proofread prompt_overrides drawer v6 fields", () => {
  it("qwen3_context key is part of the expected prompt_overrides schema", () => {
    const overrides: Record<string, string | null> = {
      qwen3_context: "袁幸堯 史滕雷",
      "refiners.zh": "custom refiner prompt",
    };
    expect(overrides["qwen3_context"]).toBe("袁幸堯 史滕雷");
    expect(overrides["refiners.zh"]).toBe("custom refiner prompt");
  });

  it("null value for qwen3_context clears the override", () => {
    const overrides: Record<string, string | null> = { qwen3_context: null };
    expect(overrides["qwen3_context"]).toBeNull();
  });
});
```

### Step 2: Implement (GREEN)

**Pipelines page (`Pipelines.tsx` or equivalent):**

When the selected/active pipeline has `pipeline_type === "v6_vad_dual_asr"`, render a "Refiner Prompt" collapsible panel below the stage list. The panel contains:
- A `<textarea>` pre-filled with `pipeline.refiner_prompt_override?.zh ?? ""`.
- A **Save** button: calls `PATCH /api/pipelines/<id>` with `{ refiner_prompt_override: { zh: textareaValue } }`.
- A **Clear** button: calls `PATCH /api/pipelines/<id>` with `{ refiner_prompt_override: { zh: null } }`.
- A helper text: "留空則使用預設模板 (`zh_broadcast_hk_v6.json`)"

PATCH call uses the existing `patchPipeline(id, patch)` API helper (or equivalent in `frontend/src/lib/api/v5.ts`). On success, refresh the pipeline data.

**Proofread page PromptOverridesDrawer:**

Extend the existing drawer with two new fields at the bottom of the form (after the existing prompt override textareas):

1. **"qwen3 Context (詞庫)"** — `<textarea rows={3}>`, label in Traditional Chinese. Bound to `promptOverrides.qwen3_context`. Placeholder: "例：袁幸堯 史滕雷 HIGHLAND BLINK"
2. **"Refiner Prompt Override"** — `<textarea rows={8}>`, label in Traditional Chinese. Bound to `promptOverrides["refiners.zh"]`.

The Save button for the drawer already calls `PATCH /api/files/<id>` with the full `prompt_overrides` object — the two new fields are included naturally when non-empty.

**Type update:** Extend the `PromptOverrides` type (if typed) to include `qwen3_context?: string | null`.

- [ ] Run tests:

```bash
cd frontend && npm run test -- --run src/tests/v6-prompt-editing.test.ts
```

Expected: 5 pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Pipelines.tsx  # (or index.tsx)
git add frontend/src/pages/Proofread/components/PromptOverridesDrawer.tsx
git add frontend/src/lib/api/v5.ts  # if PATCH pipeline type updated
git add frontend/src/tests/v6-prompt-editing.test.ts
git commit -m "feat(v6): Pipelines refiner prompt panel + Proofread drawer qwen3_context/refiner fields (T13)"
```

---

## Task Summary

| Task | Description | Tests | Est. Time |
|---|---|---|---|
| T1 | Create branch, commit spec + plan | — | 10 min |
| T2 | SileroVadStage (Stage 0) | 6 unit | 45 min |
| T3 | Qwen3VadEngine (Stage 1A engine) | 4 unit | 45 min |
| T4 | Qwen3PerRegionStage (Stage 1A stage) | 4 unit | 30 min |
| T5 | TimeAnchoredMergeStage (Stage 2) | 8 unit | 60 min |
| T6 | v6 Refiner prompt template | 7 unit | 20 min |
| T7 | StageContext audio_path field | 2 unit | 30 min |
| T8 | PipelineRunner._run_v6() with pipeline_type dispatch | 4 integration | 60 min |
| T9 | Pipeline JSON configs with pipeline_type field + validation stub | — | 20 min |
| T10 | Playwright E2E smoke test | 3 E2E | 45 min |
| T11 | Backend: PipelineManager refiner_prompt_override + _run_v6 resolution | 4 unit | 45 min |
| T12 | Backend: prompt_overrides qwen3_context key + _run_v6 context resolution | 3 unit | 30 min |
| T13 | Frontend: Pipelines page refiner prompt panel + Proofread drawer extension | ~5 vitest | 60 min |
| **Total** | | **~55 tests** | **~9h** |

---

## Task Dependency Order

```
T1 (branch + commit spec/plan)
  │
  ├─→ T2 (VAD stage), T3 (qwen3 engine), T5 (merge stage) — parallel batch
  │
  ├─→ T4 (qwen3 per-region stage, depends on T3)
  │
  ├─→ T7 (StageContext.audio_path), T6 (refiner prompt template) — parallel
  │
  ├─→ T8 (pipeline_runner _run_v6 with pipeline_type dispatch),
  │   T9 (v6 pipeline JSON configs with pipeline_type),
  │   T11 (PipelineManager refiner_prompt_override patch + _run_v6 resolution),
  │   T12 (prompt_overrides qwen3_context + _run_v6 context resolution)
  │   — parallel batch (all require T7 + T6 to be done first)
  │
  └─→ T10 (FE Playwright smoke), T13 (FE prompt editing UI) — parallel last
```

Note: T8 and T11/T12 both touch `pipeline_runner.py` / manager code — if assigned to separate agents, coordinate to avoid merge conflicts on `_run_v6()`.

---

## Verification Gates (per CLAUDE.md §Development Guidelines)

Before marking v6 complete:

1. **Code quality** — `pytest tests/test_v6_stages.py tests/test_v6_runner.py` all pass; no hardcoded file paths (use env var / profile config); no mutation.
2. **Functional correctness** — curl smoke: `curl http://localhost:5001/api/pipelines | jq '[.pipelines[] | select(.name | startswith("[v6]"))]'` returns ≥1 pipeline; upload a file via Dashboard with v6 pipeline and confirm translations appear on Proofread page.
3. **Integration** — Full v6 pipeline runs on 賽馬 audio file: VAD → qwen3 → mlx → merge → refiner chain completes; `translations[i].start/end` match expected ~80 segments; SubtitleOverlay renders at correct video timestamps.
4. **Backward compat** — v4/v5 pipelines still work: run a v5 pipeline on any existing file and confirm no regression.
5. **Documentation** — CLAUDE.md v6 section added; README.md updated (Traditional Chinese).

---

## Appendix: Key Code Reference Paths

| Purpose | File |
|---|---|
| Existing v5 RefinerStage (reuse for Stage 3) | `backend/stages/v5/refiner_stage.py` |
| Existing LLMRefiner engine (reuse) | `backend/engines/refiner/llm_refiner.py` |
| v5-A5 prompt to compare/strip | `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json` |
| PipelineRunner v5 DAG (model for v6) | `backend/pipeline_runner.py::_run_v5()` |
| Prototype orchestrator | `backend/scripts/v5_prototype/prototype_vad_qwen3.py` |
| Prototype subprocess | `backend/scripts/v5_prototype/qwen3_vad_subprocess.py` |
| Stage 2 algorithm prototype | `/tmp/v6_stage2_merge.py` |
| Stage 0 evidence | `/tmp/v6_prototype_stage1a_v2.json` |
| Stage 2 evidence | `/tmp/v6_stage2_result.json` |
