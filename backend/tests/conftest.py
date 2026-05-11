import os
import sys
from pathlib import Path

import pytest

# R5 Phase 5 T1.3 — app.py raises RuntimeError on import if FLASK_SECRET_KEY
# is unset or is the placeholder. Set a non-placeholder test value before any
# `import app` happens. Tests that need to verify the boot-time check can
# still monkeypatch.delenv() and force a reload (see test_phase5_security).
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-only-for-pytest-do-not-deploy")

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def _sync_imported_manager_refs(request, monkeypatch):
    """Ensure module-level manager references imported by test modules stay in
    sync with any monkeypatches applied by test-local fixtures.

    Some test modules do ``from app import _profile_manager`` at module load
    time.  When a test-local fixture later replaces ``app._profile_manager``
    via ``monkeypatch.setattr``, the test module's cached reference is stale
    and won't see profiles created via the patched manager.

    This fixture requests the ``client`` fixture (if present for the test) so
    that the test-local patch is applied first, then re-binds the stale names
    in the test module to match the now-current ``app._profile_manager``.
    """
    # Only act for tests in modules that import _profile_manager from app
    _MODULES_NEEDING_SYNC = ('test_languages_crud', 'test_subtitle_source_mode')
    if not any(m in str(request.fspath) for m in _MODULES_NEEDING_SYNC):
        yield
        return

    # Trigger the 'client' fixture (idempotent — pytest caches it) so that
    # the test-local monkeypatch for app._profile_manager is in place before
    # we forward the reference.
    try:
        request.getfixturevalue('client')
    except pytest.FixtureLookupError:
        yield
        return

    try:
        import app as _app
        import importlib
        test_mod_name = Path(request.fspath).stem
        try:
            test_mod = importlib.import_module(f'tests.{test_mod_name}')
        except ModuleNotFoundError:
            test_mod = importlib.import_module(test_mod_name)
        if hasattr(test_mod, '_profile_manager'):
            monkeypatch.setattr(test_mod, '_profile_manager', _app._profile_manager)
    except (ImportError, AttributeError):
        pass

    yield


@pytest.fixture(autouse=True)
def _isolate_app_data(request, tmp_path, monkeypatch):
    """Auto-isolate every test from the real DATA_DIR.

    Prevents tests from overwriting backend/data/registry.json when they
    call API endpoints that invoke _save_registry(). Applies to every test
    in the suite without requiring opt-in from individual fixtures.

    Tests that don't depend on the Flask app (e.g. rebuild_registry unit
    tests) still run when Flask is unavailable — the isolation just
    becomes a no-op for them.
    """
    try:
        import app
        from renderer import SubtitleRenderer
    except ImportError:
        yield
        return

    test_data_dir = tmp_path / "data"
    (test_data_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (test_data_dir / "renders").mkdir(exist_ok=True)
    (test_data_dir / "results").mkdir(exist_ok=True)

    monkeypatch.setattr(app, "DATA_DIR", test_data_dir)
    monkeypatch.setattr(app, "UPLOAD_DIR", test_data_dir / "uploads")
    monkeypatch.setattr(app, "RENDERS_DIR", test_data_dir / "renders")
    monkeypatch.setattr(app, "RESULTS_DIR", test_data_dir / "results")

    # R5 Phase 1: existing tests don't authenticate, so bypass auth gates.
    # LOGIN_DISABLED makes flask_login.@login_required pass through.
    # R5_AUTH_BYPASS makes our @require_file_owner / @admin_required wrappers
    # short-circuit (otherwise they'd hit AnonymousUserMixin.is_admin AttributeError).
    #
    # R5 Phase 3: admin route tests (test_admin_users.py) use real sessions and
    # real auth checks — bypass must NOT be active so @admin_required enforces
    # is_admin. Detect by checking the test module name.
    _REAL_AUTH_MODULES = ("test_admin_users", "test_per_user_profiles", "test_per_user_glossaries", "test_queue_retry", "test_files_job_id", "test_cancel_running", "test_phase5_security", "test_phase5_ownership", "test_render_ownership")
    _use_real_auth = any(m in str(request.fspath) for m in _REAL_AUTH_MODULES)
    monkeypatch.setitem(app.app.config, "RATELIMIT_ENABLED", False)
    if not _use_real_auth:
        monkeypatch.setitem(app.app.config, "LOGIN_DISABLED", True)
        monkeypatch.setitem(app.app.config, "R5_AUTH_BYPASS", True)

    # Also replace the module-level _subtitle_renderer instance, which was
    # constructed at import time with the real RENDERS_DIR.
    monkeypatch.setattr(
        app,
        "_subtitle_renderer",
        SubtitleRenderer(test_data_dir / "renders"),
    )

    # Snapshot and clear the registry under the same lock production code uses.
    with app._registry_lock:
        original_registry = app._file_registry.copy()
        app._file_registry.clear()

    yield

    with app._registry_lock:
        app._file_registry.clear()
        app._file_registry.update(original_registry)
