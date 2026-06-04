from output_lang_postprocess import apply_script, clause_split_all, formal_refine


def test_apply_script_trad_simplified_to_hk():
    segs = [{"start": 0, "end": 1, "text": "我们简体"}]
    out = apply_script(segs, "trad")
    assert out[0]["text"] == "我們簡體"
    assert segs[0]["text"] == "我们简体"  # input untouched


def test_apply_script_simp_traditional_to_simplified():
    segs = [{"start": 0, "end": 1, "text": "我們繁體"}]
    out = apply_script(segs, "simp")
    assert out[0]["text"] == "我们繁体"


def test_apply_script_noop_for_non_chinese_passthrough():
    segs = [{"start": 0, "end": 1, "text": "Hello"}]
    assert apply_script(segs, "trad")[0]["text"] == "Hello"


def test_clause_split_all_splits_overcap_segment():
    segs = [{"start": 0.0, "end": 6.0, "text": "今晚我好高興同埋好榮幸，多謝各位嘉賓蒞臨出席"}]
    out = clause_split_all(segs, char_cap=18)
    assert len(out) == 2
    assert all(len(p["text"]) <= 18 for p in out)


def test_clause_split_all_keeps_short_segment():
    segs = [{"start": 0.0, "end": 2.0, "text": "今晚我好高興"}]
    assert len(clause_split_all(segs, char_cap=18)) == 1


def test_formal_refine_uses_llm_and_parses_json_text():
    segs = [{"start": 0, "end": 1, "text": "我哋今日嚟玩"}]
    out = formal_refine(segs, lambda system, user: '{"action":"rewrite","text":"我們今日進行遊戲"}')
    assert out[0]["text"] == "我們今日進行遊戲"


def test_formal_refine_plain_text_fallback():
    segs = [{"start": 0, "end": 1, "text": "我哋玩"}]
    out = formal_refine(segs, lambda system, user: "我們進行遊戲")
    assert out[0]["text"] == "我們進行遊戲"


def test_formal_refine_style_aware_default_neutral():
    # 2026-06-04: 書面語 refiner is style-aware. Default (generic) = neutral de-raced
    # prompt that forbids domain-term injection; 'racing' = the racing-flavoured V6 prompt.
    segs = [{"start": 0, "end": 1, "text": "佢好開心㗎"}]
    echo = lambda system, user: system  # echo the chosen system prompt back as the "refined" text
    racing = formal_refine(segs, echo, style="racing")[0]["text"]
    generic = formal_refine(segs, echo, style="generic")[0]["text"]
    default = formal_refine(segs, echo)[0]["text"]
    assert "賽馬術語" in racing               # racing prompt is racing-flavoured
    assert "賽馬術語" not in generic          # neutral prompt has no racing lock
    assert "特定領域術語" in generic          # …and explicitly forbids domain-term injection
    assert default == generic                # default == neutral (de-raced)


def test_derive_aligned_output_refine_passes_style():
    from output_lang_aligned import derive_aligned_output
    seen = {}
    def capture(system, user):
        seen["sys"] = system
        return user
    # yue→zh is 'refine'; the style must reach formal_refine's prompt choice.
    derive_aligned_output([{"start": 0, "end": 1, "text": "佢好開心"}], "yue", "zh", "trad", capture, style="racing")
    assert "賽馬術語" in seen["sys"]
    derive_aligned_output([{"start": 0, "end": 1, "text": "佢好開心"}], "yue", "zh", "trad", capture, style="generic")
    assert "賽馬術語" not in seen["sys"]
