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
    def fake_qwen(s, u, t):
        captured["sys"] = s
        captured["usr"] = u
        return "x"
    monkeypatch.setattr("stages.mt_stage._call_qwen", fake_qwen)
    profile = _profile()
    profile["system_prompt"] = "DEFAULT"
    stage = MTStage(profile)
    ctx = StageContext(file_id="f1", user_id=1, pipeline_id="p1",
                       stage_index=1, cancel_event=None, progress_callback=None,
                       pipeline_overrides={})
    stage.transform([{"start": 0, "end": 1, "text": "a"}], ctx)
    assert captured["sys"] == "DEFAULT"
