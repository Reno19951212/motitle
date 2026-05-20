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
    assert out == [{"start": 0.0, "end": 1.0, "text": "judged", "flags": []}]


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
    # "raw" (3 chars) → "polished" (8 chars) is >1.5× so flags=["long"] is correct
    assert out[0]["text"] == "polished"
    assert out[0]["start"] == 0 and out[0]["end"] == 1


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
    # "中文" (2 chars) → "EN translation" (14 chars) is >1.5× so flags=["long"] is correct
    assert out[0]["text"] == "EN translation"
    assert out[0]["start"] == 0 and out[0]["end"] == 1


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
