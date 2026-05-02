import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from translation.proxy_entities import (
    extract_proxy_entities,
    has_translit_run,
    EN_STOPWORDS,
)


def test_extract_capitalized_phrase():
    en = "Federico Valverde scored against Manchester United."
    ents = extract_proxy_entities(en)
    assert "Federico Valverde" in ents
    assert "Manchester United" in ents


def test_skip_sentence_initial_capital():
    # "The" / "When" / "However" should be ignored as proxy entities
    en = "The team won. When pressure mounts, however the captain leads."
    ents = extract_proxy_entities(en)
    assert "The" not in ents
    assert "When" not in ents


def test_skip_common_calendar_words():
    en = "On Monday in January, the meeting happened."
    ents = extract_proxy_entities(en)
    assert "Monday" not in ents
    assert "January" not in ents


def test_has_translit_run_3_chars():
    # 3+ consecutive translit chars
    assert has_translit_run("羅德里哥") is True


def test_has_translit_run_below_threshold():
    assert has_translit_run("中場") is False  # not translit


def test_has_translit_run_with_dot():
    # Translit chars connected by ·
    assert has_translit_run("大衛·阿拉巴") is True
