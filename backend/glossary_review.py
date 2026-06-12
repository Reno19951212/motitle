"""校對頁逐項詞彙套用（glossary-apply-item）— pure prompt/parse/validate。

No I/O, no Flask, no registry access — the route in app.py owns those.
Spec: docs/superpowers/specs/2026-06-12-proofread-glossary-review-design.md §4
Prompt 改良自舊 GLOSSARY_APPLY_SYSTEM_PROMPT（app.py:3184-3237 嘅「只改一詞」原則）
+ ai-edit 嘅語體保持規則（validation 實證過 register-drift pattern）。
"""
import json
import re
from typing import Optional

MAX_OUTPUT_CHARS = 200

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_TEXT_KEY_RE = re.compile(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"')


def build_apply_system_prompt(lang_label: str, side: str) -> str:
    direction = (
        "字幕入面有一個寫法唔啱嘅詞，你要將佢改成標準寫法"
        if side == "target" else
        "原文入面有一個專有名詞，你要確保字幕用咗佢嘅標準譯名"
    )
    return (
        "你係廣播字幕詞彙審核員。" + direction + "。\n"
        "規則：\n"
        f"1. 你只可以修改同個詞相關嘅嗰幾隻字 — 句子其他部分必須逐字保留。\n"
        f"2. 輸出必須係「{lang_label}」，維持原句嘅書寫系統（繁／簡）同語體"
        "（書面語定口語）— 絕對唔可以改語氣。\n"
        "3. 修改後句子必須包含標準寫法。\n"
        "4. 如果個詞喺句中有屈折變化／前後接字，照語法自然咁接駁。\n"
        '5. 只輸出 JSON：{"text": "修改後字幕"}。冇 markdown、冇解釋、冇思考標籤。'
    )


def build_apply_user_prompt(row_text: str, src_text: str,
                            alias: str, canonical: str) -> str:
    payload = {
        "現有字幕": row_text,
        "要修改嘅詞": alias,
        "標準寫法": canonical,
    }
    if (src_text or "").strip():
        payload["原文參考"] = src_text
    return json.dumps(payload, ensure_ascii=False)


def parse_response(raw) -> Optional[str]:
    """Lenient LLM-output parse → cleaned subtitle text, or None on failure."""
    if not isinstance(raw, str):
        return None
    txt = _THINK_RE.sub("", raw).strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\s*", "", txt)
        txt = re.sub(r"\s*```\s*$", "", txt).strip()
    if txt.startswith("{"):
        try:
            obj = json.loads(txt, strict=False)
            txt = obj.get("text", "")
        except ValueError:
            m = _TEXT_KEY_RE.search(txt)
            if not m:
                return None
            try:
                txt = json.loads('"' + m.group(1) + '"', strict=False)
            except ValueError:
                return None
    if not isinstance(txt, str):
        return None
    txt = " ".join(txt.split())
    if not txt or len(txt) > MAX_OUTPUT_CHARS:
        return None
    return txt


def validate_applied(new_text: str, canonical: str, before_text: str) -> Optional[str]:
    """套用結果驗證。Return None=合格，否則錯誤描述（route 回 422 用）。"""
    if canonical not in new_text:
        return "輸出唔包含標準寫法"
    if new_text == before_text:
        return "輸出同原句一樣（冇修改）"
    # 防大幅重寫：剔除 canonical 之後，新舊句嘅共同字符比例要 >= 40%
    base = before_text.replace(canonical, "")
    kept = sum(1 for ch in base if ch in new_text)
    if base and kept / len(base) < 0.4:
        return "改動超出單一詞範圍（疑似重寫成句）"
    return None
