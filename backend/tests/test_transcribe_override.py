import importlib, pytest


@pytest.fixture
def app_mod(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import app as _a
    importlib.reload(_a)
    return _a


def test_override_signature_accepts_kwargs(app_mod):
    import inspect
    sig = inspect.signature(app_mod.transcribe_with_segments)
    for p in ("lang_override", "task_override", "s2hk_override"):
        assert p in sig.parameters and sig.parameters[p].default is None


def test_resolve_whisper_task_helper(app_mod):
    assert app_mod._resolve_whisper_task("translate") == "translate"
    assert app_mod._resolve_whisper_task(None) == "transcribe"
    assert app_mod._resolve_whisper_task("transcribe") == "transcribe"


def test_signature_accepts_asr_profile_override(app_mod):
    import inspect
    sig = inspect.signature(app_mod.transcribe_with_segments)
    assert "asr_profile_override" in sig.parameters
    assert sig.parameters["asr_profile_override"].default is None


def test_mlx_engine_reads_task_from_config():
    # mlx engine forwards config["task"] into the mlx_whisper.transcribe kwargs;
    # default stays "transcribe" when absent. Patch mlx_whisper.transcribe to
    # capture kwargs. The engine references the module-level `mlx_whisper`
    # attribute (`mlx_whisper.transcribe(...)`) and gates on MLX_WHISPER_AVAILABLE.
    import asr.mlx_whisper_engine as m

    captured = {}

    class _Fake:
        @staticmethod
        def transcribe(audio, **kw):
            captured.update(kw)
            return {"segments": []}

    orig_avail = getattr(m, "MLX_WHISPER_AVAILABLE", False)
    orig_lib = getattr(m, "mlx_whisper", None)
    m.MLX_WHISPER_AVAILABLE = True
    m.mlx_whisper = _Fake
    try:
        eng = m.MlxWhisperEngine({"model_size": "large-v3", "task": "translate"})
        eng.transcribe("x.wav", language="yue")
        assert captured["task"] == "translate"
        assert captured["language"] == "yue"
        captured.clear()
        eng2 = m.MlxWhisperEngine({"model_size": "large-v3"})  # no task → default
        eng2.transcribe("x.wav", language="zh")
        assert captured["task"] == "transcribe"
    finally:
        m.MLX_WHISPER_AVAILABLE = orig_avail
        if orig_lib is not None:
            m.mlx_whisper = orig_lib
