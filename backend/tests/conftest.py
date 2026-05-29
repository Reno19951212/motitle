import os
import sys
import time
import uuid
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
    # is_admin.
    #
    # Two ways a test opts into real auth (either is sufficient):
    #   1. Legacy: test module filename is in _REAL_AUTH_MODULES (backward compat).
    #   2. New:    test is decorated with @pytest.mark.real_auth.
    # "test_phase5_security" migrated to @pytest.mark.real_auth — removed from tuple.
    _REAL_AUTH_MODULES = ("test_admin_users", "test_per_user_profiles", "test_per_user_glossaries", "test_queue_retry", "test_files_job_id", "test_cancel_running", "test_phase5_ownership", "test_render_ownership")
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


# ---------------------------------------------------------------------------
# v3.19 Sprint 1 — shared fixtures for Phase B findings tests
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Default Flask test client: isolated data dirs + auth bypass.

    Individual test files may override this fixture for specialized setups
    (e.g. tests that need real auth or a pre-populated profile manager).
    """
    try:
        import app as app_mod
        from profiles import ProfileManager
    except ImportError:
        pytest.skip("app module not available")

    new_prof_mgr = ProfileManager(tmp_path)
    monkeypatch.setattr("app._profile_manager", new_prof_mgr)
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c

@pytest.fixture
def v6_file_with_translations(tmp_path):
    """Insert a synthetic V6 file with Sprint-1-style legacy mirror fields.

    The fixture populates both by_lang.<lang> AND top-level zh_text/status so
    that tests relying on this fixture work correctly after Sprint 1 fixes.
    Tests that specifically want PRE-fix V6 shape (no mirrors) should build
    their own registry entry directly.

    Returns file_id.
    """
    try:
        import app as app_mod
    except ImportError:
        pytest.skip("app module not available")

    fid = f"v6-phb-{uuid.uuid4().hex[:8]}"
    segments_data = [
        {"start": 0.0,  "end": 1.5, "text": "冇人會傷害嗰啲感受"},
        {"start": 1.5,  "end": 3.0, "text": "今日賽事精彩紛呈"},
        {"start": 3.0,  "end": 5.0, "text": "高蘭布連卡速度驚人"},
    ]
    translations_data = []
    for i, seg in enumerate(segments_data):
        row = {
            "idx": i,
            "start": seg["start"],
            "end": seg["end"],
            "source_lang": "zh",
            "source_text": seg["text"],
            "by_lang": {
                "zh": {
                    "text": seg["text"],
                    "status": "pending",
                    "flags": [],
                },
            },
            # Sprint 1 Change 1 mirrors — present so the fixture reflects
            # the post-fix state; Change 4 migration handles existing on-disk files.
            "zh_text": seg["text"],
            "status": "pending",
            "flags": [],
        }
        translations_data.append(row)

    # Create a dummy media file so the render endpoint can resolve the path
    dummy_media = tmp_path / "data" / "uploads" / f"{fid}_raceday.mp4"
    dummy_media.parent.mkdir(parents=True, exist_ok=True)
    dummy_media.write_bytes(b"DUMMY")

    entry = {
        "id": fid,
        "original_name": "raceday.mp4",
        "size": 1024,
        "status": "done",
        "uploaded_at": time.time(),
        "user_id": None,
        "active_kind": "pipeline_v6",
        "active_id": "test-pipeline-v6",
        "segments": [],          # V6 keeps translations, not segments at top level
        "translations": translations_data,
        "translation_status": "done",
        "prompt_overrides": None,
        "error": None,
        "model": None,
        "backend": None,
        "asr_seconds": None,
        "translation_seconds": None,
        "pipeline_seconds": None,
        "file_path": str(dummy_media),
    }

    with app_mod._registry_lock:
        app_mod._file_registry[fid] = entry

    yield fid

    with app_mod._registry_lock:
        app_mod._file_registry.pop(fid, None)


@pytest.fixture
def v6_file_with_stage_outputs(tmp_path):
    """Insert a synthetic V6 file with stage_outputs populated.

    Used by B-1 test to verify /api/files/<fid>/stages/* routes work
    once the require_file_owner decorator accepts 'fid' kwarg.

    Returns file_id.
    """
    try:
        import app as app_mod
    except ImportError:
        pytest.skip("app module not available")

    fid = f"v6-stg-{uuid.uuid4().hex[:8]}"

    # Create a dummy media file
    dummy_media = tmp_path / "data" / "uploads" / f"{fid}_test.mp4"
    dummy_media.parent.mkdir(parents=True, exist_ok=True)
    dummy_media.write_bytes(b"DUMMY")

    stage_outputs = {
        "2": {
            "stage_idx": 2,
            "status": "done",
            "segments": [
                {"idx": 0, "text": "original text", "start": 0.0, "end": 1.5},
            ],
        },
        "4": {
            "stage_idx": 4,
            "status": "done",
            "segments": [
                {"idx": 0, "text": "original text", "start": 0.0, "end": 1.5},
            ],
        },
    }

    entry = {
        "id": fid,
        "original_name": "test.mp4",
        "size": 1024,
        "status": "done",
        "uploaded_at": time.time(),
        "user_id": None,
        "active_kind": "pipeline_v6",
        "active_id": "test-pipeline-v6",
        "pipeline_id": "test-pipeline-v6",
        "segments": [],
        "translations": [],
        "translation_status": "done",
        "stage_outputs": stage_outputs,
        "prompt_overrides": None,
        "pipeline_overrides": {},
        "error": None,
        "model": None,
        "backend": None,
        "asr_seconds": None,
        "translation_seconds": None,
        "pipeline_seconds": None,
        "file_path": str(dummy_media),
    }

    with app_mod._registry_lock:
        app_mod._file_registry[fid] = entry

    yield fid

    with app_mod._registry_lock:
        app_mod._file_registry.pop(fid, None)


@pytest.fixture
def get_registry_entry():
    """Return a function that looks up the current registry entry for a file_id."""
    try:
        import app as app_mod
    except ImportError:
        pytest.skip("app module not available")

    def _get(file_id):
        with app_mod._registry_lock:
            return app_mod._file_registry.get(file_id)

    return _get


@pytest.fixture
def render_complete():
    """Return a helper that polls _render_jobs until status is no longer 'processing'."""
    try:
        import app as app_mod
    except ImportError:
        pytest.skip("app module not available")

    def _wait(render_id, timeout=120):
        deadline = time.time() + timeout
        with app_mod._render_jobs_lock:
            job = dict(app_mod._render_jobs.get(render_id, {}))
        while job.get("status") == "processing" and time.time() < deadline:
            time.sleep(0.5)
            with app_mod._render_jobs_lock:
                job = dict(app_mod._render_jobs.get(render_id, {}))
        return job

    return _wait
