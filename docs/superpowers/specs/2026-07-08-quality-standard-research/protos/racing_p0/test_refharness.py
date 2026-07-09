import refharness as rh


def test_term_accept_track_work():
    assert rh.term_accept("track_work", "牠晨操表現理想")
    assert not rh.term_accept("track_work", "他在該場地的表現出色")


def test_term_accept_closer():
    assert rh.term_accept("closer", "後上賽駒佔優")
    assert not rh.term_accept("closer", "在後方的馬匹")


def test_term_accept_newcomer():
    assert rh.term_accept("newcomer", "對初次上陣的賽駒有利")
    assert rh.term_accept("newcomer", "新馬受惠")
    assert not rh.term_accept("newcomer", "對新來者有利")


def test_term_accept_unit_rejects_gongchi():
    assert rh.term_accept("unit", "今次扳上2000米")
    assert not rh.term_accept("unit", "二千公尺又是另一級距")


def test_term_accept_reset_protected():
    assert rh.term_accept("reset", "母系源自「Reset」")
    assert rh.term_accept("reset", "他的外祖父是Reset")
    assert not rh.term_accept("reset", "他是一匹未重置的母馬")


def test_find_cue_substring_ci():
    mot = [{"start": 0, "end": 1, "en": "His TRACK works very good", "zh": "x"}]
    assert rh.find_cue(mot, "track works")["en"].startswith("His")
    assert rh.find_cue(mot, "nonexistent") is None


def test_overlap_pro_joins_overlapping():
    pro = [{"start": 0, "end": 5, "text": "A"}, {"start": 5, "end": 10, "text": "B"},
           {"start": 10, "end": 12, "text": "C"}]
    assert rh.overlap_pro(pro, 4, 6) == "A B"
    assert rh.overlap_pro(pro, 20, 22) == ""
