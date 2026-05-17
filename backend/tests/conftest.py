import os
import shutil
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

    # v4.0 A5 T10 — isolate v4 manager storage from the real
    # backend/config/{asr_profiles,mt_profiles,pipelines,glossaries} dirs.
    # Without this, every test that hit /api/asr_profiles or
    # /api/mt_profiles or /api/pipelines etc. left junk JSONs in the
    # real config tree. Strategy:
    #
    #   1. Build tmp_path/config/<sub> for every subdir managers expect.
    #   2. Seed read-only data (languages/, prompt_templates/) by copy
    #      so list / get endpoints still return real shapes.
    #   3. Re-instantiate each manager pointed at the tmp config dir
    #      and swap them onto the live app module.
    #   4. Re-wire decorators with the fresh managers so
    #      @require_asr_profile_owner etc. consult them.
    #
    # Approach B (monkeypatch managers) chosen over module reload
    # because many tests do `import app as app_mod` and hold module-
    # level references; a reload would invalidate those.
    test_config_dir = tmp_path / "config"
    test_config_dir.mkdir(parents=True, exist_ok=True)
    for sub in (
        "asr_profiles",
        "mt_profiles",
        "pipelines",
        "glossaries",
        "languages",
        "prompt_templates",
    ):
        (test_config_dir / sub).mkdir(exist_ok=True)

    # Seed read-only assets so language/prompt-template endpoints have
    # data to return. We DO NOT copy glossaries/ or *_profiles/ — those
    # are exactly the dirs tests pollute, and the isolation is meant to
    # start each test from an empty slate.
    real_config = Path(__file__).resolve().parent.parent / "config"
    for src_sub in ("languages", "prompt_templates"):
        src = real_config / src_sub
        if src.exists():
            dst = test_config_dir / src_sub
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)

    # Set env var so any *fresh* imports (rare) also see the tmp path.
    monkeypatch.setenv("R5_CONFIG_DIR", str(test_config_dir))

    # Swap CONFIG_DIR on the live module + replace each manager.
    monkeypatch.setattr(app, "CONFIG_DIR", test_config_dir)

    from glossary import GlossaryManager
    from language_config import LanguageConfigManager
    from asr_profiles import ASRProfileManager
    from mt_profiles import MTProfileManager
    from pipelines import PipelineManager

    fresh_glossary = GlossaryManager(test_config_dir)
    fresh_language = LanguageConfigManager(test_config_dir)
    fresh_asr = ASRProfileManager(test_config_dir)
    fresh_mt = MTProfileManager(test_config_dir)
    fresh_pipeline = PipelineManager(
        test_config_dir,
        asr_manager=fresh_asr,
        mt_manager=fresh_mt,
        glossary_manager=fresh_glossary,
    )

    monkeypatch.setattr(app, "_glossary_manager", fresh_glossary)
    monkeypatch.setattr(app, "_language_config_manager", fresh_language)
    monkeypatch.setattr(app, "_asr_profile_manager", fresh_asr)
    monkeypatch.setattr(app, "_mt_profile_manager", fresh_mt)
    monkeypatch.setattr(app, "_pipeline_manager", fresh_pipeline)

    # Re-register v4 managers with decorator module so the ownership
    # check decorators look up profiles in the fresh managers.
    try:
        from auth.decorators import set_v4_managers
        set_v4_managers(fresh_asr, fresh_mt, fresh_pipeline)
    except ImportError:
        pass

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

    # v4.0 A5 T10 — restore the production v4 managers in the decorator
    # closure so the *next* test (which gets a fresh monkeypatch) starts
    # from a known baseline. monkeypatch undoes setattr() on the app
    # module automatically, but set_v4_managers stores closures in
    # auth.decorators directly.
    try:
        from auth.decorators import set_v4_managers
        set_v4_managers(
            app._asr_profile_manager,
            app._mt_profile_manager,
            app._pipeline_manager,
        )
    except ImportError:
        pass
