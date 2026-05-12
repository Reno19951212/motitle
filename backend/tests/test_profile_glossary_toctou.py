"""Phase 5 T2.8 — update_if_owned / delete_if_owned close TOCTOU."""
import pytest


@pytest.fixture
def pm(tmp_path):
    from profiles import ProfileManager
    return ProfileManager(tmp_path)


@pytest.fixture
def gm(tmp_path):
    from glossary import GlossaryManager
    return GlossaryManager(tmp_path)


def test_profile_update_if_owned_returns_none_for_non_owner(pm):
    p = pm.create({
        "name": "private", "asr": {"engine": "whisper", "model": "tiny"},
        "translation": {"engine": "mock"}, "user_id": 1,
    })
    result = pm.update_if_owned(p["id"], user_id=2, is_admin=False,
                                patch={"name": "hacked"})
    assert result is None
    assert pm.get(p["id"])["name"] == "private"


def test_profile_update_if_owned_returns_updated_for_owner(pm):
    p = pm.create({
        "name": "alice's", "asr": {"engine": "whisper", "model": "tiny"},
        "translation": {"engine": "mock"}, "user_id": 1,
    })
    result = pm.update_if_owned(p["id"], user_id=1, is_admin=False,
                                patch={"name": "alice's renamed"})
    assert result is not None and result["name"] == "alice's renamed"


def test_profile_update_if_owned_admin_can_edit_any(pm):
    p = pm.create({
        "name": "alice's", "asr": {"engine": "whisper", "model": "tiny"},
        "translation": {"engine": "mock"}, "user_id": 1,
    })
    result = pm.update_if_owned(p["id"], user_id=999, is_admin=True,
                                patch={"name": "admin override"})
    assert result is not None and result["name"] == "admin override"


def test_profile_delete_if_owned_blocked_for_non_owner(pm):
    p = pm.create({
        "name": "owned", "asr": {"engine": "whisper", "model": "tiny"},
        "translation": {"engine": "mock"}, "user_id": 1,
    })
    ok = pm.delete_if_owned(p["id"], user_id=2, is_admin=False)
    assert ok is False
    assert pm.get(p["id"]) is not None


def test_profile_delete_if_owned_allows_owner(pm):
    p = pm.create({
        "name": "owned", "asr": {"engine": "whisper", "model": "tiny"},
        "translation": {"engine": "mock"}, "user_id": 1,
    })
    assert pm.delete_if_owned(p["id"], user_id=1, is_admin=False) is True
    assert pm.get(p["id"]) is None


def test_glossary_update_if_owned(gm):
    g = gm.create({"name": "terms", "description": "", "user_id": 1, "source_lang": "en", "target_lang": "zh"})
    assert gm.update_if_owned(g["id"], user_id=2, is_admin=False,
                              patch={"name": "hacked"}) is None
    r = gm.update_if_owned(g["id"], user_id=1, is_admin=False,
                           patch={"name": "renamed"})
    assert r is not None and r["name"] == "renamed"


def test_glossary_delete_if_owned_blocked_for_non_owner(gm):
    g = gm.create({"name": "terms", "description": "", "user_id": 1, "source_lang": "en", "target_lang": "zh"})
    assert gm.delete_if_owned(g["id"], user_id=2, is_admin=False) is False
    assert gm.get(g["id"]) is not None


def test_glossary_delete_if_owned_allows_owner(gm):
    g = gm.create({"name": "terms", "description": "", "user_id": 1, "source_lang": "en", "target_lang": "zh"})
    assert gm.delete_if_owned(g["id"], user_id=1, is_admin=False) is True
    assert gm.get(g["id"]) is None
