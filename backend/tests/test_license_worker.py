"""Defense-in-depth worker guard (Task 8).

Verifies BOTH layers:
  1. The helper `_license_guard_or_raise()` raises when the licence is locked.
  2. The wiring — `_asr_handler` and `_mt_handler` (the registered worker
     entry points) actually call the guard FIRST, so any AI job (ASR,
     profile MT, and the translate-second LLM sub-path) fails fast if the
     licence lapses mid-session.
"""
import pytest
import app as app_mod
from licensing import validator


def _force_locked(monkeypatch):
    """Force `evaluate()` to report locked regardless of license.json."""
    monkeypatch.setattr(
        validator, "evaluate",
        lambda *a, **k: validator.LicenseStatus("none", False, "test"))


def _force_unlocked(monkeypatch):
    """Force `evaluate()` to report unlocked so the guard is a no-op."""
    monkeypatch.setattr(
        validator, "evaluate",
        lambda *a, **k: validator.LicenseStatus("active", True, "test"))


def test_license_guard_or_raise_refuses_when_locked(monkeypatch):
    _force_locked(monkeypatch)
    with pytest.raises(RuntimeError, match="licence"):
        app_mod._license_guard_or_raise()


def test_license_guard_or_raise_passes_when_unlocked(monkeypatch):
    _force_unlocked(monkeypatch)
    # No exception → the guard is a no-op when unlocked.
    assert app_mod._license_guard_or_raise() is None


def test_asr_handler_calls_guard_first_when_locked(monkeypatch):
    """_asr_handler must refuse BEFORE touching the registry.

    Passing a job with no "file_id" means that if the guard did NOT run
    first, the handler would raise KeyError("file_id"). A RuntimeError that
    mentions "licence" proves the guard ran as the handler's first action.
    """
    _force_locked(monkeypatch)
    with pytest.raises(RuntimeError, match="licence"):
        app_mod._asr_handler({})


def test_mt_handler_calls_guard_first_when_locked(monkeypatch):
    """_mt_handler must refuse BEFORE branching to any AI sub-path.

    This covers all three branches reachable from _mt_handler — the
    translate-second LLM path (_translate_second_handler), the V6
    short-circuit, and the profile path (_auto_translate) — uniformly,
    because the guard is the handler's first statement. As with the ASR
    case, the empty job would raise KeyError("file_id") if the guard did
    not run first.
    """
    _force_locked(monkeypatch)
    with pytest.raises(RuntimeError, match="licence"):
        app_mod._mt_handler({})
