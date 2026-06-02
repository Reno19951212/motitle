import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_make_ollama_llm_call_returns_callable():
    fn = _app._make_ollama_llm_call()
    assert callable(fn)
    import inspect
    assert len(inspect.signature(fn).parameters) == 2
