import pytest
from unittest.mock import patch, Mock
from engines.llm import LLMEngine


def test_llm_engine_abc_cannot_instantiate():
    """LLMEngine is ABC — direct instantiation must raise TypeError."""
    with pytest.raises(TypeError):
        LLMEngine()


def test_ollama_llm_call_success(monkeypatch):
    from engines.llm.ollama import OllamaLLM
    fake_resp = Mock()
    fake_resp.json.return_value = {"message": {"content": "  hello world  "}}
    fake_resp.raise_for_status = Mock()
    monkeypatch.setattr("requests.post", Mock(return_value=fake_resp))
    llm = OllamaLLM(model="m", base_url="http://localhost:11434")
    out = llm.call("sys", "user")
    assert out == "hello world"


def test_ollama_llm_call_empty_raises(monkeypatch):
    from engines.llm.ollama import OllamaLLM
    fake_resp = Mock()
    fake_resp.json.return_value = {"message": {"content": ""}}
    fake_resp.raise_for_status = Mock()
    monkeypatch.setattr("requests.post", Mock(return_value=fake_resp))
    llm = OllamaLLM(model="m", base_url="http://localhost:11434", max_retries=0)
    with pytest.raises(RuntimeError, match="empty"):
        llm.call("sys", "user")


def test_ollama_llm_call_retries_on_failure(monkeypatch):
    """First call fails, second succeeds — verify retry logic."""
    from engines.llm.ollama import OllamaLLM
    call_count = {"n": 0}
    def fake_post(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ConnectionError("boom")
        r = Mock()
        r.json.return_value = {"message": {"content": "ok"}}
        r.raise_for_status = Mock()
        return r
    monkeypatch.setattr("requests.post", fake_post)
    # Use lower sleep to keep test fast
    monkeypatch.setattr("time.sleep", lambda s: None)
    llm = OllamaLLM(model="m", base_url="http://localhost:11434", max_retries=2)
    out = llm.call("sys", "user")
    assert out == "ok"
    assert call_count["n"] == 2


def test_ollama_llm_call_passes_think_param(monkeypatch):
    """think:false should be sent in payload (185× speedup we discovered)."""
    from engines.llm.ollama import OllamaLLM
    captured = {}
    def fake_post(url, json=None, timeout=None):
        captured["payload"] = json
        r = Mock()
        r.json.return_value = {"message": {"content": "x"}}
        r.raise_for_status = Mock()
        return r
    monkeypatch.setattr("requests.post", fake_post)
    llm = OllamaLLM(model="m", base_url="http://localhost:11434")
    llm.call("sys", "user", think=False)
    assert captured["payload"]["think"] is False
