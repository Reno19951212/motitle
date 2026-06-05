"""Platform-aware backend resolution for the output_lang pipeline.

Pure functions: given environment variables + detected platform, decide which
ASR engine / Ollama model / Ollama URL to use. macOS `auto` defaults reproduce
the historical hard-coded values exactly (byte-identical behaviour on Apple
Silicon). See docs/superpowers/specs/2026-06-06-cross-platform-delivery-design.md
"""

import platform
import shutil

_ARCH_MAP = {
    "arm64": "arm64", "aarch64": "arm64",
    "x86_64": "x86_64", "amd64": "x86_64", "AMD64": "x86_64",
}
_OS_MAP = {"Darwin": "darwin", "Windows": "win32", "Linux": "linux"}


def detect_platform() -> dict:
    """Return {'os': darwin|win32|linux, 'arch': arm64|x86_64, 'has_cuda': bool}."""
    os_name = _OS_MAP.get(platform.system(), platform.system().lower())
    arch = _ARCH_MAP.get(platform.machine(), platform.machine().lower())
    has_cuda = os_name != "darwin" and shutil.which("nvidia-smi") is not None
    return {"os": os_name, "arch": arch, "has_cuda": has_cuda}
