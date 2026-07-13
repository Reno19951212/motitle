# backend/tests/test_normalize_hook.py
"""derive_aligned_output 掛 normalize_stage：單位/騎師落 zh 軌 + changes 保留。"""
import output_lang_aligned as ola


def test_derive_applies_normalize_racing(monkeypatch):
    import translation.crosslang_mt as cmt
    # MT 回一個含公尺+Luke 嘅譯文
    monkeypatch.setattr(cmt, "translate_segments",
                        lambda base, cl, ol, llm, **k: [{"start": 0, "end": 1,
                                                         "text": "Luke 跑二千公尺"}])
    base = [{"start": 0, "end": 1, "text": "Luke ran 2000m"}]
    out = ola.derive_aligned_output(base, "en", "zh", "trad", lambda s, u: "",
                                    style="racing", glossaries=None, glossary_llm=False)
    assert "霍宏聲" in out[0]["text"] and "二千米" in out[0]["text"]
    gc = out[0].get("glossary_changes") or []
    tags = {c.get("glossary") for c in gc}
    assert "單位正規化" in tags and "騎師正名" in tags
    assert all(c.get("lang") == "zh" for c in gc)   # caller 蓋 lang
