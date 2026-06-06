import ffmpeg_locate as fl


def test_find_ffmpeg_uses_which_first(monkeypatch):
    monkeypatch.setattr(fl.shutil, "which", lambda n: "/usr/bin/ffmpeg")
    assert fl.find_ffmpeg() == "/usr/bin/ffmpeg"


def test_find_ffmpeg_macos_homebrew_fallback(monkeypatch):
    monkeypatch.setattr(fl.shutil, "which", lambda n: None)
    monkeypatch.setattr(fl.os, "name", "posix")
    monkeypatch.setattr(fl.os.path, "isfile", lambda p: p == "/opt/homebrew/bin/ffmpeg")
    assert fl.find_ffmpeg() == "/opt/homebrew/bin/ffmpeg"


def test_find_ffmpeg_usr_local_bin_fallback(monkeypatch):
    monkeypatch.setattr(fl.shutil, "which", lambda n: None)
    monkeypatch.setattr(fl.os, "name", "posix")
    monkeypatch.setattr(fl.os.path, "isfile", lambda p: p == "/usr/local/bin/ffmpeg")
    assert fl.find_ffmpeg() == "/usr/local/bin/ffmpeg"


def test_find_ffmpeg_windows_fallback(monkeypatch):
    monkeypatch.setattr(fl.shutil, "which", lambda n: None)
    monkeypatch.setattr(fl.os, "name", "nt")
    target = fl._WIN_FALLBACKS[0]
    monkeypatch.setattr(fl.os.path, "isfile", lambda p: p == target)
    assert fl.find_ffmpeg() == target


def test_find_ffmpeg_returns_bare_name_if_nothing(monkeypatch):
    monkeypatch.setattr(fl.shutil, "which", lambda n: None)
    monkeypatch.setattr(fl.os.path, "isfile", lambda p: False)
    assert fl.find_ffmpeg() == "ffmpeg"


def test_find_ffprobe_uses_which_first(monkeypatch):
    monkeypatch.setattr(fl.shutil, "which", lambda n: "/usr/bin/ffprobe")
    assert fl.find_ffprobe() == "/usr/bin/ffprobe"


def test_find_ffprobe_macos_homebrew_fallback(monkeypatch):
    monkeypatch.setattr(fl.shutil, "which", lambda n: None)
    monkeypatch.setattr(fl.os, "name", "posix")
    monkeypatch.setattr(fl.os.path, "isfile", lambda p: p == "/opt/homebrew/bin/ffprobe")
    assert fl.find_ffprobe() == "/opt/homebrew/bin/ffprobe"


def test_find_ffprobe_returns_bare_name_if_nothing(monkeypatch):
    monkeypatch.setattr(fl.shutil, "which", lambda n: None)
    monkeypatch.setattr(fl.os.path, "isfile", lambda p: False)
    assert fl.find_ffprobe() == "ffprobe"
