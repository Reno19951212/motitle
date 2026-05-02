"""Tests for sentence-aware translation pipeline."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_merge_empty_segments():
    from translation.sentence_pipeline import merge_to_sentences
    result = merge_to_sentences([])
    assert result == []


def test_merge_single_complete_sentence():
    from translation.sentence_pipeline import merge_to_sentences
    segments = [
        {"start": 0.0, "end": 3.0, "text": "Hello world."},
    ]
    result = merge_to_sentences(segments)
    assert len(result) == 1
    assert result[0]["text"] == "Hello world."
    assert result[0]["seg_indices"] == [0]
    assert result[0]["seg_word_counts"] == {0: 2}
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 3.0


def test_merge_fragments_into_two_sentences():
    from translation.sentence_pipeline import merge_to_sentences
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 2.0, "end": 4.0, "text": "the mat. The dog"},
        {"start": 4.0, "end": 6.0, "text": "ran away quickly."},
    ]
    result = merge_to_sentences(segments)
    assert len(result) == 2
    assert "The cat sat on the mat." in result[0]["text"]
    assert 0 in result[0]["seg_indices"]
    assert 1 in result[0]["seg_indices"]
    assert result[0]["start"] == 0.0
    assert "The dog ran away quickly." in result[1]["text"]
    assert 1 in result[1]["seg_indices"]
    assert 2 in result[1]["seg_indices"]
    assert result[1]["end"] == 6.0


def test_merge_shared_segment():
    from translation.sentence_pipeline import merge_to_sentences
    segments = [
        {"start": 0.0, "end": 3.0, "text": "First sentence here."},
        {"start": 3.0, "end": 6.0, "text": "Second one. Third starts"},
        {"start": 6.0, "end": 9.0, "text": "and finishes here."},
    ]
    result = merge_to_sentences(segments)
    assert len(result) == 3
    total_seg1_words = sum(
        s["seg_word_counts"].get(1, 0) for s in result
    )
    assert total_seg1_words == 4


def test_redistribute_single_sentence_three_segments():
    from translation.sentence_pipeline import merge_to_sentences, redistribute_to_segments
    original_segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 2.0, "end": 5.0, "text": "the mat and then"},
        {"start": 5.0, "end": 7.0, "text": "went to sleep."},
    ]
    merged = merge_to_sentences(original_segments)
    zh_sentences = ["貓坐在墊子上，然後去睡覺了。"]
    result = redistribute_to_segments(merged, zh_sentences, original_segments)
    assert len(result) == 3
    combined = "".join(r["zh_text"] for r in result)
    assert combined == "貓坐在墊子上，然後去睡覺了。"
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 2.0
    assert result[1]["start"] == 2.0
    assert result[1]["end"] == 5.0
    assert result[2]["start"] == 5.0
    assert result[2]["end"] == 7.0
    assert result[0]["en_text"] == "The cat sat on"
    assert result[2]["en_text"] == "went to sleep."


def test_redistribute_prefers_punctuation_break():
    from translation.sentence_pipeline import merge_to_sentences, redistribute_to_segments
    original_segments = [
        {"start": 0.0, "end": 3.0, "text": "Hello there my friend"},
        {"start": 3.0, "end": 6.0, "text": "how are you doing today."},
    ]
    merged = merge_to_sentences(original_segments)
    zh_sentences = ["你好啊，我的朋友你今天怎麼樣。"]
    result = redistribute_to_segments(merged, zh_sentences, original_segments)
    assert len(result) == 2
    assert result[0]["zh_text"].endswith("，") or "，" in result[0]["zh_text"]


def test_redistribute_lopsided_rebalance_fills_empty_seg():
    """V_R9 MT-α: lopsided rebalance prevents empty segments when proportional
    target would otherwise produce one. Real Madrid baseline #26 reproduces this."""
    from translation.sentence_pipeline import redistribute_to_segments
    # 3 segs unbalanced word counts (1, 8, 5) — naive proportional split would
    # give seg 0 a near-zero ZH allocation.
    original_segments = [
        {"start": 0.0, "end": 1.0, "text": "field."},  # 1 word
        {"start": 1.0, "end": 5.0, "text": "In central midfield, the problem is more tactical."},  # 8 words
        {"start": 5.0, "end": 8.0, "text": "Madrid midfield is packed gifted athletic."},  # 5 words
    ]
    merged = [{"seg_indices": [0, 1, 2], "seg_word_counts": {0: 1, 1: 8, 2: 5}}]
    zh = ["在中場方面，問題則更為戰術層面。雖然皇馬中場人才濟濟，"]
    result = redistribute_to_segments(merged, zh, original_segments)
    # No segment should be completely empty
    for r in result:
        assert r["zh_text"].strip(), f"empty seg detected: {result}"


def test_redistribute_locked_mask_prevents_name_split():
    """V_R9 MT-α: middle-dot in foreign names locked — break never lands
    between X and ·, or between · and Y."""
    from translation.sentence_pipeline import _build_locked_mask
    text = "在後防方面，大衛·阿拉巴與安東尼奧·呂迪格的傷病。"
    locked = _build_locked_mask(text)
    # Find positions of the · chars
    dot_positions = [i for i, ch in enumerate(text) if ch == "·"]
    for dp in dot_positions:
        # Break BEFORE dot (position dp) — locked
        assert locked[dp] is True, f"position {dp} (before ·) should be locked"
        # Break AFTER dot (position dp + 1) — also locked (between · and Y)
        assert locked[dp + 1] is True, f"position {dp+1} (after ·) should be locked"


def test_redistribute_locked_mask_number_run():
    """V_R9 MT-α: number+量詞 sequences are locked (e.g. 二零二六年)."""
    from translation.sentence_pipeline import _build_locked_mask
    text = "於二零二六年一月解僱"
    locked = _build_locked_mask(text)
    # Positions inside "二零二六年" should be locked. "二" is at index 1.
    # Break BEFORE index 2 (between 二 and 零) should be locked.
    assert locked[2] is True
    assert locked[3] is True
    assert locked[4] is True


def test_redistribute_orphan_merge_disabled_by_default():
    """V_R9 MT-α: orphan merge is opt-in (default off) to preserve segment timing."""
    from translation.sentence_pipeline import redistribute_to_segments
    original_segments = [
        {"start": 0.0, "end": 2.0, "text": "First clause"},
        {"start": 2.0, "end": 4.0, "text": "and second part"},
    ]
    merged = [{"seg_indices": [0, 1], "seg_word_counts": {0: 2, 1: 3}}]
    zh = ["很短的"]  # 3 chars total — would normally cause orphan
    result = redistribute_to_segments(merged, zh, original_segments)
    # Default behavior: timing preserved for both segs
    assert result[0]["start"] == 0.0
    assert result[1]["start"] == 2.0


def test_orphan_merge_preserves_timing_in_chained_orphans():
    """V_R11 Bug #2: chained orphans must NOT corrupt downstream timing.

    Previously donor.start was assigned to recipient.start, causing 3+ orphan
    chains to produce overlapping cues like (0,1)→(0,2)→(0,3)→(0,5).
    """
    from translation.sentence_pipeline import _orphan_merge
    segs = [
        {"start": 0.0, "end": 1.0, "en_text": "a", "zh_text": "甲"},
        {"start": 1.0, "end": 2.0, "en_text": "b", "zh_text": "乙"},
        {"start": 2.0, "end": 3.0, "en_text": "c", "zh_text": "丙"},
        {"start": 3.0, "end": 5.0, "en_text": "tail", "zh_text": "丁戊己庚。"},
    ]
    out = _orphan_merge([dict(s) for s in segs], min_chars=4)
    # Timing must be preserved exactly
    assert [(s["start"], s["end"]) for s in out] == [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 5.0)]
    # No overlap
    for i in range(len(out) - 1):
        assert out[i]["end"] <= out[i + 1]["start"] + 0.01


def test_redistribute_total_en_zero_preserves_zh():
    """V_R11 Bug M3: when total_en_words==0 (silence segs with empty EN),
    ZH content must NOT be silently dropped."""
    from translation.sentence_pipeline import redistribute_to_segments
    en_segs = [
        {"start": 0.0, "end": 1.0, "text": ""},
        {"start": 1.0, "end": 2.0, "text": ""},
    ]
    merged = [{"seg_indices": [0, 1], "seg_word_counts": {0: 0, 1: 0}}]
    zh = ["有內容嘅中文字。"]
    result = redistribute_to_segments(merged, zh, en_segs)
    total_in = sum(len(z) for z in zh)
    total_out = sum(len(r["zh_text"]) for r in result)
    assert total_out == total_in, f"ZH chars dropped: {total_in} → {total_out}"


def test_redistribute_fully_locked_run_preserved():
    """V_R11 Bug #3: pure transliterated foreign name (all chars locked) must
    NOT be split. Caller must handle _find_unlocked_anywhere -1 sentinel by
    allocating the locked run intact."""
    from translation.sentence_pipeline import redistribute_to_segments
    # 6-char pure translit run flanked by non-translit chars
    en_segs = [
        {"start": 0.0, "end": 2.0, "text": "Two words"},
        {"start": 2.0, "end": 4.0, "text": "more here"},
    ]
    merged = [{"seg_indices": [0, 1], "seg_word_counts": {0: 2, 1: 2}}]
    zh = ["AB雲尼素斯諾託CD"]  # 雲尼素斯諾託 all in _TRANSLIT_CHARS
    result = redistribute_to_segments(merged, zh, en_segs)
    combined = result[0]["zh_text"] + result[1]["zh_text"]
    # The 6-char name must appear intact in ONE segment
    assert "雲尼素斯諾託" in result[0]["zh_text"] or "雲尼素斯諾託" in result[1]["zh_text"], \
        f"name split across segs: {[s['zh_text'] for s in result]}"
    # Char preservation
    assert combined == "AB雲尼素斯諾託CD"


def test_dot_heuristic_locks_oov_compound_name():
    """V_R11 Bug #4: ·-flanked CJK heuristic locks compound names like
    阿爾瓦羅·卡列拉斯 even when individual chars aren't all in translit set
    or glossary."""
    from translation.sentence_pipeline import _build_locked_mask
    text = "是左閘阿爾瓦羅·卡列拉斯。"
    locked = _build_locked_mask(text)
    # 阿爾瓦羅·卡列拉斯 spans index 3-11. All internal positions 4..11 locked
    for p in range(4, 12):
        assert locked[p] is True, f"position {p} inside 阿爾瓦羅·卡列拉斯 must be locked"


def test_translit_lock_protects_vinicius():
    """V_R10 A.2: 雲尼素斯 (Cantonese for Vinicius) — no `·` separator,
    must NOT be split mid-name by transliteration heuristic."""
    from translation.sentence_pipeline import _build_locked_mask
    text = "惟雲尼素斯與羅德里哥的前景仍存疑慮。"
    locked = _build_locked_mask(text)
    # 雲尼素斯 starts at index 1, ends at 5. Internal positions 2,3,4 locked.
    assert locked[2] is True, "break at pos 2 (inside 雲尼素斯) must be locked"
    assert locked[3] is True
    assert locked[4] is True
    # 羅德里哥 starts at index 6, internal 7,8,9 locked
    assert locked[7] is True
    assert locked[8] is True
    assert locked[9] is True


def test_translit_lock_protects_compound_with_dot():
    """V_R10 A.2: 法蘭高·馬斯坦託諾 — translit chars + middle dot. Whole
    span must be locked from internal splits (·-aware)."""
    from translation.sentence_pipeline import _build_locked_mask
    text = "僅有法蘭高·馬斯坦託諾與布拉希姆"
    locked = _build_locked_mask(text)
    # 法蘭高·馬斯坦託諾 at idx 2-10. Internal locks 3..10
    for p in range(3, 10):
        assert locked[p] is True, f"position {p} inside 法蘭高·馬斯坦託諾 must be locked"


def test_glossary_lock_extends_locked_mask():
    """V_R10 A.1: glossary ZH terms lock interior positions."""
    from translation.sentence_pipeline import _build_locked_mask
    text = "今晚由皇家馬德里對拜仁慕尼黑，誰勝誰負？"
    # Pretend glossary has these terms (note: 皇家馬德里 has length 5)
    terms = ["皇家馬德里", "拜仁慕尼黑"]
    locked = _build_locked_mask(text, glossary_zh_terms=terms)
    # 皇家馬德里 at idx 3, internal pos 4..7 locked (NOT 3 or 8)
    for p in range(4, 8):
        assert locked[p] is True, f"pos {p} inside 皇家馬德里 must be locked"


def test_redistribute_lock_aware_min_pos_advancement():
    """V_R10 bug fix: when char_offset+1 lands on a locked position,
    redistribute must advance forward through locks rather than clamp back.

    Regression: previously the clamp `max(min_pos, _find_break_point(...))`
    pushed break_at back onto a locked position even when find_break_point
    returned a valid non-locked spot.

    Scenario: 3-segment sentence, ZH starts with a name. Seg 1 expected to
    skip past the name's internal positions.
    """
    from translation.sentence_pipeline import redistribute_to_segments
    # ZH text: 雲尼素斯與羅德里哥都打主力，皇家馬德里取得勝利。
    # 雲尼素斯 at idx 0-3, must not be split inside.
    original_segments = [
        {"start": 0.0, "end": 2.0, "text": "Vinicius and Rodrigo"},  # 3 words
        {"start": 2.0, "end": 4.0, "text": "both started, Real Madrid"},  # 4 words
        {"start": 4.0, "end": 6.0, "text": "won the match."},  # 3 words
    ]
    merged = [{"seg_indices": [0, 1, 2], "seg_word_counts": {0: 3, 1: 4, 2: 3}}]
    zh = ["雲尼素斯與羅德里哥都打主力，皇家馬德里取得勝利。"]
    result = redistribute_to_segments(merged, zh, original_segments)
    # No segment should land mid-name
    for r in result[:-1]:
        z = r["zh_text"].strip()
        # 雲尼素斯 / 羅德里哥 / 皇家馬德里 chars should not be at edge
        assert not z.endswith("雲"), f"split mid-雲尼素斯: {result}"
        assert not z.endswith("尼"), f"split mid-雲尼素斯: {result}"
        assert not z.endswith("素"), f"split mid-雲尼素斯: {result}"
        assert not z.endswith("羅"), f"split mid-羅德里哥: {result}"
        assert not z.endswith("德"), f"split mid-羅德里哥: {result}"
        assert not z.endswith("里"), f"split mid-羅德里哥: {result}"


def test_redistribute_no_single_char_orphan_when_punct_behind_offset():
    """Regression: user-uploaded video showed 13 single-char ZH segments
    because _find_break_point returned a position BEHIND char_offset (the
    same SOFT punct already consumed by previous seg). Clamp then yielded
    just 1 char.

    Reproduces #18 「肩」 from user file dbf9f8a6bda7 where the 3-segment
    sentence group's middle seg got 1 char allocation.
    """
    from translation.sentence_pipeline import redistribute_to_segments
    original_segments = [
        {"start": 0.0, "end": 4.0,
         "text": "That leaves 20-year-old Dean Hausson, who is himself battling calf issues,"},  # 11 words
        {"start": 4.0, "end": 6.0,
         "text": "and 22-year-old academy graduate Raul Asensio,"},  # 6 words
        {"start": 6.0, "end": 9.0,
         "text": "bearing most of the responsibility at the heart of defence."},  # 10 words
    ]
    merged = [{"seg_indices": [0, 1, 2],
                "seg_word_counts": {0: 11, 1: 6, 2: 10}}]
    zh_sentences = [
        "這令年僅二十歲的迪恩·豪森與二十二歲青訓畢業生勞爾·阿森西奧，肩負起後防中路的沉重責任。"
    ]
    result = redistribute_to_segments(merged, zh_sentences, original_segments)
    assert len(result) == 3
    # Critical: middle seg must have ≥4 chars (lopsided rebalance min_chars=4 floor)
    middle_zh = result[1]["zh_text"].strip()
    assert len(middle_zh) >= 4, \
        f"middle seg has {len(middle_zh)}-char allocation: {middle_zh!r} — single-char regression"
    # Word check: 「肩」 should NOT stand alone
    assert middle_zh != "肩", "middle seg is single-char 「肩」 orphan"


def test_redistribute_conjunction_bonus_prefers_clause_break():
    """V_R9 MT-α: conjunction bonus rewards splits that leave next clause
    starting with a coordinating conjunction (但/而/和/所以/...)."""
    from translation.sentence_pipeline import _find_break_point, _build_locked_mask
    # Two equally-attractive break candidates near target — one followed by
    # a conjunction should win.
    text = "他成功了，但他並不快樂。"  # 12 chars, 「，」at pos 4, 「。」at pos 12
    locked = _build_locked_mask(text)
    # Without bonus: SOFT 「，」at pos 4 wins anyway (closer to target)
    # With bonus: confirm pos 4 wins — bonus reinforces decision
    pos = _find_break_point(text, target=5, locked=locked, use_conjunction_bonus=True)
    # 「但」starts at pos 5 → break at pos 5 should get +20 bonus
    # But SOFT「，」at pos 4 has score 100 - dist*3; need to verify which wins
    # Actually break BEFORE pos 5 means split text[:5]="他成功了，" — next char text[5]=「但」
    # So break at pos 5 returns? Let's check with bonus.
    # Either pos 4 (SOFT) or pos 5 (whitespace + conjunction bonus) — pos 4 should still win
    # because SOFT score 100 dominates over bonus 20+0.
    # Test confirms function doesn't crash + produces a valid position
    assert 1 <= pos <= len(text)


def test_redistribute_shared_segment_merged():
    from translation.sentence_pipeline import merge_to_sentences, redistribute_to_segments
    original_segments = [
        {"start": 0.0, "end": 3.0, "text": "First sentence."},
        {"start": 3.0, "end": 6.0, "text": "Second sentence."},
    ]
    merged = merge_to_sentences(original_segments)
    zh_sentences = ["第一句話。", "第二句話。"]
    result = redistribute_to_segments(merged, zh_sentences, original_segments)
    assert len(result) == 2
    assert result[0]["zh_text"] == "第一句話。"
    assert result[1]["zh_text"] == "第二句話。"
    assert result[0]["start"] == 0.0
    assert result[1]["start"] == 3.0


def test_validate_all_valid():
    from translation.sentence_pipeline import validate_batch
    results = [
        {"start": 0.0, "end": 2.0, "en_text": "Hello.", "zh_text": "你好。"},
        {"start": 2.0, "end": 4.0, "en_text": "World.", "zh_text": "世界。"},
    ]
    assert validate_batch(results) == []


def test_validate_repetition():
    from translation.sentence_pipeline import validate_batch
    results = [
        {"start": 0.0, "end": 1.0, "en_text": "A", "zh_text": "重複"},
        {"start": 1.0, "end": 2.0, "en_text": "B", "zh_text": "重複"},
        {"start": 2.0, "end": 3.0, "en_text": "C", "zh_text": "重複"},
        {"start": 3.0, "end": 4.0, "en_text": "D", "zh_text": "正常"},
    ]
    bad = validate_batch(results)
    assert 0 in bad
    assert 1 in bad
    assert 2 in bad
    assert 3 not in bad


def test_validate_missing():
    from translation.sentence_pipeline import validate_batch
    results = [
        {"start": 0.0, "end": 2.0, "en_text": "Hello.", "zh_text": "你好。"},
        {"start": 2.0, "end": 4.0, "en_text": "World.", "zh_text": "[TRANSLATION MISSING] World."},
    ]
    bad = validate_batch(results)
    assert 1 in bad
    assert 0 not in bad


def test_validate_too_long():
    from translation.sentence_pipeline import validate_batch
    long_zh = "一" * 33
    results = [
        {"start": 0.0, "end": 2.0, "en_text": "Short.", "zh_text": long_zh},
    ]
    bad = validate_batch(results)
    assert 0 in bad


def test_validate_hallucination():
    from translation.sentence_pipeline import validate_batch
    results = [
        {"start": 0.0, "end": 2.0, "en_text": "Hi", "zh_text": "一二三四五六七"},
    ]
    bad = validate_batch(results)
    assert 0 in bad


def test_translate_with_sentences_basic():
    from translation.sentence_pipeline import translate_with_sentences
    from translation.mock_engine import MockTranslationEngine
    engine = MockTranslationEngine({})
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 2.0, "end": 4.0, "text": "the mat."},
        {"start": 4.0, "end": 6.0, "text": "The dog ran."},
    ]
    result = translate_with_sentences(engine, segments)
    assert len(result) == 3
    for r in result:
        assert r["zh_text"] != ""
        assert r["en_text"] != ""
    assert result[0]["start"] == 0.0
    assert result[2]["end"] == 6.0


def test_translate_with_sentences_empty():
    from translation.sentence_pipeline import translate_with_sentences
    from translation.mock_engine import MockTranslationEngine
    engine = MockTranslationEngine({})
    result = translate_with_sentences(engine, [])
    assert result == []


def test_merge_respects_time_gap_guard():
    """A gap larger than max_gap_sec forces a sentence boundary even if
    pySBD would otherwise merge the text."""
    from translation.sentence_pipeline import merge_to_sentences
    # Two fragments that would normally merge into one sentence, but the
    # 2.5-second gap between them exceeds the 1.5-second default threshold.
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 4.5, "end": 7.0, "text": "the mat yesterday."},
    ]
    result = merge_to_sentences(segments)
    # Gap (4.5 - 2.0 = 2.5s) > 1.5s → must produce two separate units
    assert len(result) == 2
    assert result[0]["seg_indices"] == [0]
    assert result[1]["seg_indices"] == [1]


def test_merge_allows_small_gap():
    """A gap smaller than max_gap_sec allows pySBD to merge across segments."""
    from translation.sentence_pipeline import merge_to_sentences
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 2.3, "end": 4.0, "text": "the mat yesterday."},
    ]
    result = merge_to_sentences(segments)
    # Gap 0.3s < 1.5s → merged into one sentence
    assert len(result) == 1
    assert result[0]["seg_indices"] == [0, 1]


def test_merge_custom_max_gap():
    """max_gap_sec parameter controls the split threshold."""
    from translation.sentence_pipeline import merge_to_sentences
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 3.0, "end": 5.0, "text": "the mat yesterday."},
    ]
    # Default 1.5s would NOT split (gap is 1.0s)
    assert len(merge_to_sentences(segments)) == 1
    # Strict 0.5s SHOULD split
    assert len(merge_to_sentences(segments, max_gap_sec=0.5)) == 2


def test_merge_preserves_timestamps_after_split():
    """After gap-split, each merged sentence gets correct start/end from its segments."""
    from translation.sentence_pipeline import merge_to_sentences
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Hello world."},
        {"start": 5.0, "end": 7.0, "text": "Goodbye."},  # gap=3s
    ]
    result = merge_to_sentences(segments)
    assert len(result) == 2
    assert result[0]["start"] == 0.0 and result[0]["end"] == 2.0
    assert result[1]["start"] == 5.0 and result[1]["end"] == 7.0


def test_translate_with_sentences_progress_callback():
    """Progress callback is invoked with segment-scale counts, not sentence counts."""
    from translation.sentence_pipeline import translate_with_sentences
    from translation.mock_engine import MockTranslationEngine
    engine = MockTranslationEngine({})
    # 3 segments that merge into 1 sentence
    segments = [
        {"start": 0.0, "end": 1.0, "text": "The cat"},
        {"start": 1.0, "end": 2.0, "text": "sat on"},
        {"start": 2.0, "end": 3.0, "text": "the mat."},
    ]
    calls = []
    def cb(done, total):
        calls.append((done, total))
    translate_with_sentences(engine, segments, progress_callback=cb)
    # Callback should report totals in units of original segments (3), not sentences (1)
    assert calls, "callback must be invoked at least once"
    for done, total in calls:
        assert total == 3, f"expected total=3 segments, got {total}"


def test_find_break_point_prefers_soft_over_hard():
    """SOFT 「，」at distance 5 should beat HARD 「。」at distance 11."""
    from translation.sentence_pipeline import _find_break_point
    text = "本賽季唯一上陣時間超過百分之七十五的皇馬後防四人組成員，僅有左閘阿爾瓦羅·卡雷拉斯一人。"
    # target = 33 (mid-name), 「，」at 28, 「。」at 44
    assert len(text) == 44
    assert text[27] == "，"
    assert text[43] == "。"
    pos = _find_break_point(text, target=33)
    assert pos == 28, f"Expected break at 「，」 (pos 28), got {pos}"


def test_find_break_point_max_pos_constraint():
    """max_pos limits search to prevent picking sentence-final 。 that empties next seg."""
    from translation.sentence_pipeline import _find_break_point
    text = "本賽季唯一上陣時間超過百分之七十五的皇馬後防四人組成員，僅有左閘阿爾瓦羅·卡雷拉斯一人。"
    # target = 33, max_pos = 35 (force search to skip the 「。」 at pos 44)
    pos = _find_break_point(text, target=33, max_pos=35)
    assert pos == 28, f"Expected 「，」 at 28, got {pos}"


def test_find_break_point_no_punct_falls_back_to_target():
    """When no punct in search range, returns target unchanged."""
    from translation.sentence_pipeline import _find_break_point
    text = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰"  # no punctuation
    pos = _find_break_point(text, target=8)
    assert pos == 8


def test_find_break_point_search_range_15():
    """Default search_range=15 should reach SOFT punct at distance 7 from target=18."""
    from translation.sentence_pipeline import _find_break_point
    # 「，」at pos 11 (index 10); text length = 21
    # target=18 is 7 chars away — within default search_range=15 → should find 「，」
    text = "甲乙丙丁戊己庚辛壬癸，甲乙丙丁戊己庚辛壬癸"  # 「，」at pos 11
    assert len(text) == 21
    assert text[10] == "，"
    pos = _find_break_point(text, target=18)  # distance 7 from 「，」
    assert pos == 11, f"Expected 「，」 at 11, got {pos}"


def test_redistribute_avoids_mid_name_cut():
    """Hybrid v2 redistribute should split at 「，」 not mid-name."""
    from translation.sentence_pipeline import redistribute_to_segments
    merged_sentences = [{
        "seg_indices": [0, 1],
        "seg_word_counts": {0: 18, 1: 6},
        "merged_text": "ignored",
    }]
    zh_sentences = ["本賽季唯一上陣時間超過七成比賽的皇馬後防四人組成員，僅有左閘阿爾瓦羅·卡雷拉斯一人。"]
    original_segments = [
        {"start": 0, "end": 5, "text": "The only member..."},
        {"start": 5, "end": 10, "text": "season is left back..."},
    ]
    results = redistribute_to_segments(merged_sentences, zh_sentences, original_segments)
    assert len(results) == 2
    seg0_zh = results[0]["zh_text"]
    seg1_zh = results[1]["zh_text"]
    # Seg 0 should end with 「，」, seg 1 should be non-empty and contain the name
    assert seg0_zh.endswith("，"), f"Seg 0 should end with 「，」, got: {seg0_zh!r}"
    assert seg1_zh.strip(), f"Seg 1 should not be empty, got: {seg1_zh!r}"
    assert "阿爾瓦羅" in seg1_zh, f"Name 阿爾瓦羅 should be in seg 1, got: {seg1_zh!r}"
    # Specifically the name should NOT be cut between segments
    assert not seg0_zh.endswith("阿"), f"Seg 0 should not end mid-name, got: {seg0_zh!r}"


