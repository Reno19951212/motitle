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


from unittest.mock import patch, MagicMock
from collections import namedtuple


def test_whisper_engine_transcribe_faster():
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"})

    MockSeg = namedtuple("MockSeg", ["start", "end", "text", "words"])
    mock_segments = [
        MockSeg(start=0.0, end=2.5, text=" Hello world", words=None),
        MockSeg(start=2.5, end=5.0, text=" Testing one two", words=None),
    ]
    MockInfo = namedtuple("MockInfo", ["language"])
    mock_info = MockInfo(language="en")

    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter(mock_segments), mock_info)

    with patch.object(engine, '_get_model', return_value=(mock_model, 'faster')):
        result = engine.transcribe("/tmp/test.wav", language="en")

    assert len(result) == 2
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 2.5
    assert result[0]["text"] == "Hello world"
    assert result[1]["text"] == "Testing one two"


def test_whisper_engine_transcribe_openai():
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"})

    mock_result = {
        "text": "Hello world",
        "language": "en",
        "segments": [
            {"id": 0, "start": 0.0, "end": 2.5, "text": " Hello world"},
            {"id": 1, "start": 2.5, "end": 5.0, "text": " Testing"},
        ]
    }

    mock_model = MagicMock()
    mock_model.transcribe.return_value = mock_result

    with patch.object(engine, '_get_model', return_value=(mock_model, 'openai')):
        result = engine.transcribe("/tmp/test.wav", language="en")

    assert len(result) == 2
    assert result[0]["text"] == "Hello world"
    assert result[1]["text"] == "Testing"


def test_whisper_engine_get_info():
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({"engine": "whisper", "model_size": "small", "language": "en", "device": "auto"})
    info = engine.get_info()
    assert info["engine"] == "whisper"
    assert info["model_size"] == "small"
    assert info["available"] is True
    assert "en" in info["languages"]


import json


def test_api_list_asr_engines():
    """Test the /api/asr/engines REST endpoint."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/asr/engines")
        assert resp.status_code == 200
        data = resp.get_json()
        engines = data["engines"]
        assert len(engines) == 4

        engine_names = [e["engine"] for e in engines]
        assert "whisper" in engine_names
        assert "mlx-whisper" in engine_names
        assert "qwen3-asr" in engine_names
        assert "flg-asr" in engine_names

        whisper_info = next(e for e in engines if e["engine"] == "whisper")
        assert whisper_info["available"] is True

        mlx_info = next(e for e in engines if e["engine"] == "mlx-whisper")
        assert mlx_info["available"] is True

        qwen_info = next(e for e in engines if e["engine"] == "qwen3-asr")
        assert qwen_info["available"] is False


def test_whisper_engine_params_schema():
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({"engine": "whisper", "model_size": "small", "device": "auto"})
    schema = engine.get_params_schema()
    assert schema["engine"] == "whisper"
    assert "model_size" in schema["params"]
    assert "language" in schema["params"]
    assert "device" in schema["params"]
    assert schema["params"]["model_size"]["type"] == "string"
    assert "small" in schema["params"]["model_size"]["enum"]
    assert schema["params"]["model_size"]["default"] == "small"


def test_mlx_whisper_engine_schema_and_info():
    """MlxWhisperEngine reports correct info and schema."""
    from asr.mlx_whisper_engine import MlxWhisperEngine
    engine = MlxWhisperEngine({"engine": "mlx-whisper", "model_size": "large-v3"})

    info = engine.get_info()
    assert info["engine"] == "mlx-whisper"
    assert info["model_size"] == "large-v3"
    assert info["available"] is True

    schema = engine.get_params_schema()
    params = schema["params"]
    assert "model_size" in params
    assert "large-v3" in params["model_size"]["enum"]
    assert params["model_size"]["default"] == "large-v3"
    assert "language" in params
    assert "condition_on_previous_text" in params
    assert params["condition_on_previous_text"]["type"] == "boolean"


def test_whisper_engine_params_schema_includes_layer1():
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({"engine": "whisper", "model_size": "tiny"})
    schema = engine.get_params_schema()
    params = schema["params"]

    assert "max_new_tokens" in params
    assert params["max_new_tokens"]["type"] == "integer"
    assert params["max_new_tokens"]["default"] is None
    assert params["max_new_tokens"]["minimum"] == 1

    assert "condition_on_previous_text" in params
    assert params["condition_on_previous_text"]["type"] == "boolean"
    assert params["condition_on_previous_text"]["default"] is True

    assert "vad_filter" in params
    assert params["vad_filter"]["type"] == "boolean"
    assert params["vad_filter"]["default"] is False


def test_whisper_engine_schema_includes_initial_prompt():
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({"engine": "whisper", "model_size": "tiny"})
    params = engine.get_params_schema()["params"]
    assert "initial_prompt" in params
    assert params["initial_prompt"]["type"] == "string"
    assert params["initial_prompt"]["default"] == ""


def test_mlx_whisper_schema_includes_initial_prompt():
    from asr.mlx_whisper_engine import MlxWhisperEngine
    engine = MlxWhisperEngine({"engine": "mlx-whisper", "model_size": "large-v3"})
    params = engine.get_params_schema()["params"]
    assert "initial_prompt" in params
    assert params["initial_prompt"]["type"] == "string"
    assert params["initial_prompt"]["default"] == ""


def test_whisper_engine_passes_initial_prompt_to_faster_whisper():
    """When initial_prompt is set in config, it must be forwarded to model.transcribe()."""
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({
        "engine": "whisper", "model_size": "tiny", "language": "zh", "device": "cpu",
        "initial_prompt": "以下係香港賽馬新聞，繁體中文。",
    })

    MockSeg = namedtuple("MockSeg", ["start", "end", "text", "words"])
    MockInfo = namedtuple("MockInfo", ["language"])
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter([
        MockSeg(start=0.0, end=2.5, text=" 你好", words=None),
    ]), MockInfo(language="zh"))

    with patch.object(engine, '_get_model', return_value=(mock_model, 'faster')):
        engine.transcribe("/tmp/test.wav", language="zh")

    call_kwargs = mock_model.transcribe.call_args.kwargs
    assert call_kwargs.get("initial_prompt") == "以下係香港賽馬新聞，繁體中文。"


def test_whisper_engine_passes_none_initial_prompt_when_unset():
    """No initial_prompt key in config → kwarg is explicitly None (so faster-whisper's
    own default kicks in, not undefined behavior)."""
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({
        "engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu",
    })

    MockSeg = namedtuple("MockSeg", ["start", "end", "text", "words"])
    MockInfo = namedtuple("MockInfo", ["language"])
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter([]), MockInfo(language="en"))

    with patch.object(engine, '_get_model', return_value=(mock_model, 'faster')):
        engine.transcribe("/tmp/test.wav", language="en")

    call_kwargs = mock_model.transcribe.call_args.kwargs
    assert "initial_prompt" in call_kwargs
    assert call_kwargs["initial_prompt"] is None


def test_whisper_engine_empty_string_initial_prompt_treated_as_none():
    """Empty string is falsy → should be normalized to None (avoids empty prompt
    being passed to model, which can confuse decoder)."""
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({
        "engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu",
        "initial_prompt": "",
    })

    MockSeg = namedtuple("MockSeg", ["start", "end", "text", "words"])
    MockInfo = namedtuple("MockInfo", ["language"])
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter([]), MockInfo(language="en"))

    with patch.object(engine, '_get_model', return_value=(mock_model, 'faster')):
        engine.transcribe("/tmp/test.wav", language="en")

    assert mock_model.transcribe.call_args.kwargs["initial_prompt"] is None


def test_whisper_engine_openai_path_forwards_initial_prompt():
    """openai-whisper path also forwards initial_prompt."""
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({
        "engine": "whisper", "model_size": "tiny", "language": "zh", "device": "cpu",
        "initial_prompt": "繁體中文。",
    })

    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"text": "", "language": "zh", "segments": []}

    with patch.object(engine, '_get_model', return_value=(mock_model, 'openai')):
        engine.transcribe("/tmp/test.wav", language="zh")

    assert mock_model.transcribe.call_args.kwargs["initial_prompt"] == "繁體中文。"


def test_qwen3_engine_params_schema():
    from asr import create_asr_engine
    engine = create_asr_engine({"engine": "qwen3-asr", "model_size": "large"})
    schema = engine.get_params_schema()
    assert schema["engine"] == "qwen3-asr"
    assert "model_size" in schema["params"]
    assert "language" in schema["params"]


def test_flg_engine_params_schema():
    from asr import create_asr_engine
    engine = create_asr_engine({"engine": "flg-asr", "model_size": "standard"})
    schema = engine.get_params_schema()
    assert schema["engine"] == "flg-asr"
    assert "model_size" in schema["params"]
    assert "language" in schema["params"]


def test_api_asr_engine_params_whisper():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/asr/engines/whisper/params")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["engine"] == "whisper"
        assert "params" in data
        assert "model_size" in data["params"]
        assert "language" in data["params"]
        assert "device" in data["params"]


def test_api_asr_engine_params_qwen3():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/asr/engines/qwen3-asr/params")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["engine"] == "qwen3-asr"


def test_api_asr_engine_params_unknown():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/asr/engines/nonexistent/params")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data


def test_whisper_faster_passes_layer1_params():
    """Layer 1 params are forwarded to model.transcribe()."""
    from asr.whisper_engine import WhisperEngine

    engine = WhisperEngine({
        "engine": "whisper",
        "model_size": "tiny",
        "max_new_tokens": 30,
        "condition_on_previous_text": False,
        "vad_filter": True,
    })

    MockInfo = namedtuple("MockInfo", ["language"])
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter([]), MockInfo(language="en"))

    with patch.object(engine, '_get_model', return_value=(mock_model, 'faster')):
        engine.transcribe("/tmp/test.wav", language="en")

    mock_model.transcribe.assert_called_once_with(
        "/tmp/test.wav",
        language="en",
        task="transcribe",
        max_new_tokens=30,
        condition_on_previous_text=False,
        vad_filter=True,
        word_timestamps=False,
        initial_prompt=None,
    )


def test_whisper_faster_null_and_zero_max_tokens_become_none():
    """max_new_tokens of None, 0, or absent all map to None (unlimited)."""
    from asr.whisper_engine import WhisperEngine

    MockInfo = namedtuple("MockInfo", ["language"])

    _MISSING = object()  # sentinel for "key absent from config"

    for val in (None, 0, _MISSING):
        config = {"engine": "whisper", "model_size": "tiny"}
        if val is not _MISSING:
            config["max_new_tokens"] = val

        engine = WhisperEngine(config)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), MockInfo(language="en"))

        with patch.object(engine, '_get_model', return_value=(mock_model, 'faster')):
            engine.transcribe("/tmp/test.wav", language="en")

        call_kwargs = mock_model.transcribe.call_args.kwargs
        label = f"val={val!r}"
        assert call_kwargs["max_new_tokens"] is None, f"Expected None for {label}"


def test_whisper_faster_invalid_max_new_tokens_falls_back_to_none():
    """Non-integer max_new_tokens (e.g. from manually-edited profile JSON) falls back to None."""
    from asr.whisper_engine import WhisperEngine

    MockInfo = namedtuple("MockInfo", ["language"])

    for bad_val in ("abc", "2.5", True):
        engine = WhisperEngine({"engine": "whisper", "model_size": "tiny", "max_new_tokens": bad_val})
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), MockInfo(language="en"))

        with patch.object(engine, '_get_model', return_value=(mock_model, 'faster')):
            engine.transcribe("/tmp/test.wav", language="en")

        call_kwargs = mock_model.transcribe.call_args.kwargs
        assert call_kwargs["max_new_tokens"] is None, f"Expected None for bad_val={bad_val!r}"


def test_whisper_openai_passes_condition_on_previous_text():
    """openai-whisper path passes condition_on_previous_text; ignores the others."""
    from asr.whisper_engine import WhisperEngine

    engine = WhisperEngine({
        "engine": "whisper", "model_size": "tiny",
        "condition_on_previous_text": False,
        "max_new_tokens": 30,
        "vad_filter": True,
    })

    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"text": "", "language": "en", "segments": []}

    with patch.object(engine, '_get_model', return_value=(mock_model, 'openai')):
        engine.transcribe("/tmp/test.wav", language="en")

    call_kwargs = mock_model.transcribe.call_args.kwargs
    assert call_kwargs["condition_on_previous_text"] is False
    assert "max_new_tokens" not in call_kwargs
    assert "vad_filter" not in call_kwargs


# ── Phase 6 Step 1: word_timestamps support ──────────────────────────────────


def test_whisper_faster_word_timestamps_off_by_default():
    """When word_timestamps not set, faster-whisper receives False and no words in output."""
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({"engine": "whisper", "model_size": "tiny"})

    MockSeg = namedtuple("MockSeg", ["start", "end", "text", "words"])
    mock_segs = [MockSeg(start=0.0, end=1.0, text=" Hi", words=None)]
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter(mock_segs), MagicMock())

    with patch.object(engine, '_get_model', return_value=(mock_model, 'faster')):
        result = engine.transcribe("/tmp/t.wav")

    assert mock_model.transcribe.call_args.kwargs["word_timestamps"] is False
    assert "words" not in result[0]


def test_whisper_faster_word_timestamps_populates_words():
    """When word_timestamps=True and engine returns words, they appear in segment dict."""
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({
        "engine": "whisper", "model_size": "tiny", "word_timestamps": True,
    })

    MockWord = namedtuple("MockWord", ["word", "start", "end", "probability"])
    MockSeg = namedtuple("MockSeg", ["start", "end", "text", "words"])
    words = [
        MockWord(word=" Hello", start=0.0, end=0.4, probability=0.95),
        MockWord(word=" world", start=0.4, end=0.9, probability=0.88),
    ]
    mock_segs = [MockSeg(start=0.0, end=1.0, text=" Hello world", words=words)]
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter(mock_segs), MagicMock())

    with patch.object(engine, '_get_model', return_value=(mock_model, 'faster')):
        result = engine.transcribe("/tmp/t.wav")

    assert mock_model.transcribe.call_args.kwargs["word_timestamps"] is True
    assert "words" in result[0]
    assert len(result[0]["words"]) == 2
    assert result[0]["words"][0]["word"] == " Hello"
    assert result[0]["words"][0]["start"] == 0.0
    assert result[0]["words"][0]["end"] == 0.4
    assert result[0]["words"][0]["probability"] == 0.95


def test_whisper_openai_word_timestamps_populates_words():
    """openai-whisper path: dict-based words get lifted into the segment."""
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({
        "engine": "whisper", "model_size": "tiny", "word_timestamps": True,
    })

    mock_model = MagicMock()
    mock_model.transcribe.return_value = {
        "segments": [{
            "start": 0.0, "end": 1.0, "text": " Hi there",
            "words": [
                {"word": " Hi", "start": 0.0, "end": 0.2, "probability": 0.9},
                {"word": " there", "start": 0.2, "end": 1.0, "probability": 0.8},
            ],
        }]
    }

    with patch.object(engine, '_get_model', return_value=(mock_model, 'openai')):
        result = engine.transcribe("/tmp/t.wav")

    assert mock_model.transcribe.call_args.kwargs["word_timestamps"] is True
    assert len(result[0]["words"]) == 2
    assert result[0]["words"][1]["end"] == 1.0


def test_whisper_faster_no_words_when_engine_returns_none():
    """If word_timestamps=True but engine returns no words (e.g., empty segment), skip gracefully."""
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({
        "engine": "whisper", "model_size": "tiny", "word_timestamps": True,
    })
    MockSeg = namedtuple("MockSeg", ["start", "end", "text", "words"])
    mock_segs = [MockSeg(start=0.0, end=1.0, text=" Hi", words=None)]
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter(mock_segs), MagicMock())

    with patch.object(engine, '_get_model', return_value=(mock_model, 'faster')):
        result = engine.transcribe("/tmp/t.wav")

    assert "words" not in result[0]  # Graceful absence


def test_whisper_schema_advertises_word_timestamps():
    """Schema includes the new word_timestamps param so frontend can surface it."""
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({"engine": "whisper", "model_size": "tiny"})
    schema = engine.get_params_schema()
    assert "word_timestamps" in schema["params"]
    assert schema["params"]["word_timestamps"]["default"] is False
