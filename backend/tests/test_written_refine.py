"""書面語 refiner W6 機制 — port 自 2026-06-13 written-quality 研究 W6 proto。"""
import output_lang_postprocess as olp


GLOSS = [{"name": "賽馬", "entries": [
    {"source": "BEST PAL", "target": "好友心得 (D456)"},
    {"source": "LUCKY", "target": "幸運有您 (E356)"},
]}]


def _segs(*texts):
    return [{"start": float(i), "end": float(i + 1), "text": t} for i, t in enumerate(texts)]


def _capture_llm():
    """回 (llm, calls) — calls 記錄每次 (system, user)。LLM 回 keep JSON 照抄 user 本句。"""
    calls = []

    def llm(system, user):
        calls.append((system, user))
        # 抽【本句】（或者成個 user）做輸出，模擬「乖乖只改本句」
        body = user.split("【本句】")[-1].split("【後文】")[0].strip() if "【本句】" in user else user
        import json as _j
        return _j.dumps({"action": "keep", "text": body})
    return llm, calls


def test_window_user_format():
    llm, calls = _capture_llm()
    olp.formal_refine(_segs("第一句", "第二句", "第三句", "第四句", "第五句"),
                      llm, style="racing", glossaries=GLOSS, context_window=2)
    # 中間段（idx 2）user 要有前文（第一/第二）+ 本句（第三）+ 後文（第四/第五）
    sys2, user2 = calls[2]
    assert "【前文】" in user2 and "【本句】" in user2 and "【後文】" in user2
    assert "第三句" in user2 and "第一句" in user2 and "第五句" in user2


def test_window_boundaries():
    llm, calls = _capture_llm()
    olp.formal_refine(_segs("頭", "二", "尾"), llm, style="racing",
                      glossaries=GLOSS, context_window=2)
    assert "【前文】" not in calls[0][1]          # 第一段冇前文
    assert "【後文】" not in calls[-1][1]         # 最後段冇後文


def test_roster_injected_in_system_not_user():
    llm, calls = _capture_llm()
    olp.formal_refine(_segs("第六位外面位置好友心得"), llm, style="racing",
                      glossaries=GLOSS, context_window=0)
    sysp, user = calls[0]
    assert "好友心得" in sysp and "本句保護詞" in sysp     # 注入喺 SYSTEM
    # 本句命中嘅名先注入；冇出現嘅名唔注入。注意 W5 base prompt 本身用「幸運有您」做
    # 反例（保護詞示範），所以只可以 assert 佢冇出現喺逐句注入嘅 roster block，
    # 唔可以 assert 成個 sysp（會撞到 base prompt 嘅示範文字）。
    roster_block = sysp.split("【本句保護詞")[-1]
    assert "好友心得" in roster_block
    assert "幸運有您" not in roster_block


def test_pos_terms_racing_only():
    llm, calls = _capture_llm()
    olp.formal_refine(_segs("尾三紅衫"), llm, style="racing", glossaries=None, context_window=0)
    assert "尾三" in calls[0][0] and "倒數第三" in calls[0][0]
    llm2, calls2 = _capture_llm()
    olp.formal_refine(_segs("尾三紅衫"), llm2, style="generic", glossaries=None, context_window=0)
    assert "本句保護詞" not in calls2[0][0]               # generic 無位置術語注入


def test_name_diff_flag_recorded():
    # LLM 將馬名改走 → name_dropped flag
    def drop_llm(system, user):
        import json as _j
        return _j.dumps({"action": "keep", "text": "第六位外檔位置獲好評"})  # 好友心得 冇咗
    out = olp.formal_refine(_segs("第六位外面位置好友心得"), drop_llm, style="racing",
                            glossaries=GLOSS, context_window=0)
    assert out[0].get("refine_name_dropped") == ["好友心得"]


def test_name_diff_no_flag_when_kept():
    def keep_llm(system, user):
        import json as _j
        return _j.dumps({"action": "keep", "text": "第六位、外檔位置的是好友心得。"})
    out = olp.formal_refine(_segs("第六位外面位置好友心得"), keep_llm, style="racing",
                            glossaries=GLOSS, context_window=0)
    assert "refine_name_dropped" not in out[0]


def test_context_window_zero_no_window():
    llm, calls = _capture_llm()
    olp.formal_refine(_segs("甲", "乙"), llm, style="racing", glossaries=None, context_window=0)
    assert "【前文】" not in calls[0][1] and "【本句】" not in calls[0][1]   # 純本句


def test_empty_segment_passthrough():
    llm, calls = _capture_llm()
    out = olp.formal_refine(_segs("有字", ""), llm, style="racing", glossaries=None)
    assert out[1]["text"] == ""
    assert len(calls) == 1                              # 空段唔 call LLM


def test_cancel_check_raises():
    class _C(Exception):
        pass

    def boom():
        raise _C()
    import pytest
    with pytest.raises(_C):
        olp.formal_refine(_segs("一句"), lambda s, u: "x", style="racing", cancel_check=boom)


def test_glossary_import_failopen(monkeypatch):
    # phonetic_correction 攞唔到 → 空 name set，唔 crash（仍正常 refine）
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "phonetic_correction":
            raise ImportError("simulated")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    llm, calls = _capture_llm()
    out = olp.formal_refine(_segs("好友心得"), llm, style="racing", glossaries=GLOSS, context_window=0)
    assert len(out) == 1                                # 唔 crash
    assert "本句保護詞" not in calls[0][0]               # 冇 name set → 冇注入


def test_derive_threads_glossaries_into_refine(monkeypatch):
    import output_lang_aligned as ola
    seen = {}

    def fake_refine(segments, llm_call, style="generic", glossaries=None,
                    context_window=2, cancel_check=None):
        seen["glossaries"] = glossaries
        seen["style"] = style
        return [{**s} for s in segments]
    monkeypatch.setattr(ola.olp, "formal_refine", fake_refine)
    base = [{"start": 0.0, "end": 1.0, "text": "尾三紅衫好友心得"}]
    # yue→zh = refine mode
    ola.derive_aligned_output(base, "yue", "zh", "trad", lambda s, u: "x",
                              style="racing", glossaries=GLOSS)
    assert seen["glossaries"] == GLOSS and seen["style"] == "racing"
