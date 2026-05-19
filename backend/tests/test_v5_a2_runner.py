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


import threading
from pathlib import Path


def test_run_v5_zh_only_pipeline(tmp_path, monkeypatch):
    """ZH source + ZH-only target with one refiner. No translator, no secondary."""
    from pipeline_runner import PipelineRunner

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

    assert len(outputs) == 2
    assert outputs[0]["stage_type"] == "asr_primary"
    assert outputs[1]["stage_type"] == "refiner:zh"
    entry = _app._file_registry["f1"]
    assert "translations" in entry
    assert entry["translations"][0]["by_lang"]["zh"]["text"] == "polished1"
    assert entry["translations"][1]["by_lang"]["zh"]["text"] == "polished2"


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
    assert entry["translations"][0]["by_lang"]["zh"]["text"] == "中文"
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
