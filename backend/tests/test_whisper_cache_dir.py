"""Tests for app._whisper_cache_dir() override precedence.

Requires the full venv because it imports the Flask `app` module
(conftest.py sets FLASK_SECRET_KEY so the import succeeds).

The Windows-branch tests patch ``app.Path`` to ``pathlib.PureWindowsPath`` so a
real ``WindowsPath`` is never instantiated on the (posix) test host — pathlib
raises ``NotImplementedError: cannot instantiate 'WindowsPath'`` otherwise.
"""
from pathlib import Path, PureWindowsPath

import app


def test_xdg_cache_home_wins(monkeypatch):
    """XDG_CACHE_HOME takes top precedence (its /whisper subdir)."""
    monkeypatch.setattr(app.os, "environ", {"XDG_CACHE_HOME": "/tmp/xdg", "HF_HOME": "/tmp/hf"})
    monkeypatch.setattr(app.os, "name", "posix")
    assert app._whisper_cache_dir() == Path("/tmp/xdg") / "whisper"


def test_hf_home_fallback(monkeypatch):
    """With no XDG_CACHE_HOME, HF_HOME is used as the cache-root fallback."""
    monkeypatch.setattr(app.os, "environ", {"HF_HOME": "/tmp/hf"})
    monkeypatch.setattr(app.os, "name", "posix")
    assert app._whisper_cache_dir() == Path("/tmp/hf") / "whisper"


def test_xdg_takes_precedence_over_hf(monkeypatch):
    """A non-empty XDG_CACHE_HOME wins over HF_HOME."""
    monkeypatch.setattr(app.os, "environ", {"XDG_CACHE_HOME": "/tmp/x", "HF_HOME": "/tmp/h"})
    monkeypatch.setattr(app.os, "name", "posix")
    assert app._whisper_cache_dir() == Path("/tmp/x") / "whisper"


def test_empty_xdg_falls_through_to_hf(monkeypatch):
    """A present-but-blank XDG_CACHE_HOME is skipped (must NOT become relative
    'whisper'); HF_HOME is used instead."""
    monkeypatch.setattr(app.os, "environ", {"XDG_CACHE_HOME": "", "HF_HOME": "/tmp/hf"})
    monkeypatch.setattr(app.os, "name", "posix")
    assert app._whisper_cache_dir() == Path("/tmp/hf") / "whisper"


def test_empty_xdg_and_hf_fall_through_to_default(monkeypatch):
    """Blank XDG_CACHE_HOME and HF_HOME both skipped -> conventional default."""
    monkeypatch.setattr(app.os, "environ", {"XDG_CACHE_HOME": "", "HF_HOME": ""})
    monkeypatch.setattr(app.os, "name", "posix")
    assert app._whisper_cache_dir() == Path.home() / ".cache" / "whisper"


def test_macos_default_no_env(monkeypatch):
    """macOS/Linux with no override -> ~/.cache/whisper (byte-identical default)."""
    monkeypatch.setattr(app.os, "environ", {})
    monkeypatch.setattr(app.os, "name", "posix")
    assert app._whisper_cache_dir() == Path.home() / ".cache" / "whisper"


class _FakeWinPath(PureWindowsPath):
    """PureWindowsPath plus a deterministic .home() so the nt-branch never
    instantiates a real WindowsPath on the posix test host."""

    @classmethod
    def home(cls):
        return cls(r"C:\Users\Fallback")


def test_windows_localappdata(monkeypatch):
    """On Windows, %LOCALAPPDATA%/whisper is used when no XDG/HF override."""
    monkeypatch.setattr(app, "Path", _FakeWinPath)
    monkeypatch.setattr(app.os, "environ", {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"})
    monkeypatch.setattr(app.os, "name", "nt")
    assert app._whisper_cache_dir() == PureWindowsPath(r"C:\Users\Test\AppData\Local") / "whisper"


def test_windows_localappdata_missing_falls_back_to_home(monkeypatch):
    """On Windows with no LOCALAPPDATA, falls back to Path.home()/whisper."""
    monkeypatch.setattr(app, "Path", _FakeWinPath)
    monkeypatch.setattr(app.os, "environ", {})
    monkeypatch.setattr(app.os, "name", "nt")
    assert app._whisper_cache_dir() == PureWindowsPath(r"C:\Users\Fallback") / "whisper"
