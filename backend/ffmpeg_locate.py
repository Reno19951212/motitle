"""Cross-platform ffmpeg/ffprobe discovery: PATH first, then per-OS fallbacks."""
import os
import shutil

_POSIX_FALLBACKS = [
    "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg",
]
_WIN_FALLBACKS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
]

_POSIX_FFPROBE_FALLBACKS = [
    "/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe", "/usr/bin/ffprobe",
]
_WIN_FFPROBE_FALLBACKS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffprobe.exe"),
    r"C:\ffmpeg\bin\ffprobe.exe",
    r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
]


def find_ffmpeg() -> str:
    """Absolute ffmpeg path if discoverable, else the bare name 'ffmpeg'."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidates = _WIN_FALLBACKS if os.name == "nt" else _POSIX_FALLBACKS
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "ffmpeg"


def find_ffprobe() -> str:
    """Absolute ffprobe path if discoverable, else the bare name 'ffprobe'."""
    found = shutil.which("ffprobe")
    if found:
        return found
    candidates = _WIN_FFPROBE_FALLBACKS if os.name == "nt" else _POSIX_FFPROBE_FALLBACKS
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "ffprobe"
