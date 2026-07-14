"""ai_chat_ops tests（Task 6）— expand 確定性/冪等/上限/approved 推導.

Run: cd backend && ./venv/bin/python -m pytest tests/test_ai_chat_ops.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import ai_chat_ops as ops_mod


def _rows():
    def row(i, zh, en, status="pending", zh_status=None):
        return {"idx": i, "start": float(i), "end": float(i) + 2.0, "status": status,
                "by_lang": {"zh": {"text": zh, "status": zh_status or status, "flags": []},
                            "en": {"text": en, "status": "pending", "flags": []}},
                "zh_text": zh, "en_text": en, "glossary_changes": []}
    return [
        row(0, "今朝有晨操。", "Track work this morning."),
        row(1, "晨操之後晨操。", "After track work, more Track Work.", status="approved"),
        row(2, "冇相關字詞。", "Nothing here."),
    ]


OUTS = ["zh", "en"]


def test_validate_ops_lang_subset_and_seg_bounds():
    assert ops_mod.validate_ops(
        [{"op": "replace_term", "from": "a", "to": "b", "langs": ["ja"]}], OUTS, 3
    ) is not None  # bogus lang → 中文錯誤（防開新 by_lang 軌）
    assert ops_mod.validate_ops(
        [{"op": "rewrite_cue", "seg_no": 4, "lang_role": "first", "instruction": "i"}], OUTS, 3
    ) is not None  # seg_no 出界（1-based，cue_count=3）
    assert ops_mod.validate_ops(
        [{"op": "rewrite_cue", "seg_no": 3, "lang_role": "second", "instruction": "i"}],
        ["zh"], 3
    ) is not None  # second 但檔案冇第二語言
    assert ops_mod.validate_ops(
        [{"op": "replace_term", "from": "a", "to": "b", "langs": "all"},
         {"op": "none", "kind": "unsupported"}], OUTS, 3
    ) is None


def test_expand_replace_term_deterministic_and_skips_nonmatch():
    rows = _rows()
    out = ops_mod.expand_ops(rows, OUTS,
        [{"op": "replace_term", "from": "晨操", "to": "早操", "langs": ["zh"]}])
    assert [i["idx"] for i in out["items"]] == [0, 1]
    it = out["items"][1]
    assert it["after"] == "早操之後早操。" and it["expected_text"] == "晨操之後晨操。"
    assert it["approved"] is True and out["totals"] == {"matched": 2, "approved": 1}
    assert it["start"] == 1.0 and it["end"] == 3.0
    # immutable：原 rows 冇被改
    assert rows[0]["zh_text"] == "今朝有晨操。"


def test_expand_langs_all_and_ci_latin():
    out = ops_mod.expand_ops(_rows(), OUTS,
        [{"op": "replace_term", "from": "track work", "to": "morning gallops", "langs": "all"}])
    ens = [i for i in out["items"] if i["lang"] == "en"]
    assert [i["idx"] for i in ens] == [0, 1]
    assert ens[1]["after"] == "After morning gallops, more morning gallops."


def test_expand_idempotent_skip_and_cap():
    rows = _rows()
    # after==before（to 已經喺晒度）→ skip
    out = ops_mod.expand_ops(rows, OUTS,
        [{"op": "replace_term", "from": "晨操", "to": "晨操。", "langs": ["zh"]}])
    assert all(i["after"] != i["before"] for i in out["items"])
    # cap：整 250 行全命中 → 200 + truncated
    many = []
    for i in range(250):
        many.append({"idx": i, "start": float(i), "end": float(i) + 1, "status": "pending",
                     "by_lang": {"zh": {"text": "晨操", "status": "pending", "flags": []}},
                     "zh_text": "晨操", "glossary_changes": []})
    out2 = ops_mod.expand_ops(many, ["zh"],
        [{"op": "replace_term", "from": "晨操", "to": "早操", "langs": ["zh"]}])
    assert len(out2["items"]) == ops_mod.MAX_ITEMS and out2["truncated"] is True


def test_expand_approved_from_row_status_approve_all_asymmetry():
    rows = _rows()
    # approve-all 只掀 row.status 唔 mirror by_lang — approved 必須照 True
    rows[2] = {**rows[2], "status": "approved",
               "by_lang": {"zh": {"text": "冇相關字詞。", "status": "pending", "flags": []},
                           "en": {"text": "Nothing here.", "status": "pending", "flags": []}},
               }
    out = ops_mod.expand_ops(rows, OUTS,
        [{"op": "replace_term", "from": "字詞", "to": "詞語", "langs": ["zh"]}])
    assert out["items"][0]["approved"] is True


def test_expand_rewrite_cue_one_item():
    out = ops_mod.expand_ops(_rows(), OUTS,
        [{"op": "rewrite_cue", "seg_no": 2, "lang_role": "first", "instruction": "改書面"}])
    assert out["items"] == [{
        "idx": 1, "lang": "zh", "lang_role": "first", "kind": "ai_rewrite",
        "instruction": "改書面", "before": "晨操之後晨操。",
        "expected_text": "晨操之後晨操。", "start": 1.0, "end": 3.0, "approved": True}]


def test_ci_fold_length_guard():
    # 'İ'.lower() 變長 → 回退精確匹配，唔會索引漂移寫壞文字
    assert ops_mod.replace_all_ci("İstanbul x", "istanbul", "Y") == "İstanbul x"
    assert ops_mod.count_ci("ABC abc", "abc") == 2
