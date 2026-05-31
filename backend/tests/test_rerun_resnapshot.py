"""Re-run re-snapshots the CURRENT active pipeline onto the file (2026-05-31)."""
import importlib
import pytest

CANTO = "4696bbaa-b988-49bd-859c-e742cb365634"   # 口語 (1 refiner)
WRITTEN = "1443afcb-198b-4821-8e64-47d02bf877f3"  # 書面語 (2 refiners)


@pytest.fixture
def admin_app(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import app as _app
    importlib.reload(_app)
    _app.app.config["R5_AUTH_BYPASS"] = True
    return _app


def test_rerun_resnapshots_to_current_v6_pipeline(admin_app):
    app = admin_app
    fid = "test-rerun-1"
    with app._registry_lock:
        app._file_registry[fid] = {
            "id": fid, "user_id": 1, "status": "done",
            "active_kind": "pipeline_v6", "active_id": CANTO,
            "active_pipeline_snapshot": {"id": CANTO, "name": "old"},
        }
    pm = app._profile_manager
    saved = pm._read_settings()
    try:
        # User switches the strip to the 書面語 pipeline (global active). V6
        # active is a settings write (POST /api/active path); set_active() only
        # handles profile kind.
        pm._write_settings({**saved, "active_kind": "pipeline_v6",
                            "active_id": WRITTEN, "active_profile": WRITTEN})
        app._resnapshot_active_for_rerun(fid)
        e = app._file_registry[fid]
        assert e["active_kind"] == "pipeline_v6"
        assert e["active_id"] == WRITTEN
        assert (e.get("active_pipeline_snapshot") or {}).get("id") == WRITTEN
    finally:
        pm._write_settings(saved)
        with app._registry_lock:
            app._file_registry.pop(fid, None)


def test_rerun_resnapshots_to_profile_clears_pipeline_snapshot(admin_app):
    app = admin_app
    fid = "test-rerun-2"
    with app._registry_lock:
        app._file_registry[fid] = {
            "id": fid, "user_id": 1, "status": "done",
            "active_kind": "pipeline_v6", "active_id": WRITTEN,
            "active_pipeline_snapshot": {"id": WRITTEN, "name": "old"},
        }
    pm = app._profile_manager
    saved = pm._read_settings()
    try:
        pm.set_active("prod-default")  # profile kind, single-arg API
        app._resnapshot_active_for_rerun(fid)
        e = app._file_registry[fid]
        assert e["active_kind"] == "profile"
        assert e["active_id"] == "prod-default"
        assert e.get("active_pipeline_snapshot") is None
    finally:
        pm._write_settings(saved)
        with app._registry_lock:
            app._file_registry.pop(fid, None)
