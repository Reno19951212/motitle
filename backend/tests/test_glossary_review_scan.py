"""scan_track() — 校對頁詞彙掃描 pure function 測試。"""
import pytest
from output_lang_glossary import scan_track


def _gl(entries, name="賽馬", gid="g-1", src="en", tgt="zh"):
    return {"id": gid, "name": name, "source_lang": src, "target_lang": tgt,
            "entries": entries}

E1 = {"id": "e-1", "source": "Happy Valley", "target": "跑馬地", "target_aliases": ["快活谷"]}
# NOTE: canonical/alias must be >2 chars to survive the pipeline target-side guard
# (`_filter_target_side` skips entries whose canonical ≤2 chars — see test_guards_respected).
# The plan's original fixture used 潘頓/帕頓 (both 2 chars) which the guard rejects, so the
# alias could never become a 'fix'. Using a >2-char name keeps the test's intent (per-row
# approved-flag passthrough across two fix rows) while respecting the shared matching guard.
E2 = {"id": "e-2", "source": "Zac Purton", "target": "潘頓師傅", "target_aliases": ["帕頓師傅"]}


def test_target_side_alias_hit_is_fix():
    trk = scan_track(texts=["快活谷今晚有賽事。"], src_texts=None,
                     glossaries=[_gl([E1])], output_lang="yue",
                     content_lang="yue", derive_mode="pass", approved=[False])
    assert trk["lang"] == "yue" and trk["side"] == "target"
    items = trk["items"]
    assert len(items) == 1 and items[0]["kind"] == "fix"
    assert items[0]["alias"] == "快活谷" and items[0]["canonical"] == "跑馬地"
    assert items[0]["idx"] == 0 and items[0]["entry_id"] == "e-1"
    assert items[0]["row_text"] == "快活谷今晚有賽事。"
    assert items[0]["approved"] is False


def test_target_side_verbatim_is_ok():
    trk = scan_track(texts=["跑馬地今晚有賽事。"], src_texts=None,
                     glossaries=[_gl([E1])], output_lang="yue",
                     content_lang="yue", derive_mode="pass", approved=[False])
    assert [i["kind"] for i in trk["items"]] == ["ok"]


def test_source_side_fix_and_ok():
    g = _gl([E1])
    trk = scan_track(texts=["The races at Wong Nai Chung were thrilling."],
                     src_texts=["跑馬地今晚嘅賽事好刺激。"],   # content 命中 target 索引?
                     glossaries=[g], output_lang="en",
                     content_lang="en", derive_mode="mt", approved=[False])
    # mt gate: glossary.source_lang(en) == content_lang(en) → 用 source term 喺 src_texts 搵
    # 呢度 src_texts 係中文 — source term "Happy Valley" 唔喺入面 → 冇 item
    assert trk["items"] == []

    trk2 = scan_track(texts=["The races at Wong Nai Chung were thrilling."],
                      src_texts=["Races at Happy Valley were thrilling."],
                      glossaries=[g], output_lang="zh",
                      content_lang="en", derive_mode="mt", approved=[False])
    # source 命中 + 譯文(text)冇 canonical → fix
    assert len(trk2["items"]) == 1 and trk2["items"][0]["kind"] == "fix"
    assert trk2["items"][0]["alias"] == "Happy Valley"

    trk3 = scan_track(texts=["跑馬地賽事好刺激。"],
                      src_texts=["Races at Happy Valley were thrilling."],
                      glossaries=[g], output_lang="zh",
                      content_lang="en", derive_mode="mt", approved=[False])
    assert [i["kind"] for i in trk3["items"]] == ["ok"]


def test_approved_flag_passthrough_and_multi_rows():
    trk = scan_track(texts=["快活谷賽事。", "帕頓師傅出賽。"], src_texts=None,
                     glossaries=[_gl([E1, E2])], output_lang="yue",
                     content_lang="yue", derive_mode="pass",
                     approved=[True, False])
    fixes = [(i["idx"], i["approved"]) for i in trk["items"] if i["kind"] == "fix"]
    assert fixes == [(0, True), (1, False)]


def test_inapplicable_glossary_listed():
    # EN→ZH 表對 mt 軌（content=yue）gate 唔過 → not_applicable
    trk = scan_track(texts=["Hello."], src_texts=["你好。"],
                     glossaries=[_gl([E1])], output_lang="en",
                     content_lang="yue", derive_mode="mt", approved=[False])
    assert trk["items"] == []
    assert trk["applicable_glossaries"] == []
    assert trk["inapplicable_glossaries"] == ["賽馬"]


def test_guards_respected():
    # target ≤2 字 skip（同 pipeline 一致）
    g = _gl([{"id": "e-3", "source": "club", "target": "馬會", "target_aliases": ["俱樂部"]}])
    trk = scan_track(texts=["俱樂部公佈措施。"], src_texts=None, glossaries=[g],
                     output_lang="yue", content_lang="yue", derive_mode="pass",
                     approved=[False])
    assert trk["items"] == []   # target「馬會」≤2 字 → guard skip
