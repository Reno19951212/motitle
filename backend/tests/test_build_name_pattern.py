r"""build_name_pattern：\s+ 空白容錯 + 標點變體 + 邊界（spec §4.1/V2）。"""
from output_lang_glossary import build_name_pattern, _filter_source_side

GLOSS = {"id": "g1", "name": "賽馬", "source_lang": "en", "target_lang": "zh",
         "entries": [{"id": "e1", "source": "GOLDEN SIXTY", "target": "金鎗六十 (K001)"},
                     {"id": "e2", "source": "GLORIOUS ST PAUL'S", "target": "保羅輝煌 (K524)"}]}


def test_case_insensitive():
    assert build_name_pattern("GOLDEN SIXTY").search("golden sixty wins")


def test_double_space_and_newline():
    p = build_name_pattern("GOLDEN SIXTY")
    assert p.search("golden  sixty wins")
    assert p.search("golden\nsixty wins")


def test_curly_apostrophe_variant():
    p = build_name_pattern("GLORIOUS ST PAUL'S")
    assert p.search("glorious st paul’s ran well")   # 彎引號
    assert p.search("glorious st paul's ran well")   # 直引號


def test_word_boundary_no_partial():
    assert not build_name_pattern("CLASS").search("classic race")


def test_hyphen_variants():
    p = build_name_pattern("A-B")
    assert p.search("a–b") and p.search("a-b")


def test_empty_source_never_matches():
    assert not build_name_pattern("").search("anything")


def test_filter_source_side_double_space_now_matches():
    cands = _filter_source_side("golden  sixty wins", [GLOSS], "zh", "en", "mt")
    assert [c["source"] for c in cands] == ["GOLDEN SIXTY"]


# --- review fixes 2026-07-07: lookaround boundaries ---

def test_leading_apostrophe_token_matches():
    assert build_name_pattern("'TIS LUCKY").search("said 'tis lucky today")


def test_cjk_adjacency_matches():
    assert build_name_pattern("GOLDEN SIXTY").search("見到golden sixty出咗閘")


def test_boundary_still_blocks_ascii_partial():
    assert not build_name_pattern("CLASS").search("classic race")
    assert not build_name_pattern("ACE").search("the race is on")
