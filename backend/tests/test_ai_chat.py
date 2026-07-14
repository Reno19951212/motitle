"""ai_chat pure module tests（Task 5）— parse_ops leniency/rejection 矩陣 +
apply_lang_role_override 機械 keyword override.

Run: cd backend && ./venv/bin/python -m pytest tests/test_ai_chat.py -q
（pure module — 唔使 Flask/env）

Adapted from the task-5 brief against the FINAL validated schema
（docs/superpowers/specs/2026-07-14-ai-chat-intent-validation-tracker.md,
probe_intent.py post-Round-5）:
  - replace_term.langs is ALWAYS normalized to "all" regardless of model
    output（validation Round 5 schema simplification — UI checkbox narrows
    scope, langs field is decorative）.
  - when parse_ops sees at least one real (non-"none") op, any sibling
    "none" ops are stripped as contradictory noise — only "none" ops
    survive together when there is no real op alongside them.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import ai_chat


GOOD = json.dumps({"reply": "好，改晒佢", "ops": [
    {"op": "replace_term", "from": "晨操", "to": "早操", "langs": "all"}]},
    ensure_ascii=False)


def test_parse_good_replace_term():
    out = ai_chat.parse_ops(GOOD)
    assert out == {"reply": "好，改晒佢", "ops": [
        {"op": "replace_term", "from": "晨操", "to": "早操", "langs": "all"}]}


def test_parse_strips_think_and_fences():
    raw = "<think>諗緊…</think>\n```json\n" + GOOD + "\n```"
    assert ai_chat.parse_ops(raw) is not None


def test_parse_rewrite_cue():
    raw = json.dumps({"reply": "改第3段", "ops": [
        {"op": "rewrite_cue", "seg_no": 3, "lang_role": "first",
         "instruction": "馬名改做金鎗六十"}]}, ensure_ascii=False)
    out = ai_chat.parse_ops(raw)
    assert [o["op"] for o in out["ops"]] == ["rewrite_cue"]
    assert out["ops"][0]["instruction"] == "馬名改做金鎗六十"


def test_parse_none_kinds_survive_without_real_ops():
    raw = json.dumps({"reply": "?", "ops": [
        {"op": "none", "kind": "clarify", "question": "改邊個語言軌？"},
        {"op": "none", "kind": "unsupported"}]}, ensure_ascii=False)
    out = ai_chat.parse_ops(raw)
    assert [o["op"] for o in out["ops"]] == ["none", "none"]


def test_parse_real_op_strips_sibling_none_ops():
    # 模型間中會喺真操作旁邊 append 一個空 clarify/客套 none op — 呢啲係矛盾雜訊，
    # parse_ops 要剔走，只留低真操作。
    raw = json.dumps({"reply": "改第3段", "ops": [
        {"op": "rewrite_cue", "seg_no": 3, "lang_role": "first",
         "instruction": "馬名改做金鎗六十"},
        {"op": "none", "kind": "clarify", "question": "改邊個語言軌？"}]},
        ensure_ascii=False)
    out = ai_chat.parse_ops(raw)
    assert [o["op"] for o in out["ops"]] == ["rewrite_cue"]


def test_parse_rejects_degenerate_and_bad_shapes():
    # 每個都要 None：chat refusal 純文字 / 空 / 非 str / 未知 op / >MAX_OPS /
    # bool seg_no / from==to / 超長 term / ops 非 list
    bad = [
        "我係一個 AI 助手，好高興認識你！",
        "", None, 123,
        json.dumps({"reply": "x", "ops": [{"op": "delete_all"}]}),
        json.dumps({"reply": "x", "ops": [{"op": "none", "kind": "unsupported"}] * 6}),
        json.dumps({"reply": "x", "ops": [{"op": "rewrite_cue", "seg_no": True,
                                           "lang_role": "first", "instruction": "i"}]}),
        json.dumps({"reply": "x", "ops": [{"op": "replace_term", "from": "a", "to": "a",
                                           "langs": "all"}]}),
        json.dumps({"reply": "x", "ops": [{"op": "replace_term", "from": "a" * 81,
                                           "to": "b", "langs": "all"}]}),
        json.dumps({"reply": "x", "ops": "not-a-list"}),
    ]
    for raw in bad:
        assert ai_chat.parse_ops(raw) is None, raw


def test_parse_allows_empty_to_delete_and_normalizes_langs_to_all():
    # langs field 係 decorative（validation Round 5）— 模型俾乜值（list/string/漏咗）
    # parse_ops 都一律正規化做 "all"；軌範圍由 UI checkbox 收窄。
    raw = json.dumps({"reply": "刪走", "ops": [
        {"op": "replace_term", "from": "呃", "to": "", "langs": ["zh"]}]}, ensure_ascii=False)
    assert ai_chat.parse_ops(raw)["ops"][0]["langs"] == "all"

    raw2 = json.dumps({"reply": "x", "ops": [
        {"op": "replace_term", "from": "a", "to": "b", "langs": "zh"}]}, ensure_ascii=False)
    assert ai_chat.parse_ops(raw2)["ops"][0]["langs"] == "all"


def test_prompts_bounded_and_no_transcript_fields():
    lang_lines = ai_chat.lang_lines_of([
        {"role": "first", "lang": "zh", "label": "中文（書面語）"},
        {"role": "second", "lang": "en", "label": "英文"}])
    sys_p = ai_chat.build_parse_system_prompt(lang_lines)
    user_p = ai_chat.build_parse_user_prompt(
        "把所有A改成B", {"cue_count": 42, "cursor_seg_no": 7}, "上一輪：…")
    # 2026-07-14 final schema system prompt (12 few-shot examples) ~3.9k chars —
    # bound loosely to catch runaway prompt bloat, not the brief's stale <2000.
    assert len(sys_p) < 4500 and len(user_p) < 700
    assert "transcript" not in user_p and "字幕全文" not in user_p


def test_user_prompt_clamps_last_turn():
    p = ai_chat.build_parse_user_prompt("x", {"cue_count": 1}, "長" * 999)
    assert len(json.loads(p)["上一輪"]) <= 300


# ---------- apply_lang_role_override ----------

def test_apply_lang_role_override_keyword_match():
    ops = [{"op": "rewrite_cue", "seg_no": 3, "lang_role": "first", "instruction": "x"}]
    languages = [
        {"role": "first", "lang": "zh", "label": "中文"},
        {"role": "second", "lang": "en", "label": "英文"},
    ]
    out = ai_chat.apply_lang_role_override(ops, "改埋英文嗰句", languages)
    assert out[0]["lang_role"] == "second"
    # immutability: input list/dict untouched, output is new objects
    assert ops[0]["lang_role"] == "first"
    assert out is not ops
    assert out[0] is not ops[0]


def test_apply_lang_role_override_explicit_role_keyword_no_languages_needed():
    ops = [{"op": "rewrite_cue", "seg_no": 1, "lang_role": "first", "instruction": "x"}]
    out = ai_chat.apply_lang_role_override(ops, "第二語言嗰句要改", [])
    assert out[0]["lang_role"] == "second"


def test_apply_lang_role_override_noop_on_ambiguity():
    ops = [{"op": "rewrite_cue", "seg_no": 1, "lang_role": "first", "instruction": "x"}]
    languages = [
        {"role": "first", "lang": "en", "label": "英文"},
        {"role": "second", "lang": "ja", "label": "日文"},
    ]
    out = ai_chat.apply_lang_role_override(ops, "英文同日文都要改", languages)
    assert out == ops
    assert out is ops  # no-op returns the same object, no copy made


def test_apply_lang_role_override_noop_on_absence():
    ops = [{"op": "rewrite_cue", "seg_no": 1, "lang_role": "first", "instruction": "x"}]
    languages = [{"role": "first", "lang": "zh", "label": "中文"}]
    out = ai_chat.apply_lang_role_override(ops, "改一改呢句", languages)
    assert out is ops


def test_apply_lang_role_override_leaves_non_rewrite_cue_ops_untouched():
    ops = [{"op": "none", "kind": "unsupported"}]
    out = ai_chat.apply_lang_role_override(ops, "第一語言", [])
    assert out[0] == {"op": "none", "kind": "unsupported"}
    assert out[0] is ops[0]  # non-rewrite_cue ops pass through by reference
