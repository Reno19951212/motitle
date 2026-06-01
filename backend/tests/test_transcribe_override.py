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
