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
