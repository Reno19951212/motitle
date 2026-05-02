import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from translation.entity_recall import (
    SEED_NAME_INDEX,
    find_en_entities,
    check_zh_has_name,
    build_runtime_index,
)


def test_seed_index_contains_real_madrid():
    assert "real madrid" in SEED_NAME_INDEX
    assert "皇家馬德里" in SEED_NAME_INDEX["real madrid"]


def test_find_en_entities_word_boundary():
    en = "Xabi Alonso was sacked as Real Madrid manager."
    ents = find_en_entities(en, SEED_NAME_INDEX)
    assert "xabi alonso" in ents
    assert "real madrid" in ents


def test_find_en_entities_case_insensitive():
    en = "REAL MADRID news today"
    ents = find_en_entities(en, SEED_NAME_INDEX)
    assert "real madrid" in ents


def test_find_en_entities_no_substring_within_word():
    # "alaba" should not match inside "alabaster"
    en = "Made of alabaster stone."
    ents = find_en_entities(en, SEED_NAME_INDEX)
    assert "alaba" not in ents


def test_check_zh_has_name_variants():
    assert check_zh_has_name("皇馬告急", "real madrid", SEED_NAME_INDEX) is True
    assert check_zh_has_name("國米贏波", "real madrid", SEED_NAME_INDEX) is False


def test_build_runtime_index_extends_with_glossary():
    glossary = [{"en": "Mbappe", "zh": "姆巴比"}]
    idx = build_runtime_index(glossary)
    assert "mbappe" in idx
    assert "姆巴比" in idx["mbappe"]
    # seed entries still present
    assert "real madrid" in idx
