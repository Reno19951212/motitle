"""Generic parameterised cross-language MT for output_lang (2026-06-02).

Per-segment 1:1 translation (preserves segmentation + start/end). The LLM client
is injected (production: Ollama qwen3.5:35b via OllamaTranslationEngine._call_ollama).
"""
import re
from typing import Callable, Dict, List

_MT_TARGET_NAME: Dict[str, str] = {
    "yue": "香港口語廣東話（用口語字眼如 嘅/係/喺/咗/唔/睇，繁體字）",
    "zh": "現代正式繁體中文書面語",
    "cmn": "標準普通話書面中文",
    "en": "English",
    "ja": "自然書面日本語",
}
_SRC_NAME: Dict[str, str] = {"yue": "粵語/中文", "cmn": "普通話/中文", "en": "English", "ja": "Japanese"}

_MT_SYS = ("你係專業廣播字幕翻譯員。將用戶提供嘅單句{src}字幕，翻譯成{tgt}。"
           "規則：貼近廣播口播、自然流暢；唔好加原文冇嘅資訊；保留專有名詞；"
           "輸出一行、只輸出譯文本身，唔好任何解釋或標籤。")

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_LABEL_RE = re.compile(r"^(譯文|翻譯|Translation|出力)[:：]\s*")


def build_mt_system_prompt(source_language: str, output_lang: str) -> str:
    return _MT_SYS.format(src=_SRC_NAME.get(source_language, source_language),
                          tgt=_MT_TARGET_NAME.get(output_lang, output_lang))


def _clean(raw: str) -> str:
    out = _THINK_RE.sub("", raw or "").strip()
    out = _LABEL_RE.sub("", out).strip()
    return out.splitlines()[0].strip() if out else ""


def translate_segments(content_segments: List[dict], source_language: str,
                       output_lang: str, llm_call: Callable[[str, str], str]) -> List[dict]:
    """1:1 MT of content segments -> output language. New list; inputs untouched."""
    sysp = build_mt_system_prompt(source_language, output_lang)
    out: List[dict] = []
    for s in content_segments:
        txt = (s.get("text") or "").strip()
        tr = _clean(llm_call(sysp, txt)) if txt else ""
        out.append({"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": tr})
    return out
