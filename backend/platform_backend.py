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


# ---------------------------------------------------------------------------
# Task 2: resolve_asr_override
# ---------------------------------------------------------------------------

def _asr_backend_choice(env: dict, info: dict) -> str:
    """Return one of: mlx | cuda | cpu | whispercpp."""
    val = (env.get("R5_ASR_BACKEND") or "auto").strip().lower()
    if val in ("mlx", "cuda", "cpu", "whispercpp"):
        return val
    if info["os"] == "darwin":
        return "mlx"
    return "cuda" if info["has_cuda"] else "cpu"


def resolve_asr_override(env: dict, info: dict) -> dict:
    """Return the FRESH asr override dict for the output_lang pipeline.

    Replaces app._output_lang_asr_override()'s hard-coded body. macOS/auto
    reproduces the historical mlx-whisper large-v3 (cond=False) dict exactly.
    """
    choice = _asr_backend_choice(env, info)
    if choice == "mlx":
        return {"asr": {"engine": "mlx-whisper", "model_size": "large-v3", "condition_on_previous_text": False}}
    if choice == "whispercpp":
        return {"asr": {"engine": "whispercpp", "model_size": "large-v3", "device": "cuda", "compute_type": "float16", "condition_on_previous_text": False}}
    device = "cuda" if choice == "cuda" else "cpu"
    compute_type = "float16" if choice == "cuda" else "int8"
    return {"asr": {"engine": "whisper", "model_size": "large-v3", "device": device, "compute_type": compute_type, "condition_on_previous_text": False}}


# ---------------------------------------------------------------------------
# Task 3: resolve_ollama_model
# ---------------------------------------------------------------------------

_OLLAMA_MODEL_DARWIN = "qwen3.5:35b-a3b-mlx-bf16"
_OLLAMA_MODEL_CUDA = "qwen3.5:35b-a3b"  # GGUF default tag; Phase-0 validation may raise to q8_0


def resolve_ollama_model(env: dict, info: dict) -> str:
    """Return the Ollama model tag. R5_OLLAMA_MODEL overrides; else platform default.

    macOS default == the historical hard-coded MLX bf16 tag (byte-identical).
    """
    override = (env.get("R5_OLLAMA_MODEL") or "").strip()
    if override:
        return override
    return _OLLAMA_MODEL_DARWIN if info["os"] == "darwin" else _OLLAMA_MODEL_CUDA
