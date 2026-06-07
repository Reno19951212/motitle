# backend/tests/test_env_loader.py
import os
os.environ.setdefault("FLASK_SECRET_KEY", "test")   # app.py requires it at import time
import app as app_module


def test_load_env_file_sets_missing_keys(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("FOO_BETA_TEST=hello\n# a comment\n\nBAR_BETA_TEST=world\n", encoding="utf-8")
    monkeypatch.delenv("FOO_BETA_TEST", raising=False)
    monkeypatch.delenv("BAR_BETA_TEST", raising=False)
    app_module._load_env_file(env)
    assert os.environ["FOO_BETA_TEST"] == "hello"
    assert os.environ["BAR_BETA_TEST"] == "world"


def test_load_env_file_does_not_override_existing(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("ALREADY_SET_BETA_TEST=fromfile\n", encoding="utf-8")
    monkeypatch.setenv("ALREADY_SET_BETA_TEST", "fromenv")
    app_module._load_env_file(env)
    assert os.environ["ALREADY_SET_BETA_TEST"] == "fromenv"   # exported value wins


def test_load_env_file_missing_file_is_silent(tmp_path):
    app_module._load_env_file(tmp_path / "nope.env")   # must not raise


def test_load_env_file_ignores_malformed_lines(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("no_equals_here\nGOOD_BETA_TEST=v\n", encoding="utf-8")
    monkeypatch.delenv("GOOD_BETA_TEST", raising=False)
    app_module._load_env_file(env)
    assert os.environ["GOOD_BETA_TEST"] == "v"


def test_load_env_file_binary_is_silent(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes(b"\xff\xfe\x00\x01 binary garbage \x80\x81")
    app_module._load_env_file(env)   # must NOT raise (UnicodeDecodeError is a ValueError)
