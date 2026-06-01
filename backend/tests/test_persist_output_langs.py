"""
Tests for output_lang_persist.build_output_translations.
RED phase: these tests must FAIL before output_lang_persist.py exists.
"""
import copy
import pytest


def test_persist_first_and_second_output_langs():
    from output_lang_persist import build_output_translations

    src = [{"start": 0, "end": 1}, {"start": 1, "end": 2}]
    first = [{"text": "今晚嘅賽事"}, {"text": "準備起步"}]   # yue
    second = [{"text": "Tonight's race"}, {"text": "Get ready"}]  # en

    rows = build_output_translations(src, [("yue", first), ("en", second)])

    assert len(rows) == 2
    r = rows[0]
    assert r["by_lang"]["yue"]["text"] == "今晚嘅賽事"
    assert r["yue_text"] == "今晚嘅賽事"
    assert r["by_lang"]["en"]["text"] == "Tonight's race"
    assert r["en_text"] == "Tonight's race"
    assert r["start"] == 0
    assert r["end"] == 1
    assert r["by_lang"]["yue"]["status"] == "pending"


def test_persist_first_only():
    from output_lang_persist import build_output_translations

    rows = build_output_translations(
        [{"start": 0, "end": 1}],
        [("zh", [{"text": "你好"}])]
    )
    assert rows[0]["zh_text"] == "你好"
    assert "by_lang" in rows[0]
    assert len(rows[0]["by_lang"]) == 1


def test_persist_immutable_does_not_mutate_inputs():
    from output_lang_persist import build_output_translations

    src = [{"start": 0, "end": 1}]
    first = [{"text": "x"}]
    src_before = copy.deepcopy(src)
    first_before = copy.deepcopy(first)

    build_output_translations(src, [("zh", first)])

    assert src == src_before
    assert first == first_before


def test_persist_missing_segment_text_yields_empty_string():
    """If a lang's segment list is shorter than source, the row gets empty string."""
    from output_lang_persist import build_output_translations

    rows = build_output_translations(
        [{"start": 0, "end": 1}, {"start": 1, "end": 2}],
        [("zh", [{"text": "只有一句"}])]   # only 1 seg for 2 sources
    )
    assert rows[0]["zh_text"] == "只有一句"
    assert rows[1]["zh_text"] == ""
    assert rows[1]["by_lang"]["zh"]["text"] == ""


def test_persist_row_has_idx_and_flags():
    from output_lang_persist import build_output_translations

    rows = build_output_translations(
        [{"start": 0, "end": 1}],
        [("yue", [{"text": "hi"}])]
    )
    assert rows[0]["by_lang"]["yue"]["flags"] == []
    assert rows[0].get("idx") == 0  # implementation uses "idx"


def test_persist_multiple_rows_correct_indices():
    """idx must match position in source_segments, not hardcoded."""
    from output_lang_persist import build_output_translations

    src = [{"start": i, "end": i + 1} for i in range(3)]
    segs = [{"text": f"seg{i}"} for i in range(3)]
    rows = build_output_translations(src, [("yue", segs)])

    for i, row in enumerate(rows):
        assert row["idx"] == i
        assert row["start"] == i
        assert row["end"] == i + 1
        assert row["yue_text"] == f"seg{i}"


def test_persist_authoritative_mirror_not_shadowed():
    """
    The {lang}_text mirror must come from the translation text, not from any
    raw source field — the B2 9e3ef67 lesson: never let a source value shadow
    the authoritative translation output.
    """
    from output_lang_persist import build_output_translations

    # Simulate a source segment that happens to also have a 'yue_text' key
    # (old stale data); the output row's yue_text should be the translation text.
    src = [{"start": 0, "end": 1, "yue_text": "STALE_DO_NOT_USE"}]
    segs = [{"text": "正確翻譯"}]
    rows = build_output_translations(src, [("yue", segs)])

    assert rows[0]["yue_text"] == "正確翻譯"
    assert rows[0]["by_lang"]["yue"]["text"] == "正確翻譯"


def test_persist_seg_without_text_key_yields_empty_string():
    """Segments that have no 'text' key at all must not raise KeyError."""
    from output_lang_persist import build_output_translations

    rows = build_output_translations(
        [{"start": 0, "end": 1}],
        [("zh", [{}])]   # segment has no 'text' key
    )
    assert rows[0]["zh_text"] == ""
    assert rows[0]["by_lang"]["zh"]["text"] == ""


def test_persist_empty_source_returns_empty_list():
    from output_lang_persist import build_output_translations

    rows = build_output_translations([], [("zh", [])])
    assert rows == []


def test_persist_empty_lang_pairs_returns_rows_without_by_lang_entries():
    """If no language pairs provided, rows still have start/end/idx/status/by_lang."""
    from output_lang_persist import build_output_translations

    rows = build_output_translations([{"start": 0, "end": 1}], [])
    assert len(rows) == 1
    assert rows[0]["by_lang"] == {}
    assert rows[0]["idx"] == 0
    assert rows[0]["status"] == "pending"


def test_persist_returns_new_list_not_same_object():
    """Return value must be a NEW list (immutability)."""
    from output_lang_persist import build_output_translations

    src = [{"start": 0, "end": 1}]
    segs = [{"text": "hi"}]
    result = build_output_translations(src, [("zh", segs)])
    assert result is not src
    assert result[0] is not src[0]
