"""AI 輔助修改（proofread per-segment AI edit）— pure prompt/parse logic.

No I/O, no Flask, no registry access — the route in app.py owns those.
Spec: docs/superpowers/specs/2026-06-10-proofread-ai-edit-design.md
"""
import json
import re
from typing import Optional

MAX_INSTRUCTION_CHARS = 500
MAX_OUTPUT_CHARS = 200

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_TEXT_KEY_RE = re.compile(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"')


def build_system_prompt(target_label: str) -> str:
    return (
        "你係廣播字幕編輯助手。用戶會俾你一段字幕同一個修改指令，你按指令修改字幕。\n"
        "規則：\n"
        f"1. 你輸出嘅字幕必須係「{target_label}」呢種語言 — 無論指令係乜（包括翻譯指令），"
        "都絕對唔可以輸出其他語言。指令要求翻譯或者參考另一語言時，意思係："
        f"根據參考內容嘅意思，用「{target_label}」重新寫呢段字幕。\n"
        "2. 中文輸出要維持同原字幕一致嘅書寫系統（繁／簡）同語體（書面語定口語），"
        "除非指令明確要求改語氣。\n"
        "3. 保留專有名詞、人名、地名、數字、英文原樣，除非指令明確要求修改。\n"
        "4. 字幕要簡潔自然、適合廣播畫面閱讀；唔好加入原文冇嘅資訊。\n"
        '5. 只輸出 JSON，格式：{"text": "修改後字幕"}。唔好有 markdown、唔好有解釋、唔好有思考標籤。'
    )


def build_user_prompt(target_label: str, target_text: str,
                      other_label: str, other_text: str, instruction: str) -> str:
    payload = {
        "目標欄": target_label,
        "現有字幕": target_text,
        "用戶指令": instruction,
    }
    if (other_text or "").strip():
        payload["另一語言參考"] = {other_label or "另一語言": other_text}
    return json.dumps(payload, ensure_ascii=False)


def parse_response(raw) -> Optional[str]:
    """Lenient LLM-output parse → cleaned subtitle text, or None on any failure."""
    if not isinstance(raw, str):
        return None
    txt = _THINK_RE.sub("", raw).strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\s*", "", txt)
        txt = re.sub(r"\s*```\s*$", "", txt).strip()
    if txt.startswith("{"):
        try:
            # strict=False — LLMs emit raw newlines inside JSON strings
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
    txt = " ".join(txt.split())  # collapse 換行/連續空白
    if not txt or len(txt) > MAX_OUTPUT_CHARS:
        return None
    return txt
