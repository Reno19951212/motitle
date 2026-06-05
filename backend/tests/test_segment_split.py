import json

import segment_split as ss


def test_normalize_strips_space_punct_and_lowercases_latin():
    assert ss.normalize("Hello,  World!") == "helloworld"


def test_normalize_cjk_drops_punct_keeps_chars():
    assert ss.normalize("你好，世界。") == ss.normalize("你好世界")


def test_normalize_trad_simp_equal_via_t2s():
    # 「實」(trad) vs 「实」(simp) normalize to the same simplified form
    assert ss.normalize("實時") == ss.normalize("实时")


def test_merge_text_joins_with_single_space_trimmed():
    assert ss.merge_text("你好", "世界") == "你好 世界"
    assert ss.merge_text("  a ", " b  ") == "a b"
    assert ss.merge_text("", "x") == "x"


def test_compute_split_ratio_basic():
    assert ss.compute_split_ratio("12345", "1234567890") == 0.5


def test_compute_split_ratio_clamped_low_and_high():
    assert ss.compute_split_ratio("x", "x" * 100) == 0.15      # 0.01 -> clamp 0.15
    assert ss.compute_split_ratio("x" * 99, "x" * 100) == 0.85  # 0.99 -> clamp 0.85


def test_compute_split_ratio_empty_full_is_half():
    assert ss.compute_split_ratio("", "") == 0.5


def test_mechanical_parts_duplicates_each_language():
    out = ss.mechanical_parts({"yue": "你好世界", "en": "hello world"})
    assert out == {"yue": ("你好世界", "你好世界"), "en": ("hello world", "hello world")}


def test_mechanical_parts_handles_empty():
    assert ss.mechanical_parts({"yue": ""}) == {"yue": ("", "")}


def test_parse_split_response_plain_json_bilingual():
    raw = '{"parts": [{"yue": "你好", "en": "hello"}, {"yue": "世界", "en": "world"}]}'
    texts = {"yue": "你好世界", "en": "hello world"}
    out = ss.parse_split_response(raw, texts, content_lang="yue")
    assert out == {"yue": ("你好", "世界"), "en": ("hello", "world")}


def test_parse_split_response_strips_markdown_fence():
    raw = '```json\n{"parts": [{"yue": "你好"}, {"yue": "世界"}]}\n```'
    out = ss.parse_split_response(raw, {"yue": "你好世界"}, content_lang="yue")
    assert out == {"yue": ("你好", "世界")}


def test_parse_split_response_extracts_json_from_preamble():
    raw = '好的，結果係：{"parts": [{"yue": "你好"}, {"yue": "世界"}]} 完成'
    out = ss.parse_split_response(raw, {"yue": "你好世界"}, content_lang="yue")
    assert out == {"yue": ("你好", "世界")}


def test_parse_split_response_rejects_content_change():
    # LLM dropped a character -> reconstruction fails -> None (caller falls back)
    raw = '{"parts": [{"yue": "你好"}, {"yue": "世"}]}'
    assert ss.parse_split_response(raw, {"yue": "你好世界"}, content_lang="yue") is None


def test_parse_split_response_rejects_empty_source_part():
    raw = '{"parts": [{"yue": ""}, {"yue": "你好世界"}]}'
    assert ss.parse_split_response(raw, {"yue": "你好世界"}, content_lang="yue") is None


def test_parse_split_response_allows_empty_nonsource_part():
    # source yue splits cleanly; en second part empty is tolerated
    raw = '{"parts": [{"yue": "你好", "en": "hi there"}, {"yue": "世界", "en": ""}]}'
    out = ss.parse_split_response(raw, {"yue": "你好世界", "en": "hi there"}, content_lang="yue")
    assert out == {"yue": ("你好", "世界"), "en": ("hi there", "")}


def test_parse_split_response_unparseable_returns_none():
    assert ss.parse_split_response("not json at all", {"yue": "你好"}, content_lang="yue") is None


def test_build_split_prompt_user_is_json_of_texts():
    texts = {"yue": "你好世界", "en": "hello"}
    assert json.loads(ss.build_split_prompt_user(texts)) == texts


def test_build_split_prompt_system_mentions_langs_and_json_and_punctuation():
    sysp = ss.build_split_prompt_system(["yue", "en"])
    assert "yue" in sysp and "en" in sysp
    assert "JSON" in sysp
    assert "標點" in sysp  # punctuation-priority instruction present


def _sample_state():
    base = [
        {"start": 0.0, "end": 10.0, "text": "你好世界"},
        {"start": 10.0, "end": 12.0, "text": "再見"},
    ]
    translations = [
        {"idx": 0, "start": 0.0, "end": 10.0, "status": "approved",
         "by_lang": {"yue": {"text": "你好世界", "status": "approved", "flags": []},
                     "en": {"text": "hello world", "status": "approved", "flags": []}},
         "yue_text": "你好世界", "en_text": "hello world", "glossary_changes": [{"a": 1}]},
        {"idx": 1, "start": 10.0, "end": 12.0, "status": "pending",
         "by_lang": {"yue": {"text": "再見", "status": "pending", "flags": []},
                     "en": {"text": "bye", "status": "pending", "flags": []}},
         "yue_text": "再見", "en_text": "bye", "glossary_changes": []},
    ]
    aligned = [
        {"start": 0.0, "end": 10.0, "by_lang": {"yue": "你好世界", "en": "hello world"}},
        {"start": 10.0, "end": 12.0, "by_lang": {"yue": "再見", "en": "bye"}},
    ]
    return base, translations, aligned


def test_split_base_inserts_two_segments_no_id_no_words():
    base, _, _ = _sample_state()
    out = ss.split_base(base, 0, "你好", "世界", 0.0, 5.0, 10.0)
    assert len(out) == 3
    assert out[0] == {"start": 0.0, "end": 5.0, "text": "你好"}
    assert out[1] == {"start": 5.0, "end": 10.0, "text": "世界"}
    assert out[2]["text"] == "再見"
    assert "id" not in out[0] and "words" not in out[0]


def test_split_translations_resets_status_and_sets_text_both_languages():
    _, translations, _ = _sample_state()
    parts = {"yue": ("你好", "世界"), "en": ("hello", "world")}
    out = ss.split_translations(translations, 0, parts, 0.0, 5.0, 10.0)
    assert len(out) == 3
    assert out[0]["by_lang"]["yue"]["text"] == "你好"
    assert out[0]["en_text"] == "hello"
    assert out[1]["by_lang"]["en"]["text"] == "world"
    assert out[0]["status"] == "pending" and out[1]["status"] == "pending"
    assert out[0]["glossary_changes"] == [] and out[1]["glossary_changes"] == []
    assert out[0]["start"] == 0.0 and out[0]["end"] == 5.0
    assert out[1]["start"] == 5.0 and out[1]["end"] == 10.0


def test_split_aligned_values_are_strings():
    _, _, aligned = _sample_state()
    parts = {"yue": ("你好", "世界"), "en": ("hello", "world")}
    out = ss.split_aligned(aligned, 0, parts, 0.0, 5.0, 10.0)
    assert out[0]["by_lang"]["yue"] == "你好"
    assert out[1]["by_lang"]["en"] == "world"
    assert out[0]["end"] == 5.0 and out[1]["start"] == 5.0


def test_renumber_translations_sets_sequential_idx():
    _, translations, _ = _sample_state()
    parts = {"yue": ("你好", "世界"), "en": ("hello", "world")}
    out = ss.renumber_translations(ss.split_translations(translations, 0, parts, 0.0, 5.0, 10.0))
    assert [t["idx"] for t in out] == [0, 1, 2]


def test_merge_base_unions_time_and_joins_text():
    base, _, _ = _sample_state()
    out = ss.merge_base(base, 0)
    assert len(out) == 1
    assert out[0] == {"start": 0.0, "end": 12.0, "text": "你好世界 再見"}


def test_merge_translations_joins_each_language_and_resets_pending():
    _, translations, _ = _sample_state()
    out = ss.merge_translations(translations, 0)
    assert len(out) == 1
    assert out[0]["by_lang"]["yue"]["text"] == "你好世界 再見"
    assert out[0]["by_lang"]["en"]["text"] == "hello world bye"
    assert out[0]["yue_text"] == "你好世界 再見"
    assert out[0]["status"] == "pending"
    assert out[0]["start"] == 0.0 and out[0]["end"] == 12.0
    assert out[0]["glossary_changes"] == [{"a": 1}]


def test_merge_aligned_joins_strings():
    _, _, aligned = _sample_state()
    out = ss.merge_aligned(aligned, 0)
    assert out[0]["by_lang"]["en"] == "hello world bye"
    assert out[0]["start"] == 0.0 and out[0]["end"] == 12.0
