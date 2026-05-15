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
        {"source": "Legislative Council", "target": "立法會"},
        {"source": "Chief Executive", "target": "行政長官"},
    ]
    prompt = engine._build_system_prompt(style="formal", glossary=glossary)
    assert "Legislative Council" in prompt
    assert "立法會" in prompt
    assert "Chief Executive" in prompt


def test_filter_glossary_keeps_only_matching_terms():
    """Glossary filter should return only entries whose source term appears in the batch."""
    from translation.ollama_engine import OllamaTranslationEngine
    glossary = [
        {"source": "broadcast", "target": "廣播"},
        {"source": "anchor", "target": "主播"},
        {"source": "Legislative Council", "target": "立法會"},
    ]
    segments = [
        {"text": "The anchor reported the broadcast live."},
        {"text": "Hot weather was tough."},
    ]
    filtered = OllamaTranslationEngine._filter_glossary_for_batch(glossary, segments)
    assert len(filtered) == 2
    terms = {e["source"] for e in filtered}
    assert terms == {"broadcast", "anchor"}


def test_filter_glossary_is_case_insensitive():
    """Matching should be case-insensitive on the source side."""
    from translation.ollama_engine import OllamaTranslationEngine
    glossary = [{"source": "Real Madrid", "target": "皇家馬德里"}]
    segments = [{"text": "real madrid lost last night"}]
    filtered = OllamaTranslationEngine._filter_glossary_for_batch(glossary, segments)
    assert len(filtered) == 1


def test_filter_glossary_empty_inputs():
    """Empty glossary returns []; empty segments returns [] (no text to match against)."""
    from translation.ollama_engine import OllamaTranslationEngine
    assert OllamaTranslationEngine._filter_glossary_for_batch([], [{"text": "x"}]) == []
    # v3.15: empty segments → no text to match → filter returns [] (old behaviour
    # was to short-circuit and return the full glossary; that shortcut was dropped
    # when the module-level filter added lang-guard + strict term matching).
    glossary = [{"source": "x", "target": "y"}]
    assert OllamaTranslationEngine._filter_glossary_for_batch(glossary, []) == []


def test_detect_sentence_scopes_finds_multi_segment_sentences():
    """When a batch has segments that combine into a single sentence, scope is reported."""
    from translation.ollama_engine import OllamaTranslationEngine
    segments = [
        {"text": "The cat sat on"},
        {"text": "the mat yesterday."},
        {"text": "It was happy."},
    ]
    scopes = OllamaTranslationEngine._detect_sentence_scopes(segments)
    # Sentence 1 spans segments 0+1 → included
    # Sentence 2 is single-segment (2) → omitted
    assert len(scopes) == 1
    assert "cat sat on the mat yesterday" in scopes[0]


def test_detect_sentence_scopes_no_scope_when_all_single_segment():
    """If every sentence is contained in one segment, return empty list."""
    from translation.ollama_engine import OllamaTranslationEngine
    segments = [
        {"text": "Hello world."},
        {"text": "Goodbye everyone."},
    ]
    scopes = OllamaTranslationEngine._detect_sentence_scopes(segments)
    assert scopes == []


def test_detect_sentence_scopes_single_or_empty_input():
    """Handle edge cases: empty batch or single segment."""
    from translation.ollama_engine import OllamaTranslationEngine
    assert OllamaTranslationEngine._detect_sentence_scopes([]) == []
    assert OllamaTranslationEngine._detect_sentence_scopes(
        [{"text": "One segment only."}]
    ) == []


def test_parse_enriched_response_basic():
    """Parse numbered output from Pass 2 LLM."""
    from translation.ollama_engine import OllamaTranslationEngine
    text = "1. 在後防方面，大衛·阿拉巴與盧迪加傷病纏身。\n2. 他們表示，球隊真正需要徹底改革。"
    parsed = OllamaTranslationEngine._parse_enriched_response(text, expected_count=2)
    assert parsed[1].startswith("在後防方面")
    assert parsed[2].startswith("他們表示")


def test_parse_enriched_response_ignores_out_of_range():
    """Out-of-range numbers are ignored (model hallucinated extra lines)."""
    from translation.ollama_engine import OllamaTranslationEngine
    text = "1. 好\n2. 佳\n3. 妙\n4. 絕"
    parsed = OllamaTranslationEngine._parse_enriched_response(text, expected_count=2)
    assert set(parsed.keys()) == {1, 2}


def test_translation_passes_defaults_to_1():
    """Default config returns 1 pass (no enrichment)."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    assert engine._get_translation_passes() == 1


def test_translation_passes_honours_config():
    """translation_passes=2 is returned when explicitly set."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b", "translation_passes": 2})
    assert engine._get_translation_passes() == 2


def test_translation_passes_clamps_invalid_values():
    """Values outside [1, 2] are clamped; non-numeric returns 1."""
    from translation.ollama_engine import OllamaTranslationEngine
    assert OllamaTranslationEngine({"engine": "qwen2.5-3b",
                                     "translation_passes": 0})._get_translation_passes() == 1
    assert OllamaTranslationEngine({"engine": "qwen2.5-3b",
                                     "translation_passes": 5})._get_translation_passes() == 2
    assert OllamaTranslationEngine({"engine": "qwen2.5-3b",
                                     "translation_passes": "xx"})._get_translation_passes() == 1


def test_enrich_batch_falls_back_on_empty_output(monkeypatch):
    """When LLM returns empty/missing enrichment, Pass 1 is kept."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    # Monkeypatch _call_ollama to return empty response
    monkeypatch.setattr(engine, "_call_ollama", lambda s, u, t: "")
    batch_segs = [{"text": "Hello"}, {"text": "World"}]
    batch_p1 = [
        {"start": 0.0, "end": 1.0, "en_text": "Hello", "zh_text": "你好"},
        {"start": 1.0, "end": 2.0, "en_text": "World", "zh_text": "世界"},
    ]
    result = engine._enrich_batch(batch_segs, batch_p1, [], 0.1)
    assert result[0]["zh_text"] == "你好"
    assert result[1]["zh_text"] == "世界"


def test_enrich_batch_preserves_other_fields(monkeypatch):
    """Enrichment should only change zh_text; start/end/en_text are preserved."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    monkeypatch.setattr(
        engine, "_call_ollama",
        lambda s, u, t: "1. 你好嘛，今天天氣很好\n2. 歡迎來到這個世界"
    )
    batch_segs = [{"text": "Hello"}, {"text": "World"}]
    batch_p1 = [
        {"start": 0.0, "end": 1.0, "en_text": "Hello", "zh_text": "你好"},
        {"start": 1.0, "end": 2.0, "en_text": "World", "zh_text": "世界"},
    ]
    result = engine._enrich_batch(batch_segs, batch_p1, [], 0.1)
    assert result[0]["start"] == 0.0 and result[0]["end"] == 1.0
    assert result[0]["en_text"] == "Hello"
    assert result[0]["zh_text"] == "你好嘛，今天天氣很好"


def test_user_message_includes_sentence_scope_block():
    """When scopes exist, user_message must include the context block and preserve per-segment output format."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    segments = [
        {"text": "The cat sat on"},
        {"text": "the mat yesterday."},
    ]
    msg = engine._build_user_message(segments)
    # Scope block present
    assert "•" in msg
    assert "cat sat on the mat yesterday" in msg
    # Per-line format preserved — numbered lines are still there
    assert "1. The cat sat on" in msg
    assert "2. the mat yesterday." in msg
    # Instruction clearly tells LLM not to merge
    assert "do not merge" in msg.lower() or "MUST produce" in msg.lower() or "translate each numbered line" in msg.lower()


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


def test_ollama_cloud_qwen_is_thinking_model():
    """qwen3.5:397b-cloud is detected as a thinking model."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen3.5-397b-cloud"})
    assert engine._is_thinking_model() is True


def test_ollama_cloud_qwen_request_body_has_think_false():
    """think:false is included in payload for qwen3.5:397b-cloud."""
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen3.5-397b-cloud"})
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

    assert captured["body"].get("think") is False


def test_ollama_cloud_glm_not_thinking_model():
    """glm-4.6:cloud does NOT trigger thinking mode — no 'think' key in payload."""
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "glm-4.6-cloud"})
    assert engine._is_thinking_model() is False

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


def test_ollama_cloud_gpt_oss_not_thinking_model():
    """gpt-oss:120b-cloud does NOT trigger thinking mode — no 'think' key in payload."""
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "gpt-oss-120b-cloud"})
    assert engine._is_thinking_model() is False

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
    import subprocess as sp
    from translation.ollama_engine import OllamaTranslationEngine
    from translation import ollama_engine as _oe
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    # Ensure signin status cache reports "not signed in" so cloud models are unavailable
    _oe._SIGNIN_STATUS_CACHE["expires_at"] = 0

    mock_response_body = json_mod.dumps({
        "models": [{"name": "qwen2.5:3b"}, {"name": "qwen2.5:7b"}]
    }).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response_body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    # Simulate timeout (not signed in) for cloud model availability checks
    with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="ollama signin", timeout=2)), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        models = engine.get_models()

    # 6 local + 3 cloud = 9 total
    assert len(models) == 9

    available_models = [m for m in models if m["available"]]
    assert len(available_models) == 2  # qwen2.5:3b and qwen2.5:7b

    unavailable_models = [m for m in models if not m["available"]]
    assert len(unavailable_models) == 7

    # Every entry must expose is_cloud boolean
    for m in models:
        assert "is_cloud" in m
        assert isinstance(m["is_cloud"], bool)

    cloud_entries = [m for m in models if m["is_cloud"]]
    cloud_engine_keys = {m["engine"] for m in cloud_entries}
    assert cloud_engine_keys == {
        "glm-4.6-cloud",
        "qwen3.5-397b-cloud",
        "gpt-oss-120b-cloud",
    }

    local_entries = [m for m in models if not m["is_cloud"]]
    assert len(local_entries) == 6


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
    # Phase 4 prompt is written in Traditional Chinese; checks the 繁體 directive
    assert "繁體中文" in prompt and "絕不使用簡體字" in prompt


def test_system_prompt_formal_has_char_limit():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="formal", glossary=[])
    # Phase 4 prompt expresses target as "約 20–28 字"
    assert "20" in prompt and "28" in prompt


def test_system_prompt_formal_has_rthk_context():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="formal", glossary=[])
    # Phase 4 uses 香港電視廣播 instead of explicit "RTHK" branding
    assert "香港" in prompt


def test_system_prompt_cantonese_forbids_simplified():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="cantonese", glossary=[])
    assert "繁體中文" in prompt and "絕不使用簡體字" in prompt


def test_system_prompt_cantonese_has_char_limit():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="cantonese", glossary=[])
    assert "20" in prompt and "28" in prompt


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
    # Phase 3: message now uses per-line translate instruction
    assert "[Translate each numbered line" in msg
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
    """Rolling list is trimmed to last context_window pairs across consecutive
    BATCHES. (batch_size=1 now uses single-segment mode and bypasses sliding
    window — use batch_size=2 with 4 segments to force 2 sequential batches.)"""
    import json as json_mod
    from unittest.mock import patch
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b", "context_window": 1})

    captured_contexts = []  # one per batch
    original_build = engine._build_user_message

    def capturing_build(segments, context_pairs=None):
        captured_contexts.append(list(context_pairs) if context_pairs else [])
        return original_build(segments, context_pairs=context_pairs)

    # Two batches of 2 — second batch should see only 1 context pair (window=1)
    with patch.object(engine, "_call_ollama",
                       return_value="1. 一。\n2. 二。"):
        with patch.object(engine, "_build_user_message", side_effect=capturing_build):
            engine.translate(
                [
                    {"text": "First.", "start": 0, "end": 1},
                    {"text": "Second.", "start": 1, "end": 2},
                    {"text": "Third.", "start": 2, "end": 3},
                    {"text": "Fourth.", "start": 3, "end": 4},
                ],
                batch_size=2,
            )

    # First batch: empty context. Second batch: window=1 → only the LAST pair
    # from the first batch (Second.→二。)
    assert len(captured_contexts) == 2
    assert captured_contexts[0] == []
    assert len(captured_contexts[1]) == 1
    assert captured_contexts[1][0][0] == "Second."


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
    """When retry also fails (placeholder survives), PostProcessor surfaces it
    via the structured `flags` field (Phase B) so the human reviewer sees it."""
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
    # zh_text stays as-is so the reviewer sees what the LLM actually returned;
    # the warning lives in the structured flags list, not as a string prefix.
    assert "review" in result[1].get("flags", [])
    assert "[NEEDS REVIEW]" not in result[1]["zh_text"]


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


def test_api_list_translation_engines_includes_cloud():
    """API response includes the 3 cloud engines with is_cloud flag."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/translation/engines")
        assert resp.status_code == 200
        data = resp.get_json()
        engines = data.get("engines", [])

        engine_keys = {e["engine"] for e in engines}
        assert "glm-4.6-cloud" in engine_keys
        assert "qwen3.5-397b-cloud" in engine_keys
        assert "gpt-oss-120b-cloud" in engine_keys

        # Every entry must have is_cloud
        for e in engines:
            assert "is_cloud" in e

        cloud_engines = [e for e in engines if e["is_cloud"]]
        cloud_keys = {e["engine"] for e in cloud_engines}
        # OpenRouter also flagged as cloud (added in Phase 7)
        assert cloud_keys == {
            "glm-4.6-cloud",
            "qwen3.5-397b-cloud",
            "gpt-oss-120b-cloud",
            "openrouter",
        }

        # Mock and non-cloud Ollama engines must have is_cloud=False
        mock_entry = next(e for e in engines if e["engine"] == "mock")
        assert mock_entry["is_cloud"] is False

        qwen25_entry = next(e for e in engines if e["engine"] == "qwen2.5-3b")
        assert qwen25_entry["is_cloud"] is False

        # Every cloud entry must have a boolean 'available' field
        # (prevents regression where the factory gap silently dropped it)
        for e in cloud_engines:
            assert "available" in e
            assert isinstance(e["available"], bool)


def test_factory_routes_cloud_engines():
    """create_translation_engine routes all 3 cloud engine keys to OllamaTranslationEngine."""
    from translation import create_translation_engine
    from translation.ollama_engine import OllamaTranslationEngine, CLOUD_ENGINES

    for engine_name in CLOUD_ENGINES:
        engine = create_translation_engine({"engine": engine_name})
        assert isinstance(engine, OllamaTranslationEngine)
        assert engine.get_info()["engine"] == engine_name


def test_api_ollama_signin_spawns_subprocess_when_not_signed_in():
    """POST /api/ollama/signin spawns subprocess when user is NOT signed in."""
    import sys
    import subprocess as sp
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from unittest.mock import patch, MagicMock
    from translation import ollama_engine

    ollama_engine._SIGNIN_STATUS_CACHE["expires_at"] = 0

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        mock_process = MagicMock()
        mock_process.pid = 99999
        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="ollama signin", timeout=2)), \
             patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            resp = client.post("/api/ollama/signin")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["signed_in"] is False
            assert data["status"] == "signin_spawned"
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args[0][0]
            assert call_args == ["ollama", "signin"]


def test_api_ollama_signin_returns_already_signed_in():
    """POST /api/ollama/signin returns already_signed_in when user IS signed in (no spawn)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from unittest.mock import patch, MagicMock
    from translation import ollama_engine

    ollama_engine._SIGNIN_STATUS_CACHE["expires_at"] = 0

    from app import app
    app.config["TESTING"] = True

    mock_result = MagicMock()
    mock_result.stdout = "You are already signed in as user 'testuser'\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    with app.test_client() as client:
        with patch("subprocess.run", return_value=mock_result), \
             patch("subprocess.Popen") as mock_popen:
            resp = client.post("/api/ollama/signin")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["signed_in"] is True
            assert data["user"] == "testuser"
            assert data["status"] == "already_signed_in"
            mock_popen.assert_not_called()


def test_api_ollama_signin_missing_binary_returns_500():
    """POST /api/ollama/signin returns 500 when ollama binary is not in PATH."""
    import sys
    from pathlib import Path
    import subprocess as sp
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from unittest.mock import patch
    from translation import ollama_engine

    ollama_engine._SIGNIN_STATUS_CACHE["expires_at"] = 0

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        # Both status check and Popen fail because binary is missing
        with patch("subprocess.run", side_effect=FileNotFoundError("ollama")), \
             patch("subprocess.Popen", side_effect=FileNotFoundError("ollama")):
            resp = client.post("/api/ollama/signin")
            assert resp.status_code == 500
            data = resp.get_json()
            assert "error" in data
            assert "ollama" in data["error"].lower()


def test_ollama_signin_status_detects_signed_in():
    """_get_ollama_signin_status returns signed_in=True when ollama signin outputs 'already signed in'."""
    from unittest.mock import patch, MagicMock
    from translation import ollama_engine

    # Clear cache
    ollama_engine._SIGNIN_STATUS_CACHE["expires_at"] = 0

    mock_result = MagicMock()
    mock_result.stdout = "You are already signed in as user 'testuser'\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result):
        status = ollama_engine._get_ollama_signin_status()

    assert status["signed_in"] is True
    assert status["user"] == "testuser"


def test_ollama_signin_status_detects_not_signed_in_on_timeout():
    """_get_ollama_signin_status returns signed_in=False when subprocess times out (interactive flow)."""
    import subprocess
    from unittest.mock import patch
    from translation import ollama_engine

    ollama_engine._SIGNIN_STATUS_CACHE["expires_at"] = 0

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ollama signin", timeout=2)):
        status = ollama_engine._get_ollama_signin_status()

    assert status["signed_in"] is False
    assert status["user"] is None


def test_ollama_signin_status_missing_binary():
    """_get_ollama_signin_status returns signed_in=False when ollama binary is missing."""
    from unittest.mock import patch
    from translation import ollama_engine

    ollama_engine._SIGNIN_STATUS_CACHE["expires_at"] = 0

    with patch("subprocess.run", side_effect=FileNotFoundError()):
        status = ollama_engine._get_ollama_signin_status()

    assert status["signed_in"] is False
    assert status["user"] is None


def test_ollama_signin_status_cached():
    """_get_ollama_signin_status caches result for 60 seconds."""
    from unittest.mock import patch, MagicMock
    from translation import ollama_engine

    ollama_engine._SIGNIN_STATUS_CACHE["expires_at"] = 0

    mock_result = MagicMock()
    mock_result.stdout = "You are already signed in as user 'testuser'\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        ollama_engine._get_ollama_signin_status()
        ollama_engine._get_ollama_signin_status()
        ollama_engine._get_ollama_signin_status()

    # Should have called subprocess.run exactly once due to caching
    assert mock_run.call_count == 1


def test_ollama_cloud_engine_available_when_signed_in():
    """OllamaTranslationEngine._check_available() returns True for cloud engines when signed in."""
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine
    from translation import ollama_engine

    ollama_engine._SIGNIN_STATUS_CACHE["expires_at"] = 0

    mock_result = MagicMock()
    mock_result.stdout = "You are already signed in as user 'testuser'\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    engine = OllamaTranslationEngine({"engine": "gpt-oss-120b-cloud"})
    with patch("subprocess.run", return_value=mock_result):
        assert engine._check_available() is True


def test_ollama_cloud_engine_unavailable_when_not_signed_in():
    """OllamaTranslationEngine._check_available() returns False for cloud engines when not signed in."""
    import subprocess
    from unittest.mock import patch
    from translation.ollama_engine import OllamaTranslationEngine
    from translation import ollama_engine

    ollama_engine._SIGNIN_STATUS_CACHE["expires_at"] = 0

    engine = OllamaTranslationEngine({"engine": "gpt-oss-120b-cloud"})
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ollama signin", timeout=2)):
        assert engine._check_available() is False


def test_ollama_cloud_get_models_returns_available_when_signed_in():
    """get_models() returns available=True for all cloud entries when signed in."""
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine, CLOUD_ENGINES
    from translation import ollama_engine

    ollama_engine._SIGNIN_STATUS_CACHE["expires_at"] = 0

    mock_result = MagicMock()
    mock_result.stdout = "You are already signed in as user 'testuser'\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    # Mock the local /api/tags to return only qwen2.5:3b
    mock_tags_response = json_mod.dumps({"models": [{"name": "qwen2.5:3b"}]}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_tags_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    with patch("subprocess.run", return_value=mock_result), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        models = engine.get_models()

    cloud_models = [m for m in models if m["is_cloud"]]
    assert len(cloud_models) == 3
    for m in cloud_models:
        assert m["available"] is True, f"{m['engine']} should be available when signed in"


def test_api_ollama_status_endpoint():
    """GET /api/ollama/status returns signin state."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from unittest.mock import patch, MagicMock
    from translation import ollama_engine

    ollama_engine._SIGNIN_STATUS_CACHE["expires_at"] = 0

    from app import app
    app.config["TESTING"] = True

    mock_result = MagicMock()
    mock_result.stdout = "You are already signed in as user 'testuser'\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    with app.test_client() as client:
        with patch("subprocess.run", return_value=mock_result):
            resp = client.get("/api/ollama/status")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["signed_in"] is True
            assert data["user"] == "testuser"


def test_ollama_retries_on_502_then_succeeds():
    """Transient 502 from Ollama Cloud is retried; second attempt succeeds."""
    import json as json_mod
    import urllib.error
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    # First call raises 502, second call returns success
    success_body = json_mod.dumps({"message": {"content": "1. 晚上好。\n2. 歡迎收看新聞。"}}).encode()
    mock_ok = MagicMock()
    mock_ok.read.return_value = success_body
    mock_ok.__enter__ = MagicMock(return_value=mock_ok)
    mock_ok.__exit__ = MagicMock(return_value=False)

    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                url=req.full_url, code=502, msg="Bad Gateway", hdrs=None, fp=None
            )
        return mock_ok

    with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
         patch("time.sleep"):
        result = engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")

    assert len(result) == 2
    assert result[0]["zh_text"] == "晚上好。"
    assert calls["n"] == 2  # 1 fail + 1 success


def test_ollama_raises_after_retries_exhausted():
    """Persistent 502 raises ConnectionError after 4 attempts (1 initial + 3 retries)."""
    import urllib.error
    from unittest.mock import patch
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.HTTPError(
            url=req.full_url, code=502, msg="Bad Gateway", hdrs=None, fp=None
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
         patch("time.sleep"):
        with pytest.raises(ConnectionError, match="502"):
            engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")

    assert calls["n"] == 4  # 1 initial + 3 retries


def test_isolate_fixture_redirects_registry_writes():
    """The autouse _isolate_app_data fixture must redirect _save_registry writes
    to tmp_path so the real backend/data/registry.json is never touched."""
    import app
    from pathlib import Path

    # Sanity check: the fixture should have redirected DATA_DIR already
    real_data_dir = Path(__file__).parent.parent / "data"
    assert app.DATA_DIR != real_data_dir, (
        "autouse fixture failed to redirect DATA_DIR — "
        f"still pointing at {app.DATA_DIR}"
    )

    # Mutate the in-memory registry
    app._file_registry["isolation-sentinel-001"] = {
        "id": "isolation-sentinel-001",
        "original_name": "sentinel.mp4",
        "stored_name": "sentinel.mp4",
        "size": 42,
        "status": "uploaded",
        "uploaded_at": 1700000000,
    }

    # Trigger a synchronous save (R6 _save_registry() is debounced/async;
    # use _save_registry_to_disk() for an immediate flush in tests).
    app._save_registry_to_disk()

    # The test tmp registry MUST contain the sentinel
    test_registry_path = app.DATA_DIR / "registry.json"
    assert test_registry_path.exists(), "registry.json was not written to tmp_path"

    import json
    with open(test_registry_path) as f:
        saved = json.load(f)
    assert "isolation-sentinel-001" in saved

    # The real registry.json (if it exists) must NOT contain the sentinel
    if real_data_dir.joinpath("registry.json").exists():
        with open(real_data_dir / "registry.json") as f:
            real_saved = json.load(f)
        assert "isolation-sentinel-001" not in real_saved, (
            "REAL registry.json was modified — isolation fixture broken!"
        )


def test_ollama_retry_logs_to_stderr(capsys):
    """Retry loop prints [ollama] retry diagnostic to stderr on 5xx."""
    import json as json_mod
    import urllib.error
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    success_body = json_mod.dumps({"message": {"content": "1. 晚上好。\n2. 歡迎。"}}).encode()
    mock_ok = MagicMock()
    mock_ok.read.return_value = success_body
    mock_ok.__enter__ = MagicMock(return_value=mock_ok)
    mock_ok.__exit__ = MagicMock(return_value=False)

    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                url=req.full_url, code=502, msg="Bad Gateway", hdrs=None, fp=None
            )
        return mock_ok

    with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
         patch("time.sleep"):
        engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")

    captured = capsys.readouterr()
    assert "[ollama] retry" in captured.err
    assert "502" in captured.err


def test_api_ollama_signin_rejects_non_localhost():
    """POST /api/ollama/signin returns 403 when request comes from non-localhost."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from unittest.mock import patch

    from app import app
    app.config["TESTING"] = True

    with app.test_client() as client:
        # Override REMOTE_ADDR via environ_base to simulate a LAN request
        with patch("subprocess.Popen") as mock_popen:
            resp = client.post(
                "/api/ollama/signin",
                environ_base={"REMOTE_ADDR": "192.168.1.42"},
            )
            assert resp.status_code == 403
            assert "localhost" in resp.get_json().get("error", "").lower()
            # Subprocess must NOT have been spawned
            mock_popen.assert_not_called()


def test_api_ollama_status_rejects_non_localhost():
    """GET /api/ollama/status returns 403 when request comes from non-localhost."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from unittest.mock import patch

    from app import app
    app.config["TESTING"] = True

    with app.test_client() as client:
        with patch("subprocess.run") as mock_run:
            resp = client.get(
                "/api/ollama/status",
                environ_base={"REMOTE_ADDR": "10.0.0.5"},
            )
            assert resp.status_code == 403
            # Subprocess status check must NOT have run either
            mock_run.assert_not_called()


def test_api_ollama_signin_accepts_ipv6_localhost():
    """POST /api/ollama/signin accepts ::1 (IPv6 localhost) same as 127.0.0.1."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from unittest.mock import patch, MagicMock
    from translation import ollama_engine

    ollama_engine._SIGNIN_STATUS_CACHE["expires_at"] = 0

    from app import app
    app.config["TESTING"] = True

    mock_result = MagicMock()
    mock_result.stdout = "You are already signed in as user 'testuser'\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    with app.test_client() as client:
        with patch("subprocess.run", return_value=mock_result):
            resp = client.post(
                "/api/ollama/signin",
                environ_base={"REMOTE_ADDR": "::1"},
            )
            assert resp.status_code == 200
            assert resp.get_json()["signed_in"] is True


def test_api_translation_engine_models_returns_only_matching_engine():
    """GET /api/translation/engines/<name>/models returns only the entry for <name>, not all models."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True

    with app.test_client() as client:
        # Cloud engine request should return only the cloud engine's entry
        resp = client.get("/api/translation/engines/qwen3.5-397b-cloud/models")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["engine"] == "qwen3.5-397b-cloud"
        models = data["models"]
        assert len(models) == 1
        assert models[0]["engine"] == "qwen3.5-397b-cloud"
        assert models[0]["model"] == "qwen3.5:397b-cloud"
        assert models[0]["is_cloud"] is True

        # Local engine request should return only the local engine's entry
        resp = client.get("/api/translation/engines/qwen2.5-3b/models")
        assert resp.status_code == 200
        data = resp.get_json()
        models = data["models"]
        assert len(models) == 1
        assert models[0]["engine"] == "qwen2.5-3b"
        assert models[0]["model"] == "qwen2.5:3b"
        assert models[0]["is_cloud"] is False


# ===== parallel_batches =====

def test_parallel_batches_returns_same_segment_count(monkeypatch):
    """parallel_batches=2 must return the same number of segments as parallel_batches=1."""
    from translation.ollama_engine import OllamaTranslationEngine

    segments = [
        {"start": float(i), "end": float(i+1), "text": f"segment {i}"}
        for i in range(6)
    ]

    engine = OllamaTranslationEngine({"engine": "mock-ollama"})

    def simple_fake_call(system_prompt, user_message, temperature):
        import re
        nums = re.findall(r"^\d+\.", user_message, re.MULTILINE)
        lines = [f"{n[:-1]}. 翻譯 {n[:-1]}" for n in nums]
        return "\n".join(lines)

    monkeypatch.setattr(engine, "_call_ollama", simple_fake_call)

    seq_result = engine.translate(segments, batch_size=3, parallel_batches=1)
    par_result = engine.translate(segments, batch_size=3, parallel_batches=2)

    assert len(par_result) == len(seq_result) == 6


def test_parallel_batches_disables_context_window(monkeypatch):
    """When parallel_batches > 1, _translate_batch must be called with empty context_pairs."""
    from translation.ollama_engine import OllamaTranslationEngine

    segments = [
        {"start": float(i), "end": float(i+1), "text": f"seg {i}"}
        for i in range(4)
    ]
    captured_contexts = []

    def spy_translate_batch(self, batch, glossary, style, temperature, context_pairs,
                            runtime_overrides=None):
        captured_contexts.append(list(context_pairs))
        return [
            {"start": s["start"], "end": s["end"], "en_text": s["text"], "zh_text": f"譯 {s['text']}"}
            for s in batch
        ]

    monkeypatch.setattr(OllamaTranslationEngine, "_translate_batch", spy_translate_batch)

    engine = OllamaTranslationEngine({"engine": "mock-ollama", "context_window": 3})
    engine.translate(segments, batch_size=2, parallel_batches=2)

    assert all(ctx == [] for ctx in captured_contexts), (
        "parallel path must call _translate_batch with empty context_pairs"
    )


def test_parallel_batches_progress_callback_called(monkeypatch):
    """progress_callback must be called for each batch and counts must be thread-safe."""
    from translation.ollama_engine import OllamaTranslationEngine

    segments = [
        {"start": float(i), "end": float(i+1), "text": f"seg {i}"}
        for i in range(6)
    ]

    def spy_translate_batch(self, batch, glossary, style, temperature, context_pairs,
                            runtime_overrides=None):
        return [
            {"start": s["start"], "end": s["end"], "en_text": s["text"], "zh_text": f"譯 {s['text']}"}
            for s in batch
        ]

    monkeypatch.setattr(OllamaTranslationEngine, "_translate_batch", spy_translate_batch)

    calls = []
    def on_progress(completed, total):
        calls.append((completed, total))

    engine = OllamaTranslationEngine({"engine": "mock-ollama"})
    engine.translate(segments, batch_size=3, parallel_batches=2, progress_callback=on_progress)

    assert len(calls) == 2, "progress_callback must be called once per batch"
    assert calls[-1][0] == 6, "final completed count must equal total segments"
    assert all(total == 6 for _, total in calls)


def test_parallel_batches_one_uses_sequential_path(monkeypatch):
    """parallel_batches=1 must preserve context_window behaviour (non-empty context_pairs)."""
    from translation.ollama_engine import OllamaTranslationEngine

    segments = [
        {"start": float(i), "end": float(i+1), "text": f"seg {i}"}
        for i in range(4)
    ]
    captured_contexts = []

    def spy_translate_batch(self, batch, glossary, style, temperature, context_pairs,
                            runtime_overrides=None):
        captured_contexts.append(list(context_pairs))
        return [
            {"start": s["start"], "end": s["end"], "en_text": s["text"], "zh_text": f"譯 {s['text']}"}
            for s in batch
        ]

    monkeypatch.setattr(OllamaTranslationEngine, "_translate_batch", spy_translate_batch)

    engine = OllamaTranslationEngine({"engine": "mock-ollama", "context_window": 2})
    engine.translate(segments, batch_size=2, parallel_batches=1)

    assert captured_contexts[0] == [], "first batch always has empty context"
    assert len(captured_contexts[1]) > 0, "sequential path: second batch must receive context from first"


# ===== pipeline timing — app._auto_translate =====

def test_translation_progress_includes_elapsed_seconds(monkeypatch):
    """_auto_translate must include elapsed_seconds in every translation_progress emit."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import app as _app

    class FakeProfileManager:
        def get_active(self):
            return {
                "translation": {"engine": "mock"},
                "asr": {"language": "en"},
            }

    class FakeLanguageConfigManager:
        def get(self, _):
            return None

    class FakeGlossaryManager:
        def get(self, _):
            return None

    monkeypatch.setattr(_app, "_profile_manager", FakeProfileManager())
    monkeypatch.setattr(_app, "_language_config_manager", FakeLanguageConfigManager())
    monkeypatch.setattr(_app, "_glossary_manager", FakeGlossaryManager())
    monkeypatch.setattr(_app, "_update_file", lambda *a, **kw: None)
    segments = [{"start": 0.0, "end": 1.0, "text": "hello"}]
    monkeypatch.setattr(_app, "_file_registry", {"fake-id": {"segments": segments}})

    emitted = []
    monkeypatch.setattr(_app.socketio, "emit", lambda event, data=None, **kw: emitted.append((event, data)))

    _app._auto_translate("fake-id")

    progress_events = [d for e, d in emitted if e == "translation_progress"]
    assert len(progress_events) > 0, "translation_progress must be emitted"
    for evt in progress_events:
        assert "elapsed_seconds" in evt, f"elapsed_seconds missing from translation_progress: {evt}"
        assert isinstance(evt["elapsed_seconds"], float)


def test_pipeline_timing_event_emitted(monkeypatch):
    """_auto_translate must emit pipeline_timing after translation completes."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import app as _app

    class FakeProfileManager:
        def get_active(self):
            return {
                "translation": {"engine": "mock"},
                "asr": {"language": "en"},
            }

    class FakeLanguageConfigManager:
        def get(self, _):
            return None

    class FakeGlossaryManager:
        def get(self, _):
            return None

    monkeypatch.setattr(_app, "_profile_manager", FakeProfileManager())
    monkeypatch.setattr(_app, "_language_config_manager", FakeLanguageConfigManager())
    monkeypatch.setattr(_app, "_glossary_manager", FakeGlossaryManager())
    monkeypatch.setattr(_app, "_update_file", lambda *a, **kw: None)
    segments = [{"start": 0.0, "end": 1.0, "text": "hello"}]
    monkeypatch.setattr(_app, "_file_registry", {"fake-id": {"segments": segments}})

    emitted = []
    monkeypatch.setattr(_app.socketio, "emit", lambda event, data=None, **kw: emitted.append((event, data)))

    _app._auto_translate("fake-id", sid="fake-sid")

    timing_events = [d for e, d in emitted if e == "pipeline_timing"]
    assert len(timing_events) == 1, "pipeline_timing must be emitted exactly once"
    evt = timing_events[0]
    assert "translation_seconds" in evt
    assert "total_seconds" in evt
    assert "asr_seconds" in evt
    assert isinstance(evt["translation_seconds"], float)
    assert evt.get("file_id") == "fake-id"


# ---------------------------------------------------------------------------
# Strategy E — single-segment mode (batch_size=1)
# ---------------------------------------------------------------------------

def test_ollama_batch_size_1_dispatches_single_mode():
    """When batch_size=1, translate() must use single-segment path,
    NOT the regular batched _translate_batch."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    calls = []

    def fake_call(system_prompt, user_message, temperature):
        calls.append({"system": system_prompt, "user": user_message})
        # Single-mode prompt's expected output: just the ZH translation
        if "Good evening" in user_message:
            return "各位晚上好。"
        return "歡迎收看新聞。"

    with patch.object(engine, "_call_ollama", side_effect=fake_call):
        result = engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal",
                                   batch_size=1)

    # Two segments → two ollama calls (one per segment, no batching)
    assert len(calls) == 2
    # System prompt is the single-segment one (contains its signature lines)
    assert "唔加引號、編號、解釋" in calls[0]["system"]
    # User message format: 英文：... 譯文：
    assert calls[0]["user"].startswith("英文：")
    assert "譯文：" in calls[0]["user"]
    # Output preserves segment timing + extracts ZH cleanly
    assert len(result) == 2
    assert result[0]["zh_text"] == "各位晚上好。"
    assert result[0]["en_text"] == "Good evening everyone."
    assert result[0]["start"] == 0.0
    assert result[1]["zh_text"] == "歡迎收看新聞。"


def test_ollama_batch_size_1_strips_label_prefix():
    """Single-mode parser strips '譯文：' / 'Translation:' prefix from response."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    with patch.object(engine, "_call_ollama",
                       side_effect=["譯文：晚安。", "Translation: 你好。"]):
        result = engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal",
                                   batch_size=1)

    assert result[0]["zh_text"] == "晚安。"
    assert result[1]["zh_text"] == "你好。"


def test_ollama_batch_size_1_empty_text_skipped():
    """Empty source text → empty translation, no LLM call."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    segs = [
        {"start": 0.0, "end": 1.0, "text": ""},
        {"start": 1.0, "end": 2.0, "text": "Hello."},
    ]

    calls = []
    with patch.object(engine, "_call_ollama",
                       side_effect=lambda s, u, t: calls.append(u) or "你好。"):
        result = engine.translate(segs, glossary=[], style="formal", batch_size=1)

    assert len(calls) == 1   # only the non-empty seg invokes ollama
    assert result[0]["zh_text"] == ""
    assert result[1]["zh_text"] == "你好。"


def test_ollama_batch_size_1_glossary_filtered_per_segment():
    """Glossary entries are filtered by per-segment EN text (not whole batch)."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    glossary = [
        {"source": "Madrid", "target": "皇馬"},
        {"source": "Chelsea", "target": "車路士"},
    ]
    segs = [
        {"start": 0.0, "end": 1.0, "text": "Madrid wins."},      # only Madrid
        {"start": 1.0, "end": 2.0, "text": "Chelsea draws."},    # only Chelsea
    ]

    captured_prompts = []
    with patch.object(engine, "_call_ollama",
                       side_effect=lambda s, u, t: captured_prompts.append(s) or "x"):
        engine.translate(segs, glossary=glossary, style="formal", batch_size=1)

    # First call should mention Madrid → 皇馬, NOT Chelsea
    assert "Madrid" in captured_prompts[0] and "皇馬" in captured_prompts[0]
    assert "Chelsea" not in captured_prompts[0]
    # Second call: opposite
    assert "Chelsea" in captured_prompts[1] and "車路士" in captured_prompts[1]
    assert "Madrid" not in captured_prompts[1]


def test_ollama_parse_single_response_helper():
    """_parse_single_response strips labels and takes first non-empty line."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    assert engine._parse_single_response("意甲球會科莫。") == "意甲球會科莫。"
    assert engine._parse_single_response("譯文：意甲球會科莫。") == "意甲球會科莫。"
    assert engine._parse_single_response("譯文: 意甲球會科莫。") == "意甲球會科莫。"
    assert engine._parse_single_response("\n\n譯文：晚安。\n後記") == "晚安。"
    assert engine._parse_single_response("中文：你好") == "你好"


def test_ollama_batch_size_gt_1_uses_batch_path():
    """batch_size > 1 must NOT use single-mode dispatch — confirms branch
    only triggers on batch_size==1."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    captured = []
    with patch.object(engine, "_call_ollama",
                       side_effect=lambda s, u, t: captured.append(u) or "1. a\n2. b"):
        engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal", batch_size=10)

    # Batch path issues ONE call for both segments
    assert len(captured) == 1
    # Batch user message contains numbered list, not single-mode 英文：format
    assert "1. " in captured[0] and "2. " in captured[0]
