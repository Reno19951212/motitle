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


from unittest.mock import patch, MagicMock
import json as json_mod


def test_ollama_build_system_prompt_formal():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="formal", glossary=[])
    assert "繁體中文書面語" in prompt
    assert "粵語" not in prompt


def test_ollama_build_system_prompt_cantonese():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="cantonese", glossary=[])
    assert "粵語" in prompt


def test_ollama_build_system_prompt_with_glossary():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    glossary = [
        {"en": "Legislative Council", "zh": "立法會"},
        {"en": "Chief Executive", "zh": "行政長官"},
    ]
    prompt = engine._build_system_prompt(style="formal", glossary=glossary)
    assert "Legislative Council" in prompt
    assert "立法會" in prompt
    assert "Chief Executive" in prompt


def test_ollama_build_user_message():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    msg = engine._build_user_message(SAMPLE_SEGMENTS)
    assert "1. Good evening everyone." in msg
    assert "2. Welcome to the news." in msg


def test_ollama_parse_response_numbered():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    response_text = "1. 各位晚上好。\n2. 歡迎收看新聞。"
    result = engine._parse_response(response_text, SAMPLE_SEGMENTS)
    assert len(result) == 2
    assert result[0]["zh_text"] == "各位晚上好。"
    assert result[0]["en_text"] == "Good evening everyone."
    assert result[0]["start"] == 0.0
    assert result[1]["zh_text"] == "歡迎收看新聞。"


def test_ollama_parse_response_fallback_lines():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    response_text = "各位晚上好。\n歡迎收看新聞。"
    result = engine._parse_response(response_text, SAMPLE_SEGMENTS)
    assert len(result) == 2
    assert result[0]["zh_text"] == "各位晚上好。"


def test_ollama_translate_mocked_http():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    mock_response_body = json_mod.dumps({
        "message": {"content": "1. 各位晚上好。\n2. 歡迎收看新聞。"}
    }).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response_body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")

    assert len(result) == 2
    assert result[0]["zh_text"] == "各位晚上好。"
    assert result[0]["en_text"] == "Good evening everyone."
    assert result[0]["start"] == 0.0
    assert result[1]["zh_text"] == "歡迎收看新聞。"
