import os
import sys
from pathlib import Path

import pytest

# R5 Phase 5 T1.3 — app.py raises RuntimeError on import if FLASK_SECRET_KEY
# is unset or is the placeholder. Set a non-placeholder test value before any
# `import app` happens. Tests that need to verify the boot-time check can
# still monkeypatch.delenv() and force a reload (see test_phase5_security).
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-only-for-pytest-do-not-deploy")


def pytest_configure(config):
    """Register custom pytest markers so ``-W error::pytest.PytestUnknownMarkWarning``
    does not fire and ``--strict-markers`` mode is compatible.

    real_auth:
        Mark a test (or an entire class / module) to opt out of the global
        AUTH_BYPASS shortcut that most tests rely on.  Tests decorated with
        this marker run with LOGIN_DISABLED=False and R5_AUTH_BYPASS=False,
        exercising the real session / permission layer.

        Usage::

            @pytest.mark.real_auth
            def test_admin_only_endpoint(client):
                ...

        The legacy ``_REAL_AUTH_MODULES`` tuple in ``_isolate_app_data`` acts
        as a backward-compat fallback so existing test modules don't need to
        be annotated immediately.  New tests should prefer the marker.
    """
    config.addinivalue_line(
        "markers",
        "real_auth: disable AUTH_BYPASS so real login/permission checks run",
    )

sys.path.insert(0, str(Path(__file__).parent.parent))


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
    # is_admin.
    #
    # Two ways a test opts into real auth (either is sufficient):
    #   1. Legacy: test module filename is in _REAL_AUTH_MODULES (backward compat).
    #   2. New:    test is decorated with @pytest.mark.real_auth.
    # "test_phase5_security" migrated to @pytest.mark.real_auth — removed from tuple.
    _REAL_AUTH_MODULES = ("test_admin_users", "test_per_user_glossaries", "test_queue_retry", "test_files_job_id", "test_cancel_running", "test_phase5_ownership", "test_render_ownership")
    _use_real_auth = (
        any(m in str(request.fspath) for m in _REAL_AUTH_MODULES)
        or request.node.get_closest_marker("real_auth") is not None
    )
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
