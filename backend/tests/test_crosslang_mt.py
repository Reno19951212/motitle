from translation.crosslang_mt import translate_segments, build_mt_system_prompt


def test_translate_preserves_timing_and_count():
    segs = [{"start": 1.0, "end": 2.0, "text": "你好"}, {"start": 2.0, "end": 3.0, "text": "再見"}]
    calls = []

    def fake_llm(system, user):
        calls.append((system, user))
        return {"你好": "Hello", "再見": "Goodbye"}[user]

    out = translate_segments(segs, "yue", "en", fake_llm)
    assert [s["text"] for s in out] == ["Hello", "Goodbye"]
    assert [(s["start"], s["end"]) for s in out] == [(1.0, 2.0), (2.0, 3.0)]
    assert "English" in calls[0][0]


def test_translate_skips_empty_without_calling_llm():
    segs = [{"start": 0.0, "end": 1.0, "text": "  "}]
    called = []
    out = translate_segments(segs, "cmn", "ja", lambda s, u: called.append(u) or "x")
    assert out[0]["text"] == ""
    assert called == []


def test_translate_strips_think_and_label_prefix():
    segs = [{"start": 0.0, "end": 1.0, "text": "你好"}]
    out = translate_segments(segs, "yue", "ja", lambda s, u: "<think>x</think>\n譯文：こんにちは\n（注）")
    assert out[0]["text"] == "こんにちは"


def test_translate_strips_trailing_ellipsis_but_keeps_period():
    # Subtitles show cues one-by-one, so a trailing …/……/... the model adds to
    # "open" fragments looks like a bug on screen. _clean strips it, but a normal
    # sentence-ending 。 must survive.
    segs = [{"start": float(i), "end": float(i + 1), "text": t} for i, t in enumerate("abc")]
    outs = iter(["在中段稍微……", "他當時…", "正常一句。"])
    res = translate_segments(segs, "en", "zh", lambda s, u: next(outs))
    assert [r["text"] for r in res] == ["在中段稍微", "他當時", "正常一句。"]


def test_build_prompt_targets():
    assert "口語廣東話" in build_mt_system_prompt("cmn", "yue")
    assert "日本語" in build_mt_system_prompt("yue", "ja")
    assert "繁體中文書面語" in build_mt_system_prompt("en", "zh")
    # en->cmn now routes to the style template (default generic), which is a written-Chinese
    # template (繁體中文書面語); _MT_TARGET_NAME["cmn"] ("普通話書面中文") no longer appears
    assert "繁體中文書面語" in build_mt_system_prompt("en", "cmn")


def test_translate_does_not_mutate_input():
    segs = [{"start": 1.0, "end": 2.0, "text": "你好"}]
    translate_segments(segs, "yue", "en", lambda s, u: "Hi")
    assert segs[0]["text"] == "你好"
