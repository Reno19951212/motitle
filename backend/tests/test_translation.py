import pytest

SAMPLE_SEGMENTS = [
    {"start": 0.0, "end": 2.5, "text": "Good evening everyone."},
    {"start": 2.5, "end": 5.0, "text": "Welcome to the news."},
]

def test_create_mock_engine():
    from translation import create_translation_engine
    config = {"engine": "mock"}
    engine = create_translation_engine(config)
    assert engine is not None
    info = engine.get_info()
    assert info["engine"] == "mock"
    assert info["available"] is True

def test_mock_translate():
    from translation import create_translation_engine
    engine = create_translation_engine({"engine": "mock"})
    result = engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")
    assert len(result) == 2
    assert result[0]["en_text"] == "Good evening everyone."
    assert result[0]["zh_text"] == "[EN→ZH] Good evening everyone."
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 2.5
    assert result[1]["en_text"] == "Welcome to the news."

def test_mock_translate_cantonese_style():
    from translation import create_translation_engine
    engine = create_translation_engine({"engine": "mock"})
    result = engine.translate(SAMPLE_SEGMENTS, glossary=[], style="cantonese")
    assert len(result) == 2
    assert "[EN→ZH]" in result[0]["zh_text"]

def test_mock_translate_empty_segments():
    from translation import create_translation_engine
    engine = create_translation_engine({"engine": "mock"})
    result = engine.translate([], glossary=[], style="formal")
    assert result == []

def test_create_ollama_engine():
    from translation import create_translation_engine
    config = {"engine": "qwen2.5-3b", "temperature": 0.1}
    engine = create_translation_engine(config)
    assert engine is not None
    info = engine.get_info()
    assert info["engine"] == "qwen2.5-3b"

def test_create_unknown_engine_raises():
    from translation import create_translation_engine
    with pytest.raises(ValueError, match="Unknown translation engine"):
        create_translation_engine({"engine": "nonexistent"})

def test_factory_routes_all_qwen_engines():
    from translation import create_translation_engine
    for engine_name in ["qwen2.5-3b", "qwen2.5-7b", "qwen2.5-72b", "qwen3-235b"]:
        engine = create_translation_engine({"engine": engine_name})
        assert engine.get_info()["engine"] == engine_name
