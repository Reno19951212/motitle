from output_lang_aligned import (derive_mode, derive_aligned_output,
                                 build_aligned_bilingual, aligned_rows_for_export)


def test_derive_mode_matrix():
    assert derive_mode("en", "en") == "pass"
    assert derive_mode("en", "zh") == "mt"
    assert derive_mode("ja", "ja") == "pass"
    assert derive_mode("yue", "yue") == "pass"
    assert derive_mode("yue", "zh") == "refine"
    assert derive_mode("yue", "cmn") == "refine"
    assert derive_mode("cmn", "cmn") == "pass"
    assert derive_mode("cmn", "zh") == "refine"
    assert derive_mode("cmn", "yue") == "mt"
    assert derive_mode("yue", "en") == "mt"


def test_derive_pass_preserves_count_and_timing():
    base = [{"start": 1.0, "end": 2.0, "text": "今晚好高興"}, {"start": 2.0, "end": 3.0, "text": "多謝各位"}]
    out = derive_aligned_output(base, "yue", "yue", "trad", lambda s, u: "X")
    assert [(o["start"], o["end"]) for o in out] == [(1.0, 2.0), (2.0, 3.0)]
    assert [o["text"] for o in out] == ["今晚好高興", "多謝各位"]


def test_derive_mt_is_1to1():
    base = [{"start": 0, "end": 1, "text": "你好"}, {"start": 1, "end": 2, "text": "再見"}]
    out = derive_aligned_output(base, "yue", "en", "trad", lambda s, u: {"你好": "Hi", "再見": "Bye"}[u])
    assert [o["text"] for o in out] == ["Hi", "Bye"]
    assert len(out) == len(base)


def test_derive_refine_1to1_json():
    base = [{"start": 0, "end": 1, "text": "我哋今日嚟玩"}]
    out = derive_aligned_output(base, "yue", "zh", "trad",
                                lambda s, u: '{"action":"rewrite","text":"我們今日進行遊戲"}')
    assert out[0]["text"] == "我們今日進行遊戲"
    assert len(out) == 1


def test_build_aligned_bilingual_shape():
    base = [{"start": 0, "end": 1, "text": "你好"}, {"start": 1, "end": 2, "text": "世界"}]
    al = build_aligned_bilingual(base, ["yue", "en"], "yue",
                                 "trad", lambda s, u: {"你好": "Hi", "世界": "World"}.get(u, u))
    assert len(al) == 2
    assert al[0]["start"] == 0 and al[0]["end"] == 1
    assert al[0]["by_lang"]["yue"] == "你好"
    assert al[0]["by_lang"]["en"] == "Hi"


def test_aligned_rows_for_export_maps_fields():
    aligned = [{"start": 0, "end": 1, "by_lang": {"yue": "你好", "en": "Hi"}}]
    rows = aligned_rows_for_export(aligned, "yue", "en", "yue_text", "en_text")
    assert rows[0]["yue_text"] == "你好" and rows[0]["en_text"] == "Hi"
    assert rows[0]["start"] == 0 and rows[0]["end"] == 1
