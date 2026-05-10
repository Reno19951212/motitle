"""Phase 3D — per-user Profile override."""
import pytest


@pytest.fixture
def pm(tmp_path):
    """Per-test ProfileManager with 3 entries: 1 shared + 1 alice + 1 bob."""
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    shared = pm.create({"name": "Shared", "asr": {"engine": "whisper"},
                        "translation": {"engine": "mock"}, "user_id": None})
    a = pm.create({"name": "Alice", "asr": {"engine": "whisper"},
                   "translation": {"engine": "mock"}, "user_id": 1})
    b = pm.create({"name": "Bob", "asr": {"engine": "whisper"},
                   "translation": {"engine": "mock"}, "user_id": 2})
    return pm, shared["id"], a["id"], b["id"]


def test_list_visible_for_alice_returns_shared_plus_own(pm):
    manager, sid, aid, bid = pm
    visible = manager.list_visible(user_id=1, is_admin=False)
    ids = {p["id"] for p in visible}
    assert sid in ids and aid in ids
    assert bid not in ids


def test_list_visible_for_admin_returns_all(pm):
    manager, sid, aid, bid = pm
    visible = manager.list_visible(user_id=999, is_admin=True)
    ids = {p["id"] for p in visible}
    assert sid in ids and aid in ids and bid in ids


def test_can_edit_own_profile(pm):
    manager, sid, aid, bid = pm
    assert manager.can_edit(aid, user_id=1, is_admin=False) is True


def test_cannot_edit_others_profile(pm):
    manager, sid, aid, bid = pm
    assert manager.can_edit(bid, user_id=1, is_admin=False) is False


def test_admin_can_edit_anything(pm):
    manager, sid, aid, bid = pm
    assert manager.can_edit(sid, user_id=999, is_admin=True) is True
    assert manager.can_edit(aid, user_id=999, is_admin=True) is True


def test_can_edit_shared_only_by_admin(pm):
    """Shared profiles (user_id=None) editable only by admins."""
    manager, sid, aid, bid = pm
    assert manager.can_edit(sid, user_id=1, is_admin=False) is False
    assert manager.can_edit(sid, user_id=999, is_admin=True) is True
