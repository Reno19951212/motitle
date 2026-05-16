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
