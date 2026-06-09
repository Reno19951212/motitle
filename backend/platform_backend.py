"""Platform-aware backend resolution for the output_lang pipeline.

Pure functions: given environment variables + detected platform, decide which
ASR engine / Ollama model / Ollama URL to use. macOS `auto` defaults reproduce
the historical hard-coded values exactly (byte-identical behaviour on Apple
Silicon). See docs/superpowers/specs/2026-06-06-cross-platform-delivery-design.md
"""

import os
import platform
import shutil
import sys
from urllib.parse import urlparse

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
        device = "cuda" if info["has_cuda"] else "cpu"
        compute_type = "float16" if info["has_cuda"] else "int8"
        return {"asr": {"engine": "whispercpp", "model_size": "large-v3", "device": device, "compute_type": compute_type, "condition_on_previous_text": False}}
    device = "cuda" if choice == "cuda" else "cpu"
    compute_type = "float16" if choice == "cuda" else "int8"
    return {"asr": {"engine": "whisper", "model_size": "large-v3", "device": device, "compute_type": compute_type, "condition_on_previous_text": False}}


# ---------------------------------------------------------------------------
# Task 3: resolve_ollama_model
# ---------------------------------------------------------------------------

_OLLAMA_MODEL_DARWIN = "qwen3.5:35b-a3b-mlx-bf16"
_OLLAMA_MODEL_GGUF = "qwen3.5:35b-a3b"  # GGUF default tag; applies to all non-darwin platforms; Phase-0 validation may raise to q8_0


def resolve_ollama_model(env: dict, info: dict) -> str:
    """Return the Ollama model tag. R5_OLLAMA_MODEL overrides; else platform default.

    macOS default == the historical hard-coded MLX bf16 tag (byte-identical).
    """
    override = (env.get("R5_OLLAMA_MODEL") or "").strip()
    if override:
        return override
    return _OLLAMA_MODEL_DARWIN if info["os"] == "darwin" else _OLLAMA_MODEL_GGUF


# ---------------------------------------------------------------------------
# Task 4: resolve_ollama_url
# ---------------------------------------------------------------------------

_OLLAMA_URL_DEFAULT = "http://localhost:11434"


def resolve_ollama_url(env: dict) -> str:
    """Return the Ollama base URL. R5_OLLAMA_URL overrides; blank -> default.

    A set-but-malformed URL (missing http/https scheme or netloc) falls back to
    the default and prints a one-line warning to stderr. Blank/whitespace falls
    back silently (existing behaviour).
    """
    val = (env.get("R5_OLLAMA_URL") or "").strip()
    if not val:
        return _OLLAMA_URL_DEFAULT
    parsed = urlparse(val)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        print(
            "[platform_backend] WARNING: R5_OLLAMA_URL={!r} is not a valid "
            "http(s) URL; falling back to default {}".format(val, _OLLAMA_URL_DEFAULT),
            file=sys.stderr,
        )
        return _OLLAMA_URL_DEFAULT
    return val


# ---------------------------------------------------------------------------
# Task 5: resolve_subtitle_font_family  (subtitle burn-in CJK fallback)
# ---------------------------------------------------------------------------

# macOS subtitle burn-in runs through libass's CoreText provider. Two failure
# modes produce CJK tofu (□ Han glyphs, only ASCII digits survive):
#   1. ABSENT family ("Noto Sans TC", "Microsoft JhengHei", "Source Han Sans"):
#      not installed → CoreText substitutes Helvetica (Latin-only).
#   2. ON-DEMAND family ("PingFang *"): PingFang.ttc lives under
#      /System/Library/AssetsV2/ (downloadable font assets). The production
#      server runs as a LaunchDaemon with NO GUI/user session, and CoreText
#      cannot load AssetsV2 fonts without a session → it "matches" PingFang but
#      fails to load its glyphs → tofu. (Confirmed empirically 2026-06-09: a
#      daemon render with PingFang TC tofu'd; Heiti TC rendered cleanly. Even
#      bundling PingFang.ttc via :fontsdir= does not help — CoreText shadows it.)
# Both classes are remapped to STHeiti ("Heiti TC"/"Heiti SC"), which lives in
# /System/Library/Fonts/ PROPER and is therefore always fully loadable by a
# daemon. Other platforms keep the requested family (they ship their own Noto/
# Microsoft CJK fonts); unknown families (uploaded brand fonts via :fontsdir=,
# Hiragino, …) pass through untouched.
# NB: this is a RESCUE allowlist for legacy / out-of-band font values, not a
# complete CJK safety net — the font picker (available_subtitle_fonts) is the
# real guard that stops new bad picks. Any family here is remapped to the only
# daemon-loadable CJK faces (STHeiti). For serif/script source fonts (Songti,
# Kaiti) that means a sans substitution — accepted, since the alternative under
# a session-less daemon is tofu.
_DARWIN_CJK_FALLBACK = {
    # Absent web/Windows families (Traditional → Heiti TC)
    "noto sans tc": "Heiti TC",
    "noto sans hk": "Heiti TC",
    "noto sans cjk tc": "Heiti TC",
    "noto sans cjk hk": "Heiti TC",
    "source han sans tc": "Heiti TC",
    "source han sans hk": "Heiti TC",
    "microsoft jhenghei": "Heiti TC",  # JhengHei = Traditional Chinese
    # Absent web/Windows families (Simplified → Heiti SC)
    "noto sans sc": "Heiti SC",
    "noto sans cjk sc": "Heiti SC",
    "source han sans sc": "Heiti SC",
    "microsoft yahei": "Heiti SC",      # YaHei = Simplified Chinese
    # On-demand AssetsV2 families — "installed" but daemon-inaccessible.
    "pingfang tc": "Heiti TC",
    "pingfang hk": "Heiti TC",
    "pingfang sc": "Heiti SC",
    "songti tc": "Heiti TC",
    "kaiti tc": "Heiti TC",
    "songti sc": "Heiti SC",
    "kaiti sc": "Heiti SC",
    "stsong": "Heiti SC",
    "stkaiti": "Heiti SC",
    "stfangsong": "Heiti SC",
    "yuanti tc": "Heiti TC",
    "yuanti sc": "Heiti SC",
}


def resolve_subtitle_font_family(family, info: dict = None):
    """Map an absent / daemon-inaccessible CJK family to a daemon-safe one.

    The ASS Style 'Fontname' is handed to libass; on macOS an absent family
    (Noto/Microsoft/Source Han) OR an on-demand AssetsV2 family (PingFang, which
    a session-less LaunchDaemon cannot load) both yield Helvetica/tofu. On
    darwin we remap those to STHeiti ("Heiti TC"/"Heiti SC"), which lives in
    /System/Library/Fonts/ proper and is always loadable. Other platforms and
    any unrecognised family pass through unchanged.

    Empty / None / non-str inputs are returned as-is (the caller's defaulting
    logic owns those cases).
    """
    if not family or not isinstance(family, str):
        return family
    if info is None:
        info = detect_platform()
    if info.get("os") != "darwin":
        return family
    return _DARWIN_CJK_FALLBACK.get(family.strip().lower(), family)


# ---------------------------------------------------------------------------
# Task 6: available_subtitle_fonts  (font-picker source of truth)
# ---------------------------------------------------------------------------

# CJK subtitle fonts that the burn-in renderer can ACTUALLY use on each
# platform — i.e. that libass loads without producing tofu. The font picker is
# built from this list (plus uploaded fonts) so it never offers a family that
# would silently fall back.
#
# macOS: only families whose file lives in /System/Library/Fonts/ PROPER are
# included. PingFang / Songti / Kaiti etc. live under /System/Library/AssetsV2/
# (on-demand assets) and are DELIBERATELY excluded — the production server runs
# as a session-less LaunchDaemon and CoreText cannot load AssetsV2 fonts there
# (confirmed 2026-06-09). Each entry is runtime-verified by file existence.
# Heiti TC + Heiti SC (STHeiti) cover Traditional + Simplified and are both
# daemon-loadable. Hiragino Sans GB is deliberately NOT offered: it is GB
# (Simplified national-standard) oriented, so for this app's primary Traditional
# output it would render Simplified glyph variants — daemon-safe but typographically
# wrong. STHeiti's TC/SC split avoids that.
_MACOS_CJK_CANDIDATES = (
    ("Heiti TC", ("/System/Library/Fonts/STHeiti Medium.ttc",
                  "/System/Library/Fonts/STHeiti Light.ttc")),
    ("Heiti SC", ("/System/Library/Fonts/STHeiti Medium.ttc",
                  "/System/Library/Fonts/STHeiti Light.ttc")),
)
# Conventional bundled CJK families per OS. BEST-EFFORT ONLY — unlike the darwin
# list these are NOT file-verified (no Windows/Linux host to test against), so a
# fresh box missing them could still surface an unrenderable pick. Host-specific
# verification (Windows C:\Windows\Fonts\*.ttc, Linux fc-list) is a TODO once a
# non-macOS appliance exists. macOS is the only verified-correct platform today.
_WINDOWS_CJK = ("Microsoft JhengHei", "Microsoft YaHei", "MingLiU", "SimSun")
_LINUX_CJK = ("Noto Sans CJK TC", "Noto Sans CJK SC", "WenQuanYi Zen Hei")


def available_subtitle_fonts(info: dict = None) -> list:
    """Return the CJK system-font families usable by the burn-in renderer here.

    On darwin, only families whose file is present in /System/Library/Fonts/
    proper are returned (AssetsV2 on-demand fonts are excluded — a session-less
    daemon cannot load them). Other platforms return their conventional CJK
    families. The picker combines this with uploaded fonts (assets/fonts/).
    """
    if info is None:
        info = detect_platform()
    os_name = info.get("os")
    if os_name == "darwin":
        return [fam for fam, paths in _MACOS_CJK_CANDIDATES
                if any(os.path.exists(p) for p in paths)]
    if os_name == "win32":
        return list(_WINDOWS_CJK)
    return list(_LINUX_CJK)
