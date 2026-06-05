"""Tests for platform_backend.py — Tasks 1–4.

TDD: tests were written before the implementation.
Run from backend/ with:
  python -m pytest tests/test_platform_backend.py -v
"""

import platform_backend as pb


# ---------------------------------------------------------------------------
# Task 1: detect_platform()
# ---------------------------------------------------------------------------

def test_detect_platform_darwin_arm64(monkeypatch):
    monkeypatch.setattr(pb.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(pb.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(pb.shutil, "which", lambda name: None)
    info = pb.detect_platform()
    assert info == {"os": "darwin", "arch": "arm64", "has_cuda": False}


def test_detect_platform_windows_cuda(monkeypatch):
    monkeypatch.setattr(pb.platform, "system", lambda: "Windows")
    monkeypatch.setattr(pb.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(pb.shutil, "which", lambda name: "C:/Windows/System32/nvidia-smi.exe" if name == "nvidia-smi" else None)
    info = pb.detect_platform()
    assert info == {"os": "win32", "arch": "x86_64", "has_cuda": True}


def test_detect_platform_linux_arm64_cuda(monkeypatch):
    monkeypatch.setattr(pb.platform, "system", lambda: "Linux")
    monkeypatch.setattr(pb.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(pb.shutil, "which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)
    info = pb.detect_platform()
    assert info == {"os": "linux", "arch": "arm64", "has_cuda": True}
