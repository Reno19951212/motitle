"""Licence gate for the SocketIO `load_model` event (follow-up).

The HTTP before_request gate does not cover SocketIO events, so the
load_model handler — which warms a Whisper model into memory (AI-adjacent
compute) — must check the licence itself. When unlicensed it emits
model_error and does NOT load. Shared bypass-aware predicate `_license_ok()`
backs both this handler and the worker guard.

Run in isolation (suite has known order-dependent failures):
  pytest tests/test_license_load_model.py -q
"""
import threading

import app as app_mod
from licensing import validator


# --------------------------------------------------------------------------
# _license_ok() — bypass-aware predicate shared by the guard + load_model
# --------------------------------------------------------------------------

def test_license_ok_true_when_bypass(monkeypatch):
    monkeypatch.setitem(app_mod.app.config, "R5_LICENSE_BYPASS", True)
    monkeypatch.setattr(validator, "evaluate",
                        lambda *a, **k: validator.LicenseStatus("none", False, "x"))
    assert app_mod._license_ok() is True


def test_license_ok_false_when_locked(monkeypatch):
    monkeypatch.setitem(app_mod.app.config, "R5_LICENSE_BYPASS", False)
    monkeypatch.setattr(validator, "evaluate",
                        lambda *a, **k: validator.LicenseStatus("none", False, "x"))
    assert app_mod._license_ok() is False


def test_license_ok_true_when_unlocked(monkeypatch):
    monkeypatch.setitem(app_mod.app.config, "R5_LICENSE_BYPASS", False)
    monkeypatch.setattr(validator, "evaluate",
                        lambda *a, **k: validator.LicenseStatus("active", True, "x"))
    assert app_mod._license_ok() is True


# --------------------------------------------------------------------------
# load_model SocketIO event gating
# --------------------------------------------------------------------------

def _sio_client():
    flask_client = app_mod.app.test_client()
    return app_mod.socketio.test_client(app_mod.app, flask_test_client=flask_client)


def test_load_model_blocked_when_unlicensed(monkeypatch):
    # Connect is allowed via R5_AUTH_BYPASS (conftest default); the licence
    # gate is ON and locked.
    monkeypatch.setitem(app_mod.app.config, "R5_LICENSE_BYPASS", False)
    monkeypatch.setattr(validator, "evaluate",
                        lambda *a, **k: validator.LicenseStatus("none", False, "x"))
    called = {"get_model": False}
    monkeypatch.setattr(app_mod, "get_model",
                        lambda *a, **k: called.__setitem__("get_model", True))

    sio = _sio_client()
    assert sio.is_connected()
    sio.emit("load_model", {"model": "small"})
    names = {r["name"] for r in sio.get_received()}
    sio.disconnect()

    assert "model_error" in names
    assert "model_loading" not in names
    assert called["get_model"] is False


def test_load_model_allowed_when_licensed(monkeypatch):
    monkeypatch.setitem(app_mod.app.config, "R5_LICENSE_BYPASS", True)
    done = threading.Event()
    monkeypatch.setattr(app_mod, "get_model",
                        lambda *a, **k: (done.set(), object())[1])

    sio = _sio_client()
    assert sio.is_connected()
    sio.emit("load_model", {"model": "small"})
    assert done.wait(timeout=5), "get_model must be called when licensed"
    names = {r["name"] for r in sio.get_received()}
    sio.disconnect()

    assert "model_loading" in names
