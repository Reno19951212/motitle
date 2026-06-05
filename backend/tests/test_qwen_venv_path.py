from engines.transcribe import qwen3_vad_engine as q


def test_venv_python_posix(monkeypatch):
    monkeypatch.delenv("V6_QWEN_VENV_PYTHON", raising=False)
    p = q.default_qwen_venv_python(_os_name="posix")
    assert p.name == "python"
    assert "bin" in p.parts


def test_venv_python_windows(monkeypatch):
    monkeypatch.delenv("V6_QWEN_VENV_PYTHON", raising=False)
    p = q.default_qwen_venv_python(_os_name="nt")
    assert p.name == "python.exe"
    assert "Scripts" in p.parts


def test_venv_python_env_override(monkeypatch):
    monkeypatch.setenv("V6_QWEN_VENV_PYTHON", "/custom/python")
    assert str(q.default_qwen_venv_python()) == "/custom/python"
