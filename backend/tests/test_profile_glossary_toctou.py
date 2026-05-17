"""Phase 5 T2.8 — update_if_owned / delete_if_owned close TOCTOU.

v4.0 A5 T8: 5 legacy ProfileManager tests deleted (test_profile_update_*,
test_profile_delete_*). The v4 entity managers (ASRProfileManager,
MTProfileManager) carry equivalent update_if_owned/delete_if_owned TOCTOU
coverage in test_asr_profiles.py / test_mt_profiles.py. The glossary tests
below still exercise the GlossaryManager TOCTOU path that remains in use.
"""
import pytest


@pytest.fixture
def gm(tmp_path):
    from glossary import GlossaryManager
    return GlossaryManager(tmp_path)


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
