"""Phase 5 T2.1 — Whisper model instantiated once per (model_size, device, compute_type)."""
import pytest


@pytest.fixture(autouse=True)
def _reset_engine_caches():
    """Clear module-level caches before and after each test."""
    from asr import whisper_engine as we
    we._faster_model_cache.clear()
    we._openai_model_cache.clear()
    yield
    we._faster_model_cache.clear()
    we._openai_model_cache.clear()


def test_whisper_engine_caches_per_config(monkeypatch):
    """Two engines with identical (model_size, device, compute_type) share one model."""
    from asr import whisper_engine as we

    instantiation_count = {"n": 0}

    class FakeModel:
        def __init__(self, *a, **kw):
            instantiation_count["n"] += 1

    monkeypatch.setattr(we, "FasterWhisperModel", FakeModel)
    monkeypatch.setattr(we, "FASTER_WHISPER_AVAILABLE", True)

    e1 = we.WhisperEngine({"model_size": "small", "device": "cpu", "compute_type": "int8"})
    e2 = we.WhisperEngine({"model_size": "small", "device": "cpu", "compute_type": "int8"})

    m1, _ = e1._get_model()
    m2, _ = e2._get_model()
    assert m1 is m2
    assert instantiation_count["n"] == 1


def test_whisper_engine_separate_cache_per_device(monkeypatch):
    """Different devices get separate model instances."""
    from asr import whisper_engine as we

    instantiation_count = {"n": 0}

    class FakeModel:
        def __init__(self, *a, **kw):
            instantiation_count["n"] += 1

    monkeypatch.setattr(we, "FasterWhisperModel", FakeModel)
    monkeypatch.setattr(we, "FASTER_WHISPER_AVAILABLE", True)

    e_cpu = we.WhisperEngine({"model_size": "small", "device": "cpu", "compute_type": "int8"})
    e_cuda = we.WhisperEngine({"model_size": "small", "device": "cuda", "compute_type": "int8"})

    m_cpu, _ = e_cpu._get_model()
    m_cuda, _ = e_cuda._get_model()
    assert m_cpu is not m_cuda
    assert instantiation_count["n"] == 2


def test_whisper_engine_separate_cache_per_compute_type(monkeypatch):
    """Different compute_types (int8 vs float16) get separate model instances."""
    from asr import whisper_engine as we

    instantiation_count = {"n": 0}

    class FakeModel:
        def __init__(self, *a, **kw):
            instantiation_count["n"] += 1

    monkeypatch.setattr(we, "FasterWhisperModel", FakeModel)
    monkeypatch.setattr(we, "FASTER_WHISPER_AVAILABLE", True)

    e_int8 = we.WhisperEngine({"model_size": "small", "device": "cpu", "compute_type": "int8"})
    e_fp16 = we.WhisperEngine({"model_size": "small", "device": "cpu", "compute_type": "float16"})

    m_int8, _ = e_int8._get_model()
    m_fp16, _ = e_fp16._get_model()
    assert m_int8 is not m_fp16
    assert instantiation_count["n"] == 2


def test_whisper_engine_separate_cache_per_model_size(monkeypatch):
    """Different model sizes still get separate instances (existing behavior)."""
    from asr import whisper_engine as we

    instantiation_count = {"n": 0}

    class FakeModel:
        def __init__(self, *a, **kw):
            instantiation_count["n"] += 1

    monkeypatch.setattr(we, "FasterWhisperModel", FakeModel)
    monkeypatch.setattr(we, "FASTER_WHISPER_AVAILABLE", True)

    e_small = we.WhisperEngine({"model_size": "small", "device": "cpu"})
    e_large = we.WhisperEngine({"model_size": "large", "device": "cpu"})

    m_small, _ = e_small._get_model()
    m_large, _ = e_large._get_model()
    assert m_small is not m_large
    assert instantiation_count["n"] == 2
