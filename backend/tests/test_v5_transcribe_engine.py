def test_transcribe_engine_alias_to_asr_engine():
    """TranscribeEngine is alias for v4 ASREngine ABC (re-export)."""
    from engines.transcribe import TranscribeEngine
    from asr import ASREngine
    assert TranscribeEngine is ASREngine


def test_transcribe_factory_whisper_creates_v4_engine():
    """Factory dispatches `engine: 'whisper'` profile to v4 ASR factory."""
    from engines.transcribe import create_transcribe_engine
    profile = {"engine": "whisper", "model_size": "large-v3", "language": "en"}
    engine = create_transcribe_engine(profile)
    assert engine is not None
    from asr import ASREngine
    assert isinstance(engine, ASREngine)


def test_transcribe_factory_mlx_whisper():
    """Factory dispatches `engine: 'mlx-whisper'` profile to v4 ASR factory."""
    from engines.transcribe import create_transcribe_engine
    profile = {"engine": "mlx-whisper", "model_size": "large-v3", "language": "zh"}
    engine = create_transcribe_engine(profile)
    assert engine is not None


def test_qwen3_asr_wrapper_resolves_subprocess_python():
    from engines.transcribe.qwen3_asr import Qwen3AsrTranscribeEngine
    eng = Qwen3AsrTranscribeEngine({
        "engine": "qwen3-asr", "model_size": "1.7B", "language": "zh",
    })
    # Default subprocess Python path resolves under venv_qwen if it exists,
    # else falls back to "python3.11"
    assert "python" in eng.subprocess_python


def test_qwen3_asr_runs_subprocess(monkeypatch, tmp_path):
    """Use a fake subprocess.run to simulate Qwen3 output."""
    from engines.transcribe.qwen3_asr import Qwen3AsrTranscribeEngine
    import subprocess
    fake_output = (
        '{"language": "Cantonese", "full_text": "hello", '
        '"words": [{"start": 0, "end": 1, "text": "hello"}], '
        '"chunks": [{"start": 0, "end": 1, "text": "hello chunk"}]}'
    )
    def fake_run(*args, **kw):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=fake_output, stderr="")
    monkeypatch.setattr("subprocess.run", fake_run)
    eng = Qwen3AsrTranscribeEngine({"engine": "qwen3-asr", "language": "zh"})
    audio = tmp_path / "fake.wav"
    audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")  # minimal stub
    segments = eng.transcribe(str(audio), source_lang="zh")
    # Chunks have priority over words for segment boundaries
    assert len(segments) == 1
    assert segments[0]["text"] == "hello chunk"


def test_qwen3_asr_falls_back_to_words_when_no_chunks(monkeypatch, tmp_path):
    """If chunks empty, falls back to word-level segments."""
    from engines.transcribe.qwen3_asr import Qwen3AsrTranscribeEngine
    import subprocess
    fake_output = (
        '{"language": "Cantonese", "full_text": "hello", '
        '"words": [{"start": 0, "end": 1, "text": "hello"}], '
        '"chunks": []}'
    )
    def fake_run(*args, **kw):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=fake_output, stderr="")
    monkeypatch.setattr("subprocess.run", fake_run)
    eng = Qwen3AsrTranscribeEngine({"engine": "qwen3-asr", "language": "zh"})
    audio = tmp_path / "fake.wav"
    audio.write_bytes(b"RIFF")
    segments = eng.transcribe(str(audio), source_lang="zh")
    assert len(segments) == 1
    assert segments[0]["text"] == "hello"


def test_qwen3_asr_raises_on_subprocess_failure(monkeypatch, tmp_path):
    from engines.transcribe.qwen3_asr import Qwen3AsrTranscribeEngine
    import subprocess
    def fake_run(*args, **kw):
        return subprocess.CompletedProcess(args=args, returncode=2, stdout="", stderr="mlx_qwen3_asr not found")
    monkeypatch.setattr("subprocess.run", fake_run)
    eng = Qwen3AsrTranscribeEngine({"engine": "qwen3-asr", "language": "zh"})
    audio = tmp_path / "fake.wav"
    audio.write_bytes(b"RIFF")
    import pytest
    with pytest.raises(RuntimeError, match="Qwen3-ASR subprocess failed"):
        eng.transcribe(str(audio), source_lang="zh")


def test_qwen3_asr_language_mapping():
    """source_lang code → Qwen3 language name mapping."""
    from engines.transcribe.qwen3_asr import Qwen3AsrTranscribeEngine, _qwen3_language_name
    assert _qwen3_language_name("zh") == "Cantonese"
    assert _qwen3_language_name("yue") == "Cantonese"
    assert _qwen3_language_name("en") == "English"
    assert _qwen3_language_name("ja") == "Japanese"
    assert _qwen3_language_name("ko") == "Korean"
    # Unknown falls back to Cantonese (the prototype use case)
    assert _qwen3_language_name("klingon") == "Cantonese"
