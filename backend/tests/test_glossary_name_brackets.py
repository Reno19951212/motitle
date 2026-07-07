# backend/tests/test_glossary_name_brackets.py
"""glossary name_brackets 欄位：create default / create 帶值 / update / validate 三值。"""
import pytest
from glossary import GlossaryManager


@pytest.fixture
def mgr(tmp_path):
    return GlossaryManager(str(tmp_path))


BASE = {"name": "賽馬", "source_lang": "en", "target_lang": "zh"}


def test_create_defaults_off(mgr):
    g = mgr.create(dict(BASE))
    assert g["name_brackets"] == "off"


def test_create_with_value(mgr):
    g = mgr.create({**BASE, "name_brackets": "zh"})
    assert g["name_brackets"] == "zh"
    assert mgr.get(g["id"])["name_brackets"] == "zh"


def test_create_rejects_bad_value(mgr):
    with pytest.raises(ValueError):
        mgr.create({**BASE, "name_brackets": "yes"})


def test_update_sets_and_preserves(mgr):
    g = mgr.create(dict(BASE))
    u = mgr.update(g["id"], {"name_brackets": "all"})
    assert u["name_brackets"] == "all"
    u2 = mgr.update(g["id"], {"description": "x"})     # 冇傳 → 保留
    assert u2["name_brackets"] == "all"


def test_update_rejects_bad_value(mgr):
    g = mgr.create(dict(BASE))
    with pytest.raises(ValueError):
        mgr.update(g["id"], {"name_brackets": "both"})


def test_list_all_includes_flag(mgr):
    g = mgr.create({**BASE, "name_brackets": "zh"})
    summary = next(s for s in mgr.list_all() if s["id"] == g["id"])
    assert summary["name_brackets"] == "zh"
