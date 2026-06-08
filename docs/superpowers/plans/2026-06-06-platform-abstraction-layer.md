# Platform Abstraction Layer Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard-coded Apple-MLX model selection in the `output_lang` pipeline with an env-driven, platform-auto-detecting backend-resolution layer — so the same code runs MLX on macOS and CUDA (faster-whisper + Ollama GGUF) on Windows/GB10 — while keeping macOS behaviour byte-identical.

**Architecture:** A new pure-function module `backend/platform_backend.py` resolves ASR engine config, Ollama model tag, and Ollama URL from environment variables with platform-aware defaults (`auto` → `darwin`=MLX, NVIDIA-present=CUDA, else CPU). `app.py`'s `_output_lang_asr_override()` and `_make_ollama_llm_call()` call this module instead of embedding constants. Engine validation becomes platform-aware. All resolution logic is unit-tested with mocked env/platform — no models required.

**Tech Stack:** Python 3.8+ (stdlib `os`, `platform`, `shutil`, `sysconfig`), pytest, existing `ASREngine`/`OllamaTranslationEngine` abstractions.

**Validation-First note:** This phase builds the *abstraction* (pure logic, mocked tests, macOS default unchanged) and does NOT itself certify the CUDA output. Enabling the CUDA path in production (Windows/GB10 actually transcribing/translating for delivery) is gated on the Phase 0 equivalence-validation evidence (see [design §3](../specs/2026-06-06-cross-platform-delivery-design.md)). Writing/merging this abstraction is safe because `auto` defaults reproduce the exact current macOS values.

**Prereq:** Run baseline tests green before starting (`cd backend && pytest tests/ -k "not api_" -q`).

---

### Task 1: `detect_platform()` — platform/arch/CUDA detection

**Files:**
- Create: `backend/platform_backend.py`
- Test: `backend/tests/test_platform_backend.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_platform_backend.py
import platform_backend as pb


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_platform_backend.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'platform_backend'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/platform_backend.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_platform_backend.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/platform_backend.py backend/tests/test_platform_backend.py
git commit -m "feat(platform): add detect_platform() backend detection"
```

---

### Task 2: `resolve_asr_override(env, info)` — ASR engine config per platform

**Files:**
- Modify: `backend/platform_backend.py`
- Test: `backend/tests/test_platform_backend.py`

- [ ] **Step 1: Write the failing test**

```python
def test_resolve_asr_auto_darwin_is_mlx_identical():
    info = {"os": "darwin", "arch": "arm64", "has_cuda": False}
    out = pb.resolve_asr_override({}, info)
    assert out == {"asr": {
        "engine": "mlx-whisper",
        "model_size": "large-v3",
        "condition_on_previous_text": False,
    }}


def test_resolve_asr_auto_cuda_is_faster_whisper():
    info = {"os": "win32", "arch": "x86_64", "has_cuda": True}
    out = pb.resolve_asr_override({}, info)
    assert out == {"asr": {
        "engine": "whisper",
        "model_size": "large-v3",
        "device": "cuda",
        "compute_type": "float16",
        "condition_on_previous_text": False,
    }}


def test_resolve_asr_auto_no_cuda_is_cpu():
    info = {"os": "linux", "arch": "x86_64", "has_cuda": False}
    out = pb.resolve_asr_override({}, info)
    assert out["asr"]["engine"] == "whisper"
    assert out["asr"]["device"] == "cpu"
    assert out["asr"]["compute_type"] == "int8"


def test_resolve_asr_env_override_forces_mlx_on_linux():
    info = {"os": "linux", "arch": "arm64", "has_cuda": True}
    out = pb.resolve_asr_override({"R5_ASR_BACKEND": "mlx"}, info)
    assert out["asr"]["engine"] == "mlx-whisper"


def test_resolve_asr_env_override_gb10_whispercpp():
    info = {"os": "linux", "arch": "arm64", "has_cuda": True}
    out = pb.resolve_asr_override({"R5_ASR_BACKEND": "whispercpp"}, info)
    assert out["asr"]["engine"] == "whispercpp"
    assert out["asr"]["device"] == "cuda"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_platform_backend.py -k resolve_asr -v`
Expected: FAIL — `AttributeError: module 'platform_backend' has no attribute 'resolve_asr_override'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to backend/platform_backend.py
def _asr_backend_choice(env: dict, info: dict) -> str:
    """Return one of: mlx | cuda | cpu | whispercpp."""
    val = (env.get("R5_ASR_BACKEND") or "auto").strip().lower()
    if val in ("mlx", "cuda", "cpu", "whispercpp"):
        return val
    # auto
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
        return {"asr": {
            "engine": "mlx-whisper",
            "model_size": "large-v3",
            "condition_on_previous_text": False,
        }}
    if choice == "whispercpp":
        return {"asr": {
            "engine": "whispercpp",
            "model_size": "large-v3",
            "device": "cuda",
            "compute_type": "float16",
            "condition_on_previous_text": False,
        }}
    device = "cuda" if choice == "cuda" else "cpu"
    compute_type = "float16" if choice == "cuda" else "int8"
    return {"asr": {
        "engine": "whisper",
        "model_size": "large-v3",
        "device": device,
        "compute_type": compute_type,
        "condition_on_previous_text": False,
    }}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_platform_backend.py -k resolve_asr -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/platform_backend.py backend/tests/test_platform_backend.py
git commit -m "feat(platform): resolve_asr_override() per-platform ASR config"
```

---

### Task 3: `resolve_ollama_model(env, info)` — LLM tag per platform

**Files:**
- Modify: `backend/platform_backend.py`
- Test: `backend/tests/test_platform_backend.py`

- [ ] **Step 1: Write the failing test**

```python
def test_resolve_ollama_model_darwin_is_mlx_bf16():
    info = {"os": "darwin", "arch": "arm64", "has_cuda": False}
    assert pb.resolve_ollama_model({}, info) == "qwen3.5:35b-a3b-mlx-bf16"


def test_resolve_ollama_model_non_darwin_is_gguf():
    info = {"os": "win32", "arch": "x86_64", "has_cuda": True}
    assert pb.resolve_ollama_model({}, info) == "qwen3.5:35b-a3b"


def test_resolve_ollama_model_env_override_wins():
    info = {"os": "win32", "arch": "x86_64", "has_cuda": True}
    assert pb.resolve_ollama_model(
        {"R5_OLLAMA_MODEL": "qwen3.5:35b-a3b-q8_0"}, info
    ) == "qwen3.5:35b-a3b-q8_0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_platform_backend.py -k resolve_ollama_model -v`
Expected: FAIL — `AttributeError: ... 'resolve_ollama_model'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to backend/platform_backend.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_platform_backend.py -k resolve_ollama_model -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/platform_backend.py backend/tests/test_platform_backend.py
git commit -m "feat(platform): resolve_ollama_model() per-platform LLM tag"
```

---

### Task 4: `resolve_ollama_url(env)` — single source of truth for Ollama endpoint

**Files:**
- Modify: `backend/platform_backend.py`
- Test: `backend/tests/test_platform_backend.py`

- [ ] **Step 1: Write the failing test**

```python
def test_resolve_ollama_url_default():
    assert pb.resolve_ollama_url({}) == "http://localhost:11434"


def test_resolve_ollama_url_env():
    assert pb.resolve_ollama_url(
        {"R5_OLLAMA_URL": "http://10.0.0.5:11434"}
    ) == "http://10.0.0.5:11434"


def test_resolve_ollama_url_blank_falls_back():
    assert pb.resolve_ollama_url({"R5_OLLAMA_URL": "  "}) == "http://localhost:11434"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_platform_backend.py -k resolve_ollama_url -v`
Expected: FAIL — `AttributeError: ... 'resolve_ollama_url'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to backend/platform_backend.py
_OLLAMA_URL_DEFAULT = "http://localhost:11434"


def resolve_ollama_url(env: dict) -> str:
    """Return the Ollama base URL. R5_OLLAMA_URL overrides; blank -> default."""
    val = (env.get("R5_OLLAMA_URL") or "").strip()
    return val or _OLLAMA_URL_DEFAULT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_platform_backend.py -k resolve_ollama_url -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/platform_backend.py backend/tests/test_platform_backend.py
git commit -m "feat(platform): resolve_ollama_url() single Ollama endpoint source"
```

---

### Task 5: Wire `app.py` to use `platform_backend` (macOS byte-identical regression)

**Files:**
- Modify: `backend/app.py:333-352` (`_output_lang_asr_override`, `_make_ollama_llm_call`)
- Test: `backend/tests/test_platform_backend_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_platform_backend_wiring.py
import importlib
import platform_backend as pb


def test_app_asr_override_matches_mlx_on_darwin(monkeypatch):
    """On darwin/auto, app._output_lang_asr_override must equal the historical dict."""
    monkeypatch.setattr(pb.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(pb.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(pb.shutil, "which", lambda name: None)
    import app
    importlib.reload(app)
    assert app._output_lang_asr_override() == {"asr": {
        "engine": "mlx-whisper",
        "model_size": "large-v3",
        "condition_on_previous_text": False,
    }}


def test_app_ollama_model_matches_mlx_on_darwin(monkeypatch):
    monkeypatch.setattr(pb.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(pb.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(pb.shutil, "which", lambda name: None)
    import app
    importlib.reload(app)
    eng = app._make_ollama_llm_call_engine()  # helper added in Step 3 for testability
    assert eng._model == "qwen3.5:35b-a3b-mlx-bf16"
    assert eng._base_url == "http://localhost:11434"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_platform_backend_wiring.py -v`
Expected: FAIL — `AttributeError: module 'app' has no attribute '_make_ollama_llm_call_engine'`

- [ ] **Step 3: Modify `app.py`**

Replace the body of `_output_lang_asr_override` (currently `app.py:340-344`) and `_make_ollama_llm_call` (currently `app.py:347-352`) with:

```python
def _output_lang_asr_override():
    """Return a FRESH override dict for the output-language ASR pass.

    Backend chosen by platform_backend (env R5_ASR_BACKEND + platform detect).
    macOS/auto == the validated mlx large-v3 cond=False dict (unchanged).
    """
    import platform_backend as _pb
    return _pb.resolve_asr_override(os.environ, _pb.detect_platform())


def _make_ollama_llm_call_engine():
    """Build the Ollama engine bound to the platform-resolved model + URL.

    Split out for testability; _make_ollama_llm_call wraps it into a callable.
    """
    import platform_backend as _pb
    from translation.ollama_engine import OllamaTranslationEngine
    info = _pb.detect_platform()
    eng = OllamaTranslationEngine({
        "engine": "qwen3.5-35b-a3b",
        "ollama_url": _pb.resolve_ollama_url(os.environ),
    })
    eng._model = _pb.resolve_ollama_model(os.environ, info)
    return eng


def _make_ollama_llm_call():
    """(system, user) -> str LLM client for cross-lang MT + the 書面語 refiner."""
    eng = _make_ollama_llm_call_engine()
    return lambda system, user: eng._call_ollama(system, user, 0.3)
```

> Note: `os` is already imported at the top of `app.py`. Do not change call sites of `_output_lang_asr_override()` / `_make_ollama_llm_call()` — their signatures are unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_platform_backend_wiring.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the broader suite to confirm no regression**

Run: `cd backend && pytest tests/ -k "not api_" -q`
Expected: PASS (same count as baseline; no new failures)

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_platform_backend_wiring.py
git commit -m "refactor(output_lang): platform-resolved ASR/LLM backend (macOS unchanged)"
```

---

### Task 6: Platform-aware ASR engine validation (reject MLX off-Apple)

**Files:**
- Modify: `backend/asr_profiles.py:22,26` (and the validation function that uses `VALID_ENGINES`)
- Test: `backend/tests/test_asr_profiles_platform.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_asr_profiles_platform.py
import asr_profiles


def test_available_engines_excludes_mlx_off_apple(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "win32")
    assert "mlx-whisper" not in asr_profiles.available_engines()
    assert "whisper" in asr_profiles.available_engines()


def test_available_engines_includes_mlx_on_apple(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "darwin")
    assert "mlx-whisper" in asr_profiles.available_engines()


def test_validate_rejects_mlx_engine_off_apple(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "linux")
    errors = asr_profiles.validate_asr_profile(
        {"name": "x", "engine": "mlx-whisper", "model_size": "large-v3", "mode": "same-lang"}
    )
    assert any("mlx-whisper" in e and "platform" in e.lower() for e in errors)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_asr_profiles_platform.py -v`
Expected: FAIL — `AttributeError: module 'asr_profiles' has no attribute 'available_engines'`

- [ ] **Step 3: Modify `asr_profiles.py`**

Add near the top (after the `VALID_*` constants):

```python
import platform as _platform_mod

_OS_NORMALIZE = {"Darwin": "darwin", "Windows": "win32", "Linux": "linux"}


def _detect_os() -> str:
    return _OS_NORMALIZE.get(_platform_mod.system(), _platform_mod.system().lower())


def available_engines() -> set:
    """VALID_ENGINES minus engines that cannot run on this platform.

    mlx-whisper requires Apple Silicon (MLX/Metal); excluded off darwin.
    """
    engines = set(VALID_ENGINES)
    if _detect_os() != "darwin":
        engines.discard("mlx-whisper")
    return engines
```

Then inside `validate_asr_profile`, where the engine field is currently checked against `VALID_ENGINES`, add a platform check. Locate the existing engine-validation block and add:

```python
    engine = data.get("engine")
    if engine == "mlx-whisper" and "mlx-whisper" not in available_engines():
        errors.append("engine 'mlx-whisper' is not supported on this platform (Apple Silicon only)")
```

> Keep the existing `VALID_ENGINES` membership check intact — this adds a platform gate on top of it.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_asr_profiles_platform.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run existing asr_profiles tests for regression**

Run: `cd backend && pytest tests/ -k "asr_profile" -q`
Expected: PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add backend/asr_profiles.py backend/tests/test_asr_profiles_platform.py
git commit -m "feat(asr): platform-aware engine availability (reject mlx off-Apple)"
```

---

### Task 7: OS-aware second-venv Python path

**Files:**
- Modify: `backend/engines/transcribe/qwen3_vad_engine.py:35`
- Test: `backend/tests/test_qwen_venv_path.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_qwen_venv_path.py
from engines.transcribe import qwen3_vad_engine as q


def test_venv_python_posix(monkeypatch):
    monkeypatch.setattr(q.os, "name", "posix")
    p = q.default_qwen_venv_python()
    assert p.name == "python"
    assert "bin" in p.parts


def test_venv_python_windows(monkeypatch):
    monkeypatch.setattr(q.os, "name", "nt")
    p = q.default_qwen_venv_python()
    assert p.name == "python.exe"
    assert "Scripts" in p.parts


def test_venv_python_env_override(monkeypatch):
    monkeypatch.setenv("V6_QWEN_VENV_PYTHON", "/custom/python")
    assert str(q.default_qwen_venv_python()) == "/custom/python"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_qwen_venv_path.py -v`
Expected: FAIL — `AttributeError: ... 'default_qwen_venv_python'`

- [ ] **Step 3: Modify `qwen3_vad_engine.py`**

Replace the hard-coded `_DEFAULT_QWEN_VENV_PYTHON` (line ~35) with a function:

```python
import os

def default_qwen_venv_python():
    """Path to the py3.11 Qwen3 subprocess interpreter, OS-aware + env-overridable."""
    override = os.environ.get("V6_QWEN_VENV_PYTHON")
    if override:
        from pathlib import Path
        return Path(override)
    venv = _REPO_ROOT / "backend" / "scripts" / "v5_prototype" / "venv_qwen"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"
```

Update every reference to `_DEFAULT_QWEN_VENV_PYTHON` to call `default_qwen_venv_python()` instead (search the file; also update the fallback in `app.py:1135` to import and call this function rather than rebuild the path).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_qwen_venv_path.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/engines/transcribe/qwen3_vad_engine.py backend/app.py backend/tests/test_qwen_venv_path.py
git commit -m "fix(v6): OS-aware Qwen3 subprocess venv path (Windows Scripts/)"
```

---

### Task 8: Cross-platform ffmpeg discovery + whisper cache path

**Files:**
- Modify: `backend/renderer.py:237-247`, `backend/waveform.py:46-58`, `backend/engines/transcribe/qwen3_vad_engine.py` (ffmpeg call), `backend/app.py:2122`
- Create: `backend/ffmpeg_locate.py`
- Test: `backend/tests/test_ffmpeg_locate.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_ffmpeg_locate.py
import ffmpeg_locate as fl


def test_find_ffmpeg_uses_which_first(monkeypatch):
    monkeypatch.setattr(fl.shutil, "which", lambda n: "/usr/bin/ffmpeg")
    assert fl.find_ffmpeg() == "/usr/bin/ffmpeg"


def test_find_ffmpeg_macos_homebrew_fallback(monkeypatch):
    monkeypatch.setattr(fl.shutil, "which", lambda n: None)
    monkeypatch.setattr(fl.os.path, "isfile", lambda p: p == "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(fl.os, "name", "posix")
    assert fl.find_ffmpeg() == "/opt/homebrew/bin/ffmpeg"


def test_find_ffmpeg_returns_bare_name_if_nothing(monkeypatch):
    monkeypatch.setattr(fl.shutil, "which", lambda n: None)
    monkeypatch.setattr(fl.os.path, "isfile", lambda p: False)
    assert fl.find_ffmpeg() == "ffmpeg"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_ffmpeg_locate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ffmpeg_locate'`

- [ ] **Step 3: Write `ffmpeg_locate.py`**

```python
# backend/ffmpeg_locate.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_ffmpeg_locate.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Wire callers + fix whisper cache path**

In `renderer.py`, `waveform.py`, and `qwen3_vad_engine.py`, replace the local ffmpeg-path logic / bare `"ffmpeg"` subprocess arg with `from ffmpeg_locate import find_ffmpeg` and call `find_ffmpeg()`. In `app.py:2122`, replace `Path.home() / '.cache' / 'whisper'` with a cross-platform cache dir:

```python
def _whisper_cache_dir():
    import os
    from pathlib import Path
    env = os.environ.get("XDG_CACHE_HOME") or os.environ.get("HF_HOME")
    if env:
        return Path(env) / "whisper"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "whisper"
    return Path.home() / ".cache" / "whisper"
```

- [ ] **Step 6: Run full suite for regression**

Run: `cd backend && pytest tests/ -k "not api_" -q`
Expected: PASS (no new failures)

- [ ] **Step 7: Commit**

```bash
git add backend/ffmpeg_locate.py backend/renderer.py backend/waveform.py backend/engines/transcribe/qwen3_vad_engine.py backend/app.py backend/tests/test_ffmpeg_locate.py
git commit -m "fix(platform): cross-platform ffmpeg discovery + whisper cache dir"
```

---

## Self-Review (against the design spec)

**Spec coverage (design §2 decisions):**
- D1 (env-driven backend resolution) → Tasks 1–5 ✅
- D2 (ASR engine strategy; GB10 `whispercpp` placeholder accepted by resolver) → Task 2 ✅ (GB10 engine *implementation* is Phase 4, out of this plan's scope by design)
- D3 (LLM GGUF tag) → Tasks 3, 5 ✅
- D4 (platform-aware validation) → Task 6 ✅
- D5 (path fixes: venv, ffmpeg, cache) → Tasks 7, 8 ✅
- D7 (async_mode env) → **deferred to Phase 2 (Windows packaging)** where threading-vs-gevent is exercised on a real server; not needed for the abstraction layer. Noted, not a gap.

**Placeholder scan:** No TBD/TODO; every code step shows full code. ✅

**Type consistency:** `detect_platform()` returns `{os, arch, has_cuda}` used consistently in Tasks 2/3/5. `resolve_asr_override`/`resolve_ollama_model` take `(env, info)`; `resolve_ollama_url` takes `(env)` — consistent across tasks. ✅

**macOS regression guard:** Task 5 Steps 1/4 assert byte-identical mlx dict + mlx-bf16 tag on darwin/auto; Step 5 runs the broader suite. ✅

**Out of scope (by design, become their own plans):** Phase 0 validation matrix run, Phase 2 Windows packaging (NSSM/Inno/threading/start-win.ps1/whisper-streaming exclusion), Phase 3 macOS launchd packaging, Phase 4 GB10 (whispercpp engine + Docker/NGC), Phase 5 CI + pinned requirements + CDN localization + delete proofread.old.html.
