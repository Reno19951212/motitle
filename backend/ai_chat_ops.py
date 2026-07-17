"""AI 助手 — ops 驗證 + 機械展開（零 LLM、immutable、no I/O）.

Spec: docs/superpowers/specs/2026-07-14-ai-chat-window-design.md §3.1
matching 語義 = find-replace.js parity：literal case-insensitive，
case fold 變長（如 İ）→ 回退精確匹配（索引漂移防護）。
"""
from typing import Dict, List, Optional

MAX_ITEMS = 200


def _ci_pair(raw: str, q: str):
    lraw, lq = raw.lower(), q.lower()
    if len(lraw) != len(raw) or len(lq) != len(q):
        return raw, q
    return lraw, lq


def count_ci(raw: str, q: str) -> int:
    if not q:
        return 0
    lraw, lq = _ci_pair(raw, q)
    n, at = 0, lraw.find(lq)
    while at != -1:
        n += 1
        at = lraw.find(lq, at + len(lq))
    return n


def replace_all_ci(raw: str, q: str, rep: str) -> str:
    if not q:
        return raw
    lraw, lq = _ci_pair(raw, q)
    out, last, at = [], 0, lraw.find(lq)
    while at != -1:
        out.append(raw[last:at])
        out.append(rep)
        last = at + len(q)
        at = lraw.find(lq, last)
    out.append(raw[last:])
    return "".join(out)


def _op_langs(op: Dict, output_languages: List[str]) -> List[str]:
    langs = op.get("langs", "all")
    return list(output_languages) if langs == "all" else list(langs)


def validate_ops(ops: List[Dict], output_languages: List[str],
                 cue_count: int) -> Optional[str]:
    """None=合格；否則中文錯誤（route 回 400/422 用）。parse_ops 已保證 shape，
    呢度做 registry-aware 邊界：lang ⊆ output_languages、seg_no 1..cue_count、
    second 要真係有第二語言。"""
    for op in ops:
        kind = op.get("op")
        if kind == "replace_term":
            for lang in _op_langs(op, output_languages):
                if lang not in output_languages:
                    return "langs 必須係檔案輸出語言之一"
        elif kind == "rewrite_cue":
            seg_no = op.get("seg_no")
            if isinstance(seg_no, bool) or not isinstance(seg_no, int) \
                    or not (1 <= seg_no <= cue_count):
                return "seg_no 出界"
            if op.get("lang_role") == "second" and len(output_languages) < 2:
                return "呢個檔案冇第二語言"
        elif kind != "none":
            return "未知操作種類"
    return None


def _row_text(row: Dict, lang: str) -> str:
    bl = (row.get("by_lang") or {}).get(lang) or {}
    return bl.get("text") or row.get(f"{lang}_text") or ""


def _row_approved(row: Dict, lang: str) -> bool:
    # approve-all 只掀 row.status 唔 mirror by_lang → row.status 為準，OR by_lang
    if row.get("status") == "approved":
        return True
    bl = (row.get("by_lang") or {}).get(lang) or {}
    return bl.get("status") == "approved"


def _expand_replace_term(translations: List[Dict], output_languages: List[str],
                          replace_ops: List[Dict], items: List[Dict]) -> bool:
    """多個 replace_term op 命中同一 (idx, lang) 時 COMPOSE 成一個 item（非逐 op
    各出一個 — 舊行為會令 apply 階段第二個 item 嘅 expected_text 仲係原文，
    第一個 item 寫入之後即刻衝突失敗，靜默丟失第二個修改，UI 仲顯示 ✓）。
    做法：per (idx, lang) 由原文起維護一條 working text，逐 op（按傳入次序）
    sequential apply；最終 working != 原文先出一個 item，expected_text = 原文。
    次序：row idx 由細到大 → lang 跟 output_languages 次序（唔跟邊個 op 先掂到）。
    回傳 truncated（是否曾撞 MAX_ITEMS）。"""
    op_specs = [(op["from"], op["to"], set(_op_langs(op, output_languages)))
                for op in replace_ops]
    touched_langs = set()
    for _, _, langs in op_specs:
        touched_langs |= langs
    touched_langs_order = [lang for lang in output_languages if lang in touched_langs]
    truncated = False
    for i, row in enumerate(translations):
        for lang in touched_langs_order:
            original = _row_text(row, lang)
            if not original:
                continue
            working = original
            for frm, to, langs in op_specs:
                if lang not in langs:
                    continue
                working = replace_all_ci(working, frm, to)
            if working == original:
                continue                              # 冪等 skip（合成後零變化）
            if len(items) >= MAX_ITEMS:
                truncated = True
                break
            items.append({
                "idx": i, "lang": lang, "kind": "mechanical",
                "before": original, "after": working, "expected_text": original,
                "start": row.get("start"), "end": row.get("end"),
                "approved": _row_approved(row, lang),
            })
        if truncated:
            break
    return truncated


def expand_ops(translations: List[Dict], output_languages: List[str],
               ops: List[Dict]) -> Dict:
    """確定性展開 ops → proposal items（零 LLM、只讀、回新 dict）。"""
    items: List[Dict] = []
    truncated = False

    replace_ops = [op for op in ops if op.get("op") == "replace_term"]
    if replace_ops:
        truncated = _expand_replace_term(translations, output_languages,
                                          replace_ops, items)

    if not truncated:
        for op in ops:
            if op.get("op") != "rewrite_cue":
                continue
            idx = op["seg_no"] - 1                    # 1-based 段號 → row idx
            role = op["lang_role"]
            lang = output_languages[0] if role == "first" else output_languages[1]
            row = translations[idx]
            text = _row_text(row, lang)
            if len(items) < MAX_ITEMS:
                items.append({
                    "idx": idx, "lang": lang, "lang_role": role, "kind": "ai_rewrite",
                    "instruction": op["instruction"], "before": text,
                    "expected_text": text, "start": row.get("start"),
                    "end": row.get("end"), "approved": _row_approved(row, lang),
                })
            else:
                truncated = True
                break

    return {"items": items, "truncated": truncated,
            "totals": {"matched": len(items),
                       "approved": sum(1 for i in items if i["approved"])}}
