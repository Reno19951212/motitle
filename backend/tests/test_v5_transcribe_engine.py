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
