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

    # Fixture-isolation guard (cross-test bleed fix):
    # Several test-local fixtures (e.g. non_admin_session, and per-module
    # `client` fixtures in test_v6_second_language / test_output_lang_api /
    # test_bilingual_api / test_segment_split_routes / test_bug_*_fixes /
    # test_phase5_security) mutate these auth flags via DIRECT assignment or
    # `app.config.pop(...)` rather than monkeypatch.setitem. Direct mutation is
    # NOT auto-reverted, and `.pop()` deletes the key entirely, which corrupts
    # the value monkeypatch.setitem below would otherwise restore. The net
    # effect was the flags leaking into SUBSEQUENT tests (e.g. R5_AUTH_BYPASS
    # left False/absent → ~50 unrelated tests 401'ing in a cumulative run while
    # passing in isolation).
    #
    # This autouse fixture wraps EVERY test, and its teardown runs LAST (after
    # all test-local fixture teardowns). So we:
    #   (a) snapshot both auth flags on the way in (to restore exactly the
    #       pre-test state on the way out, removing this test's footprint), and
    #   (b) UNCONDITIONALLY ESTABLISH the correct flag state for THIS test —
    #       True/True under bypass, False/False under real_auth.
    #
    # Step (b) is what actually kills the bleed: snapshot+restore alone only
    # preserves whatever (possibly already-polluted) value was incoming, so a
    # leaked R5_AUTH_BYPASS would survive across real_auth tests. By forcing a
    # known-good starting state every time, no prior test's direct assignment /
    # `app.config.pop(...)` can corrupt this test's auth behaviour.
    #
    # NOTE: these two flags are set/restored MANUALLY (not via
    # monkeypatch.setitem). monkeypatch's undo runs *after* this generator's
    # teardown, so mixing the two would let monkeypatch re-apply a stale value
    # on top of our authoritative restore. Owning the full lifecycle here keeps
    # the post-test state deterministic.
    _AUTH_FLAG_KEYS = ("LOGIN_DISABLED", "R5_AUTH_BYPASS", "R5_LICENSE_BYPASS")
    _MISSING = object()
    _auth_flag_snapshot = {
        k: app.app.config.get(k, _MISSING) for k in _AUTH_FLAG_KEYS
    }

    if _use_real_auth:
        # Real login/permission checks must run — force bypass OFF even if a
        # prior bypass test leaked it ON.
        app.app.config["LOGIN_DISABLED"] = False
        app.app.config["R5_AUTH_BYPASS"] = False
    else:
        app.app.config["LOGIN_DISABLED"] = True
        app.app.config["R5_AUTH_BYPASS"] = True

    # License gate (Task 7) is a global before_request that 403s every /api/*
    # call when no licence is installed. The vast majority of existing tests
    # never install a licence, so bypass the gate by default — exactly like
    # R5_AUTH_BYPASS above. The licensing test suites flip this OFF in their
    # own fixtures to exercise the real gate.
    app.app.config["R5_LICENSE_BYPASS"] = True

    # Also replace the module-level _subtitle_renderer instance, which was
    # constructed at import time with the real RENDERS_DIR.
    monkeypatch.setattr(
        app,
        "_subtitle_renderer",
        SubtitleRenderer(test_data_dir / "renders"),
    )

    # v3.19 — isolate CONFIG_DIR-rooted managers so test_client() POSTs to
    # /api/pipelines (and other manager-write routes) don't leak files into
    # the real backend/config/<subdir>/. Without this, every run of
    # test_v6_runner.TestV6PipelinePostEndpoint left a fresh "Test v6 pipeline"
    # JSON in production config/pipelines/, spamming the Dashboard preset menu.
    #
    # Uses an "_isolated_managers_config" subdir name (not just "config") to
    # avoid collisions with tests that themselves create tmp_path/"config".
    test_managers_config = tmp_path / "_isolated_managers_config"
    try:
        from pipelines import PipelineManager
        from transcribe_profiles import TranscribeProfileManager
        from llm_profiles import LLMProfileManager
        from refiner_profiles import RefinerProfileManager
        # Each manager __init__ creates its subdir with parents=True, exist_ok=True,
        # so we don't need to pre-create test_managers_config.
        monkeypatch.setattr(app, "_pipeline_manager", PipelineManager(test_managers_config))
        monkeypatch.setattr(
            app, "_transcribe_profile_manager",
            TranscribeProfileManager(test_managers_config / "transcribe_profiles"),
        )
        monkeypatch.setattr(
            app, "_llm_profile_manager",
            LLMProfileManager(test_managers_config / "llm_profiles"),
        )
        monkeypatch.setattr(
            app, "_refiner_profile_manager",
            RefinerProfileManager(test_managers_config / "refiner_profiles"),
        )
        # Re-wire the auth/decorators globals so require_pipeline_owner uses
        # the test instance during ownership checks.
        try:
            from auth.decorators import set_v4_managers as _sv4
            _sv4(asr_manager=None, mt_manager=None, pipeline_manager=app._pipeline_manager)
        except ImportError:
            pass
    except ImportError:
        # Managers not importable in this test context — non-V6 tests are fine.
        pass

    # Same leak class for the glossary manager (missed in v3.19): API-level
    # glossary tests (e.g. test_glossary_multilingual's route tests) wrote
    # real files into backend/config/glossaries/ — dozens of duplicate-named
    # "T"/"EN-ZH"/"JA-ZH"/"ZH-ZH style" stubs accumulated on dev machines and
    # made the Glossary page look like deletion was broken (delete one, six
    # identically-named copies remain).
    try:
        from glossary import GlossaryManager
        monkeypatch.setattr(
            app, "_glossary_manager", GlossaryManager(test_managers_config)
        )
    except ImportError:
        pass

    # Snapshot and clear the registry under the same lock production code uses.
    with app._registry_lock:
        original_registry = app._file_registry.copy()
        app._file_registry.clear()

    yield

    with app._registry_lock:
        app._file_registry.clear()
        app._file_registry.update(original_registry)

    # Authoritative auth-flag restore (see the snapshot comment above). Runs
    # after every test-local fixture teardown, so it overrides any direct
    # assignment / `.pop()` a test fixture left behind. A key absent in the
    # snapshot is restored to absent; otherwise the original value is put back.
    for _k in _AUTH_FLAG_KEYS:
        _orig = _auth_flag_snapshot[_k]
        if _orig is _MISSING:
            app.app.config.pop(_k, None)
        else:
            app.app.config[_k] = _orig


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
def v6_zh_source_file(tmp_path):
    """V6 file whose source_lang is 'zh' — simulates a Cantonese broadcast file
    where translations only have by_lang.zh populated (no EN translation).

    Used by B-7 test to verify that render with subtitle_source='en' is
    either rejected or warns rather than burning the raw Qwen3 packed dump.
    """
    try:
        import app as app_mod
    except ImportError:
        pytest.skip("app module not available")

    fid = f"v6-zh-{uuid.uuid4().hex[:8]}"
    # source_text is a Qwen3-packed no-whitespace dump (the problematic data)
    qwen3_dump = "HIGHLANDBLINKisaGreatHorse"
    translations_data = [
        {
            "idx": 0,
            "start": 0.0,
            "end": 2.0,
            "source_lang": "zh",
            "source_text": qwen3_dump,
            "by_lang": {
                "zh": {
                    "text": "高蘭布連卡係一匹好馬",
                    "status": "approved",
                    "flags": [],
                },
            },
            "zh_text": "高蘭布連卡係一匹好馬",
            "status": "approved",
            "flags": [],
        }
    ]

    dummy_media = tmp_path / "data" / "uploads" / f"{fid}_cantonese.mp4"
    dummy_media.parent.mkdir(parents=True, exist_ok=True)
    dummy_media.write_bytes(b"DUMMY")

    entry = {
        "id": fid,
        "original_name": "cantonese_race.mp4",
        "size": 2048,
        "status": "done",
        "uploaded_at": time.time(),
        "user_id": None,
        "active_kind": "pipeline_v6",
        "active_id": "test-pipeline-v6",
        "segments": [],
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


@pytest.fixture
def non_admin_session():
    """A Flask test client authenticated as a non-admin user (bob_test).

    Used by B-2 test to exercise the real non-admin path in list_pipelines,
    which calls annotate_broken_refs with is_admin=False.

    The fixture temporarily disables R5_AUTH_BYPASS so that the route code
    uses the real current_user.is_admin value (False for bob_test).
    After the fixture yields, it restores R5_AUTH_BYPASS.
    """
    try:
        import app as app_mod
        from auth.users import init_db, create_user
    except ImportError:
        pytest.skip("app module not available")

    db = app_mod.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "bob_test", "BobPass1!", is_admin=False)
    except ValueError:
        pass  # user already exists (created in setup or previous run)

    # Temporarily disable auth bypass so is_admin=False is respected
    original_bypass = app_mod.app.config.get("R5_AUTH_BYPASS", False)
    original_login_disabled = app_mod.app.config.get("LOGIN_DISABLED", False)
    app_mod.app.config["R5_AUTH_BYPASS"] = False
    app_mod.app.config["LOGIN_DISABLED"] = False

    c = app_mod.app.test_client()
    r = c.post("/login", json={"username": "bob_test", "password": "BobPass1!"})
    if r.status_code != 200:
        app_mod.app.config["R5_AUTH_BYPASS"] = original_bypass
        app_mod.app.config["LOGIN_DISABLED"] = original_login_disabled
        pytest.fail(f"bob_test login failed: {r.status_code} {r.get_data(as_text=True)[:200]}")

    yield c

    app_mod.app.config["R5_AUTH_BYPASS"] = original_bypass
    app_mod.app.config["LOGIN_DISABLED"] = original_login_disabled
