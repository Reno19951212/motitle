"""Tests for pipeline preset_slot field (Q3)."""
import pytest


@pytest.mark.parametrize("slot", [None, 1, 2, 3, 4])
def test_v4_pipeline_accepts_valid_preset_slot(slot):
    from pipelines import validate_pipeline
    pipeline = {
        "name": "test",
        "asr_profile_id": "asr-1",
        "mt_stages": [],
        "preset_slot": slot,
    }
    errors = validate_pipeline(pipeline)
    assert "preset_slot" not in str(errors), f"slot={slot} should be valid: {errors}"


@pytest.mark.parametrize("bad", [0, 5, -1, "1", 1.5, True])
def test_v4_pipeline_rejects_invalid_preset_slot(bad):
    from pipelines import validate_pipeline
    pipeline = {
        "name": "test",
        "asr_profile_id": "asr-1",
        "mt_stages": [],
        "preset_slot": bad,
    }
    errors = validate_pipeline(pipeline)
    assert any("preset_slot" in e for e in errors), f"slot={bad!r} should be rejected"


@pytest.mark.parametrize("slot", [None, 1, 2, 3, 4])
def test_v5_pipeline_accepts_valid_preset_slot(slot):
    from pipeline_schema_v5 import validate_v5_pipeline
    pipeline = {
        "version": 5,
        "name": "test",
        "source_lang": "en",
        "target_languages": ["en"],
        "asr_primary": {"transcribe_profile_id": "t-1"},
        "preset_slot": slot,
    }
    errors, _warnings = validate_v5_pipeline(pipeline)
    assert not any("preset_slot" in e for e in errors), f"slot={slot}: {errors}"


@pytest.mark.parametrize("bad", [0, 5, "1", 1.5, True])
def test_v5_pipeline_rejects_invalid_preset_slot(bad):
    from pipeline_schema_v5 import validate_v5_pipeline
    pipeline = {
        "version": 5,
        "name": "test",
        "source_lang": "en",
        "target_languages": ["en"],
        "asr_primary": {"transcribe_profile_id": "t-1"},
        "preset_slot": bad,
    }
    errors, _ = validate_v5_pipeline(pipeline)
    assert any("preset_slot" in e for e in errors)


# ---------------------------------------------------------------------------
# Integration tests for POST /api/pipelines/<pid>/preset_slot (Q3 endpoint)
# ---------------------------------------------------------------------------
#
# Strategy:
#   - Tests 1, 3, 5 (single-user scenarios): AUTH_BYPASS is active (conftest
#     sets LOGIN_DISABLED=True + R5_AUTH_BYPASS=True), so current_user is the
#     anonymous user but is_admin is forced True.  Pipelines are created via
#     PipelineManager.create(validate_refs=False) to bypass cascade-ref check.
#     user_id=None (shared / admin-owned).
#   - Tests 2, 4 (multi-user / non-owner scenarios): real_auth marker disables
#     bypass; real users are created and logged in per-client.
# ---------------------------------------------------------------------------


def _make_pipeline_direct(mgr, name, slot=None, user_id=None):
    """Create a minimal v4 pipeline directly via the manager (bypass cascade ref)."""
    return mgr.create(
        {
            "name": name,
            "asr_profile_id": "asr-test-bypass",
            "mt_stages": [],
            "preset_slot": slot,
        },
        user_id=user_id,
        validate_refs=False,
    )


def test_setting_preset_slot_atomically_swaps_previous_occupant():
    """If P1 holds slot=2 and user POSTs P2 to slot=2,
    P1 must atomically transition to preset_slot=None."""
    import app as _app

    mgr = _app._pipeline_manager
    p1 = _make_pipeline_direct(mgr, "P1-atomic", slot=2)
    p2 = _make_pipeline_direct(mgr, "P2-atomic")

    c = _app.app.test_client()
    resp = c.post(
        f"/api/pipelines/{p2['id']}/preset_slot",
        json={"slot": 2},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["ok"] is True
    assert body["swapped_pipeline_id"] == p1["id"]

    # Verify via manager directly (bypasses route response caching)
    p1_after = mgr.get(p1["id"])
    p2_after = mgr.get(p2["id"])
    assert p1_after["preset_slot"] is None
    assert p2_after["preset_slot"] == 2


def test_endpoint_rejects_invalid_slot():
    """Slot values outside {1,2,3,4} must return 400."""
    import app as _app

    mgr = _app._pipeline_manager
    p = _make_pipeline_direct(mgr, "Px-bad-slot")

    c = _app.app.test_client()
    for bad in [0, 5, -1, "two"]:
        r = c.post(
            f"/api/pipelines/{p['id']}/preset_slot",
            json={"slot": bad},
        )
        assert r.status_code == 400, f"slot={bad!r} should 400, got {r.status_code}"


def test_endpoint_accepts_null_to_clear_slot():
    """POST slot=None must clear an existing slot assignment."""
    import app as _app

    mgr = _app._pipeline_manager
    p = _make_pipeline_direct(mgr, "Px-clear", slot=3)

    c = _app.app.test_client()
    r = c.post(f"/api/pipelines/{p['id']}/preset_slot", json={"slot": None})
    assert r.status_code == 200, r.get_data(as_text=True)

    p_after = mgr.get(p["id"])
    assert p_after["preset_slot"] is None


@pytest.mark.real_auth
def test_different_users_can_hold_same_slot():
    """User A owning slot=1 must NOT block User B from owning slot=1."""
    import app as app_module
    from auth.users import init_db, create_user, update_password
    from auth.limiter import limiter
    from pipelines import PipelineManager

    _limiter_enabled_saved = getattr(limiter, "enabled", True)
    try:
        limiter.reset()
        limiter.enabled = False
    except Exception:
        pass

    db_path = app_module.app.config["AUTH_DB_PATH"]
    init_db(db_path)

    for uname, pw in [("pslot_user_a", "TestPassA1!"), ("pslot_user_b", "TestPassB1!")]:
        try:
            create_user(db_path, uname, pw, is_admin=False)
        except ValueError:
            update_password(db_path, uname, pw)

    ca = app_module.app.test_client()
    cb = app_module.app.test_client()
    assert ca.post("/login", json={"username": "pslot_user_a", "password": "TestPassA1!"}).status_code == 200
    assert cb.post("/login", json={"username": "pslot_user_b", "password": "TestPassB1!"}).status_code == 200

    # Both users use the same manager (isolated by conftest) but with real user_ids.
    mgr = app_module._pipeline_manager
    # We need their user_ids to create pipelines with correct ownership.
    from auth.users import get_user_by_username
    uid_a = get_user_by_username(db_path, "pslot_user_a")["id"]
    uid_b = get_user_by_username(db_path, "pslot_user_b")["id"]

    pa = _make_pipeline_direct(mgr, "A1-slot1", slot=None, user_id=uid_a)
    pb = _make_pipeline_direct(mgr, "B1-slot1", slot=None, user_id=uid_b)

    # User A assigns slot=1
    ra = ca.post(f"/api/pipelines/{pa['id']}/preset_slot", json={"slot": 1})
    assert ra.status_code == 200, ra.get_data(as_text=True)

    # User B assigns slot=1 — must succeed independently (no conflict)
    rb = cb.post(f"/api/pipelines/{pb['id']}/preset_slot", json={"slot": 1})
    assert rb.status_code == 200, rb.get_data(as_text=True)

    assert mgr.get(pa["id"])["preset_slot"] == 1
    assert mgr.get(pb["id"])["preset_slot"] == 1

    try:
        limiter.enabled = _limiter_enabled_saved
    except Exception:
        pass


@pytest.mark.real_auth
def test_endpoint_rejects_non_owner():
    """A non-owner, non-admin user must receive 403."""
    import app as app_module
    from auth.users import init_db, create_user, update_password, get_user_by_username
    from auth.limiter import limiter

    _limiter_enabled_saved = getattr(limiter, "enabled", True)
    try:
        limiter.reset()
        limiter.enabled = False
    except Exception:
        pass

    db_path = app_module.app.config["AUTH_DB_PATH"]
    init_db(db_path)

    for uname, pw in [("pslot_owner_u", "OwnerPass1!"), ("pslot_other_u", "OtherPass1!")]:
        try:
            create_user(db_path, uname, pw, is_admin=False)
        except ValueError:
            update_password(db_path, uname, pw)

    owner_c = app_module.app.test_client()
    other_c = app_module.app.test_client()
    assert owner_c.post("/login", json={"username": "pslot_owner_u", "password": "OwnerPass1!"}).status_code == 200
    assert other_c.post("/login", json={"username": "pslot_other_u", "password": "OtherPass1!"}).status_code == 200

    uid_owner = get_user_by_username(db_path, "pslot_owner_u")["id"]
    mgr = app_module._pipeline_manager
    p = _make_pipeline_direct(mgr, "Po-non-owner", user_id=uid_owner)

    r = other_c.post(f"/api/pipelines/{p['id']}/preset_slot", json={"slot": 1})
    assert r.status_code == 403, r.get_data(as_text=True)

    try:
        limiter.enabled = _limiter_enabled_saved
    except Exception:
        pass
