import pytest
import app as app_mod
from licensing import validator


def test_asr_handler_refuses_when_locked(monkeypatch):
    # Force locked regardless of license.json.
    monkeypatch.setattr(validator, "evaluate",
                        lambda *a, **k: validator.LicenseStatus("none", False, "test"))
    with pytest.raises(RuntimeError, match="licence"):
        app_mod._license_guard_or_raise()
