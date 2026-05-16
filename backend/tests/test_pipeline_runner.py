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
    # MT0 receives ASR output directly; MT1 receives MT0's output (sequential chaining)
    assert "polish:" in fake_calls[0]       # MT0 user_msg uses "polish:" template prefix
    assert fake_calls[1].startswith("broadcast: MT(")  # MT1 input = MT0's return value


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


def test_persist_stage_output_writes_to_registry(monkeypatch):
    """_persist_stage_output writes to _file_registry under file.stage_outputs[idx]."""
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


# === T7 Fail-fast ===

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
    # MT0 succeeds, MT1 raises
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
    monkeypatch.setattr("pipeline_runner._socketio_emit", MagicMock())

    runner = PipelineRunner(pipeline, file_id="f1", audio_path="/tmp/x.wav", managers=managers)
    with pytest.raises(RuntimeError, match="Ollama down"):
        runner.run(user_id=1)

    statuses = [p["status"] for p in persisted]
    assert "done" in statuses  # ASR + MT0
    assert "failed" in statuses  # MT1 failed


# === T8 Progress events ===

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
    assert "pipeline_stage_start" in events
    assert "pipeline_stage_done" in events
    progress_events = [e for e in emitted if e[0] == "pipeline_stage_progress"]
    # 20 segments at 5% interval = ~20 progress emits per MT stage
    assert len(progress_events) >= 10


# === T9 cancel_event ===

def test_runner_cancel_during_mt_stage(monkeypatch):
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
        transcribe=lambda *a, **kw: [{"start": 0, "end": 1, "text": "ok"},
                                      {"start": 1, "end": 2, "text": "ok2"}]))

    cancel_event = threading.Event()
    # MT0 sets cancel on first segment
    call_count = {"n": 0}
    def fake_qwen(sys_p, usr_p, temp):
        call_count["n"] += 1
        if call_count["n"] >= 1:
            cancel_event.set()
        return "translated"
    monkeypatch.setattr("stages.mt_stage._call_qwen", fake_qwen)
    monkeypatch.setattr("pipeline_runner._persist_stage_output", MagicMock())
    monkeypatch.setattr("pipeline_runner._socketio_emit", MagicMock())

    runner = PipelineRunner(pipeline, file_id="f1", audio_path="/tmp/x.wav", managers=managers)
    with pytest.raises(JobCancelled):
        runner.run(user_id=1, cancel_event=cancel_event)


# === T10 Resume path ===

def test_runner_resumes_from_start_from_stage(monkeypatch):
    """run(start_from_stage=1) skips ASR + reads segments from stage_outputs[0]."""
    import app as app_mod

    pipeline = _pipeline(mt_count=1, glossary_enabled=False)
    managers = _managers()

    # Inject stage_outputs[0] (simulating ASR already done from prior run)
    prior_segments = [
        {"start": 0, "end": 1, "text": "prior_asr_1"},
        {"start": 1, "end": 2, "text": "prior_asr_2"},
    ]
    registry = {
        "f-resume": {
            "id": "f-resume",
            "file_path": "/tmp/x.wav",
            "user_id": 1,
            "stage_outputs": {
                "0": {
                    "stage_index": 0,
                    "stage_type": "asr",
                    "stage_ref": "asr-uuid",
                    "status": "done",
                    "ran_at": 1.0,
                    "duration_seconds": 0.5,
                    "segments": prior_segments,
                    "quality_flags": [],
                },
            },
        },
    }
    monkeypatch.setattr(app_mod, "_file_registry", registry)
    monkeypatch.setattr(app_mod, "_save_registry", lambda: None)

    # Mock ASR engine — should NOT be called when start_from_stage > 0
    asr_engine_mock = MagicMock()
    asr_engine_mock.transcribe = MagicMock(return_value=[])
    monkeypatch.setattr("stages.asr_stage.create_asr_engine",
                        lambda cfg: asr_engine_mock)

    # Mock MT — should receive prior ASR segments
    received_mt_inputs = []
    def fake_qwen(sys_p, usr_p, temp):
        received_mt_inputs.append(usr_p)
        return f"MT({usr_p})"
    monkeypatch.setattr("stages.mt_stage._call_qwen", fake_qwen)
    monkeypatch.setattr("pipeline_runner._socketio_emit", MagicMock())
    monkeypatch.setattr("pipeline_runner._persist_stage_output", MagicMock())

    runner = PipelineRunner(pipeline, file_id="f-resume", audio_path="/tmp/x.wav", managers=managers)
    outputs = runner.run(user_id=1, start_from_stage=1)

    # ASR engine should NOT have been called
    asr_engine_mock.transcribe.assert_not_called()

    # MT should have received prior_asr_1 + prior_asr_2 via user_message
    assert len(received_mt_inputs) == 2
    assert "prior_asr_1" in received_mt_inputs[0]
    assert "prior_asr_2" in received_mt_inputs[1]

    # Only MT stage should appear in outputs (ASR skipped)
    assert len(outputs) == 1
    assert outputs[0]["stage_type"] == "mt"
    assert outputs[0]["stage_index"] == 1
    # Verify MT received the prior segments and produced output
    assert len(outputs[0]["segments"]) == 2
