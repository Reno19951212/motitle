# backend/beta_mode.py
"""Central state + constants for the Admin Beta test mode (OpenRouter cloud models).

Beta mode is a single global flag (settings.json 'beta_openrouter'). When ON, the
output_lang pipeline's LLM routes to OpenRouter instead of local Ollama. ASR always
stays local (mlx-whisper). The LLM model id is hardcoded parity with the local stack.
"""
import os
import tempfile
from pathlib import Path

# Hardcoded parity with the local production stack (not user-editable).
BETA_LLM_MODEL = "qwen/qwen3.5-35b-a3b"

_ENV_PATH = Path(__file__).parent / ".env"   # backend/.env (gitignored)
_KEY_NAME = "OPENROUTER_API_KEY"


def key_status() -> bool:
    """True when an OpenRouter API key is present in the environment.

    Reads from os.environ only. A key written by set_key() is live immediately
    (set_key also calls os.environ); after a server restart it is only visible
    if .env is loaded into the environment at startup."""
    return bool(os.environ.get(_KEY_NAME))


def set_key(key: str) -> None:
    """Persist OPENROUTER_API_KEY to backend/.env (preserving other lines) and set
    it in os.environ so the running process picks it up immediately."""
    key = (key or "").strip()
    if not key:
        raise ValueError("OpenRouter API key cannot be empty")
    _write_env_var(_ENV_PATH, _KEY_NAME, key)
    os.environ[_KEY_NAME] = key


def _write_env_var(path: Path, name: str, value: str) -> None:
    """Set name=value in a .env file, preserving every other line. Creates the file
    if missing. Builds a NEW content string (no in-place mutation)."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = name + "="
    new_line = f"{name}={value}"
    out, replaced = [], False
    for ln in lines:
        if ln.startswith(prefix):
            out.append(new_line)
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append(new_line)
    # .env holds secrets (FLASK_SECRET_KEY, OPENROUTER_API_KEY). Write atomically
    # via a same-dir temp file that is 0o600 FROM CREATION (mkstemp), so the secret
    # is never world-readable — not even briefly. os.replace then gives the live
    # .env the temp's 0o600 perms (os.replace inherits the source's mode); the final
    # os.chmod is belt-and-suspenders.
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
