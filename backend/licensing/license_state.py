"""The only module that reads/writes config/license.json.

Schema: {install_id, token?, last_seen, activated_at?}
"""
import json
import os
import uuid
from pathlib import Path
from typing import Optional

# Default: backend/config/license.json. Tests monkeypatch this.
LICENSE_PATH = Path(__file__).resolve().parent.parent / "config" / "license.json"

# Only persist last_seen if it advances by more than this (bounds disk writes).
_RATCHET_THROTTLE_SEC = 3600


def _read() -> dict:
    try:
        return json.loads(LICENSE_PATH.read_text())
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _write(data: dict) -> None:
    LICENSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LICENSE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, LICENSE_PATH)


def get_or_create_install_id() -> str:
    data = _read()
    iid = data.get("install_id")
    if not iid:
        iid = uuid.uuid4().hex
        data["install_id"] = iid
        _write(data)
    return iid


def read_token() -> Optional[str]:
    return _read().get("token") or None


def read_last_seen() -> float:
    try:
        return float(_read().get("last_seen", 0.0))
    except (TypeError, ValueError):
        return 0.0


def bump_last_seen(now: float) -> None:
    data = _read()
    last = float(data.get("last_seen", 0.0) or 0.0)
    if now > last + _RATCHET_THROTTLE_SEC or last == 0.0:
        data["last_seen"] = now
        _write(data)


def save_token(token: str, now: float) -> None:
    data = _read()
    if not data.get("install_id"):
        data["install_id"] = uuid.uuid4().hex
    data["token"] = token
    data["activated_at"] = now
    data["last_seen"] = max(float(data.get("last_seen", 0.0) or 0.0), now)
    _write(data)


def clear_token() -> None:
    data = _read()
    data.pop("token", None)
    data.pop("activated_at", None)
    _write(data)
