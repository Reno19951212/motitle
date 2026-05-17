"""End-to-end test: User A (alice) creates ASR profile (private). Admin
creates a shared Pipeline that references it. User C (carol) lists pipelines
— sees the pipeline with broken_refs annotation identifying alice's private
ASR profile as inaccessible.

Uses REAL auth flow (real_auth marker) — no R5_AUTH_BYPASS shortcut.
"""

import pytest


pytestmark = pytest.mark.real_auth


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login(client, username, password):
    resp = client.post(
        "/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, (
        f"Login failed for {username}: {resp.status_code} {resp.data!r}"
    )


def _db(app_module):
    return app_module.app.config["AUTH_DB_PATH"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_v4_managers(tmp_path, monkeypatch):
    """Swap all three v4 managers for fresh isolated instances backed by
    tmp_path so this test doesn't pollute the real config directory and
    doesn't see profiles created by other tests.

    Also re-registers the managers with the decorator module so that
    require_asr_profile_owner / require_pipeline_owner consult the
    fresh instances.
    """
    import app as app_module
    from asr_profiles import ASRProfileManager
    from mt_profiles import MTProfileManager
    from pipelines import PipelineManager
    from auth.decorators import set_v4_managers
    from glossary import GlossaryManager

    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)

    asr_mgr = ASRProfileManager(config_dir)
    mt_mgr = MTProfileManager(config_dir)
    # GlossaryManager is needed by PipelineManager for glossary_ids cross-ref
    gloss_mgr = GlossaryManager(config_dir / "glossaries")
    pipe_mgr = PipelineManager(
        config_dir,
        asr_manager=asr_mgr,
        mt_manager=mt_mgr,
        glossary_manager=gloss_mgr,
    )

    monkeypatch.setattr(app_module, "_asr_profile_manager", asr_mgr)
    monkeypatch.setattr(app_module, "_mt_profile_manager", mt_mgr)
    monkeypatch.setattr(app_module, "_pipeline_manager", pipe_mgr)
    set_v4_managers(asr_mgr, mt_mgr, pipe_mgr)

    yield asr_mgr, mt_mgr, pipe_mgr

    # Restore original managers in the decorator module so other tests
    # are unaffected.
    set_v4_managers(
        app_module._asr_profile_manager,
        app_module._mt_profile_manager,
        app_module._pipeline_manager,
    )


@pytest.fixture
def three_users():
    """Provision alice, bob, carol in the real AUTH_DB.

    Follows the pattern established in test_phase5_ownership.py: write to the
    module-level AUTH_DB rather than overriding AUTH_DB_PATH (the user_loader
    closure captures the path at boot time).

    Also resets the Flask-Limiter storage so that accumulated login calls
    from earlier tests in the full suite do not trigger rate-limit 429s for
    our /login calls.  Flask-Limiter 3.x caches self.enabled at init_app time
    (config.setdefault), so monkeypatching RATELIMIT_ENABLED=False is not
    sufficient — we reset the in-memory storage instead.

    Yields (app_module, alice_id, carol_id).
    """
    import app as app_module
    from auth.users import create_user, delete_user, get_user_by_username, init_db
    from auth.limiter import limiter

    # Reset rate-limit counters and disable enforcement for this test.
    # Flask-Limiter 3.x caches self.enabled at init_app time, so
    # monkeypatching app.config["RATELIMIT_ENABLED"] is not enough.
    # Some earlier tests (e.g. test_phase6 rate_limit_app fixture) call
    # limiter.init_app(mini_app) with RATELIMIT_ENABLED=True, which
    # permanently flips limiter.enabled=True on the shared singleton.
    # We neutralize that here and restore afterward.
    _limiter_enabled_saved = getattr(limiter, "enabled", True)
    try:
        limiter.reset()
        limiter.enabled = False
    except Exception:
        pass

    db = _db(app_module)
    init_db(db)

    for username, password in [
        ("alice_t13", "AlicePass1!"),
        ("bob_t13", "BobPass1!"),
        ("carol_t13", "CarolPass1!"),
    ]:
        try:
            create_user(db, username, password, is_admin=False)
        except ValueError:
            # Already exists from a previous partial run — reset password.
            from auth.users import update_password
            update_password(db, username, password)

    alice_id = get_user_by_username(db, "alice_t13")["id"]
    carol_id = get_user_by_username(db, "carol_t13")["id"]

    yield app_module, alice_id, carol_id

    for username in ("alice_t13", "bob_t13", "carol_t13"):
        try:
            delete_user(db, username)
        except Exception:
            pass

    # Restore limiter state so subsequent tests are unaffected.
    try:
        limiter.enabled = _limiter_enabled_saved
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_broken_refs_annotated_when_subresource_invisible(
    three_users, fresh_v4_managers
):
    """Carol views a shared pipeline that references alice's private ASR
    profile.  The broken_refs annotation in the response must identify the
    ASR profile as inaccessible to Carol.

    Cross-checks:
    - Admin sees broken_refs == {} (admin can see everything).
    - Carol (non-owner, non-admin) sees broken_refs == {asr_profile_id: <id>}.
    - Shared MT stage is visible to everyone, so mt_stages absent from broken_refs.
    - Empty glossary_ids list → glossary_ids absent from broken_refs.
    """
    app_module, alice_id, carol_id = three_users
    asr_mgr, mt_mgr, pipe_mgr = fresh_v4_managers
    app = app_module.app

    # ------------------------------------------------------------------
    # 1. Alice creates a PRIVATE ASR profile (user_id = alice_id).
    # ------------------------------------------------------------------
    with app.test_client() as alice_client:
        _login(alice_client, "alice_t13", "AlicePass1!")
        asr_resp = alice_client.post(
            "/api/asr_profiles",
            json={
                "name": "alice-private-asr",
                "engine": "mlx-whisper",
                "model_size": "large-v3",
                "mode": "same-lang",
                "language": "en",
            },
        )
        assert asr_resp.status_code == 201, (
            f"ASR create failed: {asr_resp.status_code} {asr_resp.data!r}"
        )
        asr = asr_resp.get_json()
        assert asr["user_id"] == alice_id, (
            f"Expected ASR owned by alice (id={alice_id}), got user_id={asr['user_id']}"
        )
        asr_id = asr["id"]

    # ------------------------------------------------------------------
    # 2. Create shared MT profile and shared Pipeline via manager directly
    #    (simulates admin setup; user_id=None = shared).
    # ------------------------------------------------------------------
    shared_mt = mt_mgr.create(
        {
            "name": "shared-mt-t13",
            "engine": "qwen3.5-35b-a3b",
            "input_lang": "zh",
            "output_lang": "zh",
            "system_prompt": "polish the subtitle",
            "user_message_template": "polish: {text}",
        },
        user_id=None,
    )
    shared_mt_id = shared_mt["id"]

    shared_pipe = pipe_mgr.create(
        {
            "name": "shared-pipe-t13",
            "asr_profile_id": asr_id,
            "mt_stages": [shared_mt_id],
            "glossary_stage": {
                "enabled": False,
                "glossary_ids": [],
                "apply_order": "explicit",
                "apply_method": "string-match-then-llm",
            },
            "font_config": {
                "family": "Noto Sans TC",
                "size": 35,
                "color": "#ffffff",
                "outline_color": "#000000",
                "outline_width": 2,
                "margin_bottom": 40,
                "subtitle_source": "auto",
                "bilingual_order": "target_top",
            },
        },
        user_id=None,
    )
    shared_pipe_id = shared_pipe["id"]

    # ------------------------------------------------------------------
    # 3. Carol GETs the shared pipeline — should see broken_refs with asr_id.
    # ------------------------------------------------------------------
    with app.test_client() as carol_client:
        _login(carol_client, "carol_t13", "CarolPass1!")
        resp = carol_client.get(f"/api/pipelines/{shared_pipe_id}")
        assert resp.status_code == 200, (
            f"Carol cannot view shared pipeline: {resp.status_code} {resp.data!r}"
        )
        body = resp.get_json()
        assert "broken_refs" in body, "Response missing broken_refs annotation"
        assert body["broken_refs"] == {"asr_profile_id": asr_id}, (
            f"Expected only asr_profile_id in broken_refs; got {body['broken_refs']}"
        )
        # Shared MT stage must NOT appear in broken_refs (carol can see it).
        assert "mt_stages" not in body["broken_refs"]
        # Empty glossary list must NOT appear.
        assert "glossary_ids" not in body["broken_refs"]

    # ------------------------------------------------------------------
    # 4. Alice herself GETs the pipeline — she owns the ASR so no broken_refs.
    # ------------------------------------------------------------------
    with app.test_client() as alice_client2:
        _login(alice_client2, "alice_t13", "AlicePass1!")
        resp2 = alice_client2.get(f"/api/pipelines/{shared_pipe_id}")
        assert resp2.status_code == 200, (
            f"Alice cannot view shared pipeline: {resp2.status_code} {resp2.data!r}"
        )
        body2 = resp2.get_json()
        assert body2["broken_refs"] == {}, (
            f"Alice owns the ASR profile, so broken_refs should be empty; got {body2['broken_refs']}"
        )
