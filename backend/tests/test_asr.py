import pytest


def test_create_whisper_engine():
    from asr import create_asr_engine
    config = {"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"}
    engine = create_asr_engine(config)
    assert engine is not None
    info = engine.get_info()
    assert info["engine"] == "whisper"


def test_create_qwen3_engine():
    from asr import create_asr_engine
    config = {"engine": "qwen3-asr", "model_size": "large", "language": "en", "device": "cuda"}
    engine = create_asr_engine(config)
    info = engine.get_info()
    assert info["engine"] == "qwen3-asr"
    assert info["available"] is False


def test_create_flg_engine():
    from asr import create_asr_engine
    config = {"engine": "flg-asr", "model_size": "large", "language": "en", "device": "cuda"}
    engine = create_asr_engine(config)
    info = engine.get_info()
    assert info["engine"] == "flg-asr"
    assert info["available"] is False


def test_create_unknown_engine_raises():
    from asr import create_asr_engine
    with pytest.raises(ValueError, match="Unknown ASR engine"):
        create_asr_engine({"engine": "nonexistent"})


def test_stub_transcribe_raises():
    from asr import create_asr_engine
    engine = create_asr_engine({"engine": "qwen3-asr", "model_size": "large", "language": "en"})
    with pytest.raises(NotImplementedError):
        engine.transcribe("/tmp/test.wav", language="en")


def test_flg_stub_transcribe_raises():
    from asr import create_asr_engine
    engine = create_asr_engine({"engine": "flg-asr", "model_size": "large", "language": "en"})
    with pytest.raises(NotImplementedError):
        engine.transcribe("/tmp/test.wav", language="en")
