"""T1: output_languages in settings/registry snapshot.

Tests that:
1. When active_kind='output_lang' and 'output_languages' is written to settings,
   _register_file snapshots the list onto the file entry.
2. When 'output_languages' is absent from settings, _register_file defaults to [].
"""
import importlib
import pytest


@pytest.fixture
def app_mod(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import app as _a
    importlib.reload(_a)
    _a.app.config["R5_AUTH_BYPASS"] = True
    return _a


def test_register_file_snapshots_output_languages(app_mod, tmp_path):
    pm = app_mod._profile_manager
    saved = pm._read_settings()
    try:
        pm._write_settings({**saved, "active_kind": "output_lang", "active_id": "output_lang",
                            "output_languages": ["yue", "en"]})
        fid = "t-ol-1"
        app_mod._register_file(fid, "v.mp4", "v.mp4", 100, user_id=1)
        e = app_mod._file_registry[fid]
        assert e["active_kind"] == "output_lang"
        assert e["output_languages"] == ["yue", "en"]
    finally:
        pm._write_settings(saved)
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)


def test_register_file_missing_output_languages_defaults_empty(app_mod):
    pm = app_mod._profile_manager
    saved = pm._read_settings()
    try:
        pm._write_settings({k: v for k, v in saved.items() if k != "output_languages"})
        fid = "t-ol-2"
        app_mod._register_file(fid, "v.mp4", "v.mp4", 100, user_id=1)
        assert app_mod._file_registry[fid].get("output_languages", []) == []
    finally:
        pm._write_settings(saved)
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)
