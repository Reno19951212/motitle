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


def test_ollama_thinking_model_detection():
    """qwen3/qwen3.5 models are detected as thinking models; qwen2.5 is not."""
    from translation.ollama_engine import OllamaTranslationEngine
    assert OllamaTranslationEngine({"engine": "qwen3-235b"})._is_thinking_model() is True
    assert OllamaTranslationEngine({"engine": "qwen3.5-9b"})._is_thinking_model() is True
    assert OllamaTranslationEngine({"engine": "qwen2.5-3b"})._is_thinking_model() is False
    assert OllamaTranslationEngine({"engine": "qwen2.5-7b"})._is_thinking_model() is False


def test_ollama_thinking_model_sets_think_false():
    """think:false is included in payload for qwen3/qwen3.5 models."""
    import json as json_mod
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen3.5-9b"})
    mock_response = json_mod.dumps({"message": {"content": "1. 恭喜。\n2. 謝謝。"}}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json_mod.loads(req.data)
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")

    assert captured["body"].get("think") is False


def test_ollama_non_thinking_model_no_think_key():
    """think key is absent for qwen2.5 models."""
    import json as json_mod
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    mock_response = json_mod.dumps({"message": {"content": "1. 各位晚上好。\n2. 歡迎收看新聞。"}}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json_mod.loads(req.data)
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")

    assert "think" not in captured["body"]


def test_ollama_translate_mocked_ndjson():
    """Ollama returns NDJSON streaming chunks despite stream:False — content is accumulated."""
    import json as json_mod
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    # Simulate NDJSON: two streaming chunks + final done marker
    ndjson_body = (
        json_mod.dumps({"message": {"role": "assistant", "content": "1. 各位晚上好。\n"}}) + "\n" +
        json_mod.dumps({"message": {"role": "assistant", "content": "2. 歡迎收看新聞。"}}) + "\n" +
        json_mod.dumps({"done": True, "message": {"role": "assistant", "content": ""}})
    ).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = ndjson_body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")

    assert len(result) == 2
    assert result[0]["zh_text"] == "各位晚上好。"
    assert result[1]["zh_text"] == "歡迎收看新聞。"


def test_api_list_translation_engines():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/translation/engines")
        assert resp.status_code == 200
        data = resp.get_json()
        engines = data["engines"]
        assert len(engines) >= 2

        engine_names = [e["engine"] for e in engines]
        assert "mock" in engine_names

        mock_info = next(e for e in engines if e["engine"] == "mock")
        assert mock_info["available"] is True


def test_mock_engine_params_schema():
    from translation import create_translation_engine
    engine = create_translation_engine({"engine": "mock"})
    schema = engine.get_params_schema()
    assert schema["engine"] == "mock"
    assert "style" in schema["params"]
    assert schema["params"]["style"]["enum"] == ["formal", "cantonese"]


def test_mock_engine_get_models():
    from translation import create_translation_engine
    engine = create_translation_engine({"engine": "mock"})
    models = engine.get_models()
    assert len(models) == 1
    assert models[0]["engine"] == "mock"
    assert models[0]["available"] is True


def test_ollama_engine_params_schema():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    schema = engine.get_params_schema()
    assert schema["engine"] == "qwen2.5-3b"
    assert "model" in schema["params"]
    assert "temperature" in schema["params"]
    assert "batch_size" in schema["params"]
    assert "style" in schema["params"]
    assert schema["params"]["temperature"]["type"] == "number"
    assert schema["params"]["batch_size"]["type"] == "integer"


def test_ollama_engine_get_models_mocked():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    mock_response_body = json_mod.dumps({
        "models": [{"name": "qwen2.5:3b"}, {"name": "qwen2.5:7b"}]
    }).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response_body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        models = engine.get_models()

    assert len(models) == 5  # all ENGINE_TO_MODEL entries
    available_models = [m for m in models if m["available"]]
    assert len(available_models) == 2  # qwen2.5:3b and qwen2.5:7b
    unavailable_models = [m for m in models if not m["available"]]
    assert len(unavailable_models) == 3


def test_api_translation_engine_params_mock():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/translation/engines/mock/params")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["engine"] == "mock"
        assert "params" in data


def test_api_translation_engine_params_ollama():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/translation/engines/qwen2.5-3b/params")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["engine"] == "qwen2.5-3b"
        assert "model" in data["params"]
        assert "temperature" in data["params"]


def test_api_translation_engine_params_unknown():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/translation/engines/nonexistent/params")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data


def test_api_translation_engine_models_mock():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/translation/engines/mock/models")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["engine"] == "mock"
        assert len(data["models"]) == 1


def test_api_translation_engine_models_unknown():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/translation/engines/nonexistent/models")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data


def test_system_prompt_formal_forbids_simplified():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="formal", glossary=[])
    assert "NEVER use Simplified Chinese" in prompt or "Traditional Chinese ONLY" in prompt


def test_system_prompt_formal_has_char_limit():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="formal", glossary=[])
    assert "16" in prompt


def test_system_prompt_formal_has_rthk_context():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="formal", glossary=[])
    assert "RTHK" in prompt


def test_system_prompt_cantonese_forbids_simplified():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="cantonese", glossary=[])
    assert "NEVER use Simplified Chinese" in prompt or "Traditional Chinese ONLY" in prompt


def test_system_prompt_cantonese_has_char_limit():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="cantonese", glossary=[])
    assert "16" in prompt


# ── Task 7: Sliding Window Context ───────────────────────────────────────────


def test_sliding_window_context_in_user_message():
    """After first batch, context appears in user message for next batch."""
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b", "context_window": 2})
    context_pairs = [("Hello.", "你好。"), ("Good morning.", "早安。")]
    segments = [{"text": "How are you?", "start": 0, "end": 1}]

    msg = engine._build_user_message(segments, context_pairs=context_pairs)

    assert "[Context" in msg
    assert "Hello." in msg
    assert "[Translate the following:" in msg
    assert "How are you?" in msg


def test_sliding_window_zero_disables_context():
    """context_window=0 means no context block even if pairs are provided."""
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b", "context_window": 0})
    context_pairs = [("Hello.", "你好。")]
    segments = [{"text": "Good morning.", "start": 0, "end": 1}]

    msg = engine._build_user_message(segments, context_pairs=context_pairs)

    assert "[Context" not in msg


def test_sliding_window_trims_to_window_size():
    """Rolling list is trimmed to last context_window pairs."""
    import json as json_mod
    from unittest.mock import patch, MagicMock, call
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b", "context_window": 1})

    # Mock _call_ollama to return predictable numbered response
    with patch.object(engine, "_call_ollama", return_value="1. 測試翻譯。"):
        captured_context = {}
        original_build = engine._build_user_message

        def capturing_build(segments, context_pairs=None):
            captured_context["last_context"] = list(context_pairs) if context_pairs else []
            return original_build(segments, context_pairs=context_pairs)

        with patch.object(engine, "_build_user_message", side_effect=capturing_build):
            engine.translate(
                [
                    {"text": "First.", "start": 0, "end": 1},
                    {"text": "Second.", "start": 1, "end": 2},
                ],
                batch_size=1,
            )

    # The second batch call should have received only 1 context pair (window=1)
    assert len(captured_context["last_context"]) == 1
    assert captured_context["last_context"][0][0] == "First."


def test_context_window_in_params_schema():
    """context_window appears in get_params_schema() output."""
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    schema = engine.get_params_schema()

    assert "context_window" in schema["params"]
    assert schema["params"]["context_window"]["type"] == "integer"
    assert schema["params"]["context_window"]["default"] == 3


# ── Task 8: Wire PostProcessor ────────────────────────────────────────────────


def test_translate_applies_post_processor():
    """translate() runs opencc conversion on output — simplified chars become traditional."""
    from unittest.mock import patch
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    segments = [{"text": "Hello.", "start": 0.0, "end": 1.0}]

    # _call_ollama returns a response with a simplified Chinese character (软件 → should become 軟體)
    with patch.object(engine, "_call_ollama", return_value="1. 软件更新。"):
        result = engine.translate(segments)

    # opencc s2twp should convert 软件 → 軟體
    assert "軟體" in result[0]["zh_text"]
    assert "软件" not in result[0]["zh_text"]


# ── Parse response bug fixes ──────────────────────────────────────────────────


def test_parse_response_non_sequential_numbers():
    """Model starts numbering from context window's last number instead of 1.
    E.g. 3 context pairs → model outputs 4. t1  5. t2 instead of 1. t1  2. t2.
    Primary path should map positionally, not by key value."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    # Model numbered from 4 instead of 1 (as if continuing context numbering)
    response_text = "4. 各位晚上好。\n5. 歡迎收看新聞。"
    result = engine._parse_response(response_text, SAMPLE_SEGMENTS)
    assert len(result) == 2
    assert result[0]["zh_text"] == "各位晚上好。"
    assert result[1]["zh_text"] == "歡迎收看新聞。"
    assert "[TRANSLATION MISSING]" not in result[0]["zh_text"]
    assert "[TRANSLATION MISSING]" not in result[1]["zh_text"]


def test_parse_response_fallback_ignores_non_translation_lines():
    """When response has extra header/explanation lines, fallback should not
    include them as translations — only numbered lines count."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    # Model outputs a header before numbered translations (3 segments, 2 translations)
    three_segs = [
        {"start": 0.0, "end": 1.0, "text": "Good evening everyone."},
        {"start": 1.0, "end": 2.0, "text": "Welcome to the news."},
        {"start": 2.0, "end": 3.0, "text": "Tonight's top story."},
    ]
    response_text = "Here are the translations:\n1. 各位晚上好。\n2. 歡迎收看新聞。"
    result = engine._parse_response(response_text, three_segs)
    assert len(result) == 3
    assert result[0]["zh_text"] == "各位晚上好。"  # not "Here are the translations:"
    assert result[1]["zh_text"] == "歡迎收看新聞。"
    assert "[TRANSLATION MISSING]" in result[2]["zh_text"]  # only 2 of 3 provided


# ---------------------------------------------------------------------------
# Retry-missing tests
# ---------------------------------------------------------------------------
from unittest.mock import patch as _patch


def _make_seg(start, end, en, zh):
    """Helper: build a TranslatedSegment-like dict."""
    return {"start": start, "end": end, "en_text": en, "zh_text": zh}


def test_no_retry_when_no_missing():
    """When all segments translate successfully, _retry_missing is never called."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    good_batch = [
        _make_seg(0.0, 2.5, "Good evening everyone.", "各位晚上好。"),
        _make_seg(2.5, 5.0, "Welcome to the news.", "歡迎收看新聞。"),
    ]
    with _patch.object(engine, "_translate_batch", return_value=good_batch), \
         _patch.object(engine, "_retry_missing") as mock_retry:
        engine.translate(SAMPLE_SEGMENTS)
    mock_retry.assert_not_called()


def test_retry_called_for_missing_segments():
    """When _translate_batch returns a missing segment, _retry_missing is called with
    only that segment (not the whole batch)."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    batch_with_missing = [
        _make_seg(0.0, 2.5, "Good evening everyone.", "各位晚上好。"),
        _make_seg(2.5, 5.0, "Welcome to the news.", "[TRANSLATION MISSING] Welcome to the news."),
    ]
    retry_result = [
        _make_seg(2.5, 5.0, "Welcome to the news.", "歡迎收看新聞。"),
    ]
    with _patch.object(engine, "_translate_batch", return_value=batch_with_missing), \
         _patch.object(engine, "_retry_missing", return_value=retry_result) as mock_retry:
        engine.translate(SAMPLE_SEGMENTS)
    mock_retry.assert_called_once()
    # First positional arg is the list of missing segments
    retried_segs = mock_retry.call_args[0][0]
    assert len(retried_segs) == 1
    assert retried_segs[0]["text"] == "Welcome to the news."


def test_retry_success_replaces_missing():
    """When retry returns a real translation, the final output contains it — not the
    placeholder."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    batch_with_missing = [
        _make_seg(0.0, 2.5, "Good evening everyone.", "各位晚上好。"),
        _make_seg(2.5, 5.0, "Welcome to the news.", "[TRANSLATION MISSING] Welcome to the news."),
    ]
    retry_result = [
        _make_seg(2.5, 5.0, "Welcome to the news.", "歡迎收看新聞。"),
    ]
    with _patch.object(engine, "_translate_batch", return_value=batch_with_missing), \
         _patch.object(engine, "_retry_missing", return_value=retry_result):
        result = engine.translate(SAMPLE_SEGMENTS)
    assert "[TRANSLATION MISSING]" not in result[1]["zh_text"]
    assert "歡迎收看新聞" in result[1]["zh_text"]


def test_retry_failure_keeps_missing_flagged():
    """When retry also fails (placeholder survives), PostProcessor marks it
    [NEEDS REVIEW] so the human reviewer sees it."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    batch_with_missing = [
        _make_seg(0.0, 2.5, "Good evening everyone.", "各位晚上好。"),
        _make_seg(2.5, 5.0, "Welcome to the news.", "[TRANSLATION MISSING] Welcome to the news."),
    ]
    retry_still_missing = [
        _make_seg(2.5, 5.0, "Welcome to the news.", "[TRANSLATION MISSING] Welcome to the news."),
    ]
    with _patch.object(engine, "_translate_batch", return_value=batch_with_missing), \
         _patch.object(engine, "_retry_missing", return_value=retry_still_missing):
        result = engine.translate(SAMPLE_SEGMENTS)
    # PostProcessor's validate_batch turns [TRANSLATION MISSING] → [NEEDS REVIEW]
    assert "[NEEDS REVIEW]" in result[1]["zh_text"]


def test_retry_splice_multiple_missing():
    """Retry correctly splices results back when multiple segments in one batch
    are missing — verifies the iter/next splice logic for indices [0, 2] in a
    3-segment batch."""
    from translation.ollama_engine import OllamaTranslationEngine
    three_segs = [
        {"start": 0.0, "end": 1.0, "text": "Good evening everyone."},
        {"start": 1.0, "end": 2.0, "text": "Welcome to the news."},
        {"start": 2.0, "end": 3.0, "text": "Tonight's top story."},
    ]
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    # Segments 0 and 2 are missing, segment 1 is fine
    batch_with_two_missing = [
        _make_seg(0.0, 1.0, "Good evening everyone.", "[TRANSLATION MISSING] Good evening everyone."),
        _make_seg(1.0, 2.0, "Welcome to the news.", "歡迎收看新聞。"),
        _make_seg(2.0, 3.0, "Tonight's top story.", "[TRANSLATION MISSING] Tonight's top story."),
    ]
    retry_results = [
        _make_seg(0.0, 1.0, "Good evening everyone.", "各位晚上好。"),
        _make_seg(2.0, 3.0, "Tonight's top story.", "今晚頭條新聞。"),
    ]
    with _patch.object(engine, "_translate_batch", return_value=batch_with_two_missing), \
         _patch.object(engine, "_retry_missing", return_value=retry_results):
        result = engine.translate(three_segs)
    # Segment 1 (never missing) is unchanged
    assert "歡迎收看新聞" in result[1]["zh_text"]
    # Segments 0 and 2 got retried successfully
    assert "[TRANSLATION MISSING]" not in result[0]["zh_text"]
    assert "[TRANSLATION MISSING]" not in result[2]["zh_text"]
    assert "各位晚上好" in result[0]["zh_text"]
    assert "今晚頭條新聞" in result[2]["zh_text"]
