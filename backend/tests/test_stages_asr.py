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


def test_no_low_logprob_when_all_confident(monkeypatch):
    mock_engine = MagicMock()
    mock_engine.transcribe.return_value = [
        {"start": 0, "end": 1, "text": "ok", "avg_logprob": -0.3},
    ]
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: mock_engine)
    stage = ASRStage(_profile(), audio_path="/tmp/x.wav")
    stage.transform([], _ctx())
    assert "low_logprob" not in stage.quality_flags


def test_no_quality_flag_when_engine_omits_logprob(monkeypatch):
    mock_engine = MagicMock()
    mock_engine.transcribe.return_value = [{"start": 0, "end": 1, "text": "ok"}]
    monkeypatch.setattr("stages.asr_stage.create_asr_engine", lambda cfg: mock_engine)
    stage = ASRStage(_profile(), audio_path="/tmp/x.wav")
    stage.transform([], _ctx())
    assert stage.quality_flags == []
