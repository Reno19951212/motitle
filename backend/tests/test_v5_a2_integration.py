"""v5-A2 integration: build pipeline + 5 profiles + mock engines + run end-to-end."""
import threading
import pytest
from pathlib import Path
from unittest.mock import Mock, patch


def test_v5_full_dual_asr_pipeline_end_to_end(tmp_path, monkeypatch):
    """Real managers + real schema validation + mocked engines."""
    from llm_profiles import LLMProfileManager
    from transcribe_profiles import TranscribeProfileManager
    from translator_profiles import TranslatorProfileManager
    from refiner_profiles import RefinerProfileManager
    from verifier_profiles import VerifierProfileManager
    from pipelines import PipelineManager
    from pipeline_runner import PipelineRunner
    from translations_normalize_v5 import normalize_translations_for_v5

    base = tmp_path / "config"
    llm_mgr = LLMProfileManager(base / "llm")
    tp_mgr = TranscribeProfileManager(base / "transcribe")
    xl_mgr = TranslatorProfileManager(base / "translator")
    rf_mgr = RefinerProfileManager(base / "refiner")
    vf_mgr = VerifierProfileManager(base / "verifier")
    pl_mgr = PipelineManager(base / "pipeline")

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

    audio = tmp_path / "fake.wav"
    audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    import app as _app
    monkeypatch.setattr(_app, "_file_registry", {"f1": {"id": "f1", "user_id": 1}}, raising=False)
    monkeypatch.setattr(_app, "_registry_lock", threading.Lock(), raising=False)
    monkeypatch.setattr(_app, "_save_registry", lambda: None, raising=False)

    fake_transcribe = Mock()
    fake_transcribe.transcribe.return_value = [
        {"start": 0.0, "end": 1.0, "text": "段一"},
        {"start": 1.0, "end": 2.0, "text": "段二"},
    ]
    fake_llm = Mock()
    fake_llm.call.side_effect = [
        "refined1", "refined2",
        "EN one", "EN two",
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

    types = [o["stage_type"] for o in outputs]
    assert "asr_primary" in types
    assert "refiner:zh" in types
    assert "translator:zh_to_en" in types

    entry = _app._file_registry["f1"]
    translations = entry["translations"]
    assert len(translations) == 2
    assert translations[0]["by_lang"]["zh"]["text"] == "refined1"
    assert translations[0]["by_lang"]["en"]["text"] == "EN one"
    assert translations[1]["by_lang"]["zh"]["text"] == "refined2"
    assert translations[1]["by_lang"]["en"]["text"] == "EN two"

    normalized = normalize_translations_for_v5(translations)
    assert normalized == translations
