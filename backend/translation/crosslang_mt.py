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

# zh/cmn (written-Chinese) target: forbid spoken-Cantonese leakage + domain injection
_ZH_WRITTEN_RULES = (
    "輸出必須是現代正式繁體中文書面語，禁用粵語口語字（係→是、嘅→的、喺→在、咗→了、"
    "唔→不、冇→沒有、嗰→那、呢→這、我哋→我們、佢→他/牠、而家→現在、睇→看、嚟→來、畀→給；"
    "句末語氣助詞啦/㗎/囉/喎/呀/咩/喇一律刪除）。不得把通用詞按主觀場景改成原文沒有的特定領域術語。"
)

# v3: written-Chinese-authored base prompt (was Cantonese-authored — the leak root cause)
_MT_SYS = ("你是專業廣播字幕翻譯員，負責將用戶提供的單句{src}字幕翻譯成{tgt}。"
           "規則：貼近廣播口播、自然流暢；不得加入原文沒有的資訊或領域術語；保留專有名詞；"
           "輸出一行，只輸出譯文本身，不加任何解釋或標籤。{extra}")

_LEAK_RE = re.compile(r"粵語口語廣播字幕|請輸入.{0,12}(轉換|翻譯)|^系統提示|^system prompt", re.IGNORECASE)

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_LABEL_RE = re.compile(r"^(譯文|翻譯|Translation|出力)[:：]\s*")


def build_mt_system_prompt(source_language: str, output_lang: str) -> str:
    extra = _ZH_WRITTEN_RULES if output_lang in ("zh", "cmn") else ""
    return _MT_SYS.format(src=_SRC_NAME.get(source_language, source_language),
                          tgt=_MT_TARGET_NAME.get(output_lang, output_lang),
                          extra=extra)


def _clean(raw: str) -> str:
    out = _THINK_RE.sub("", raw or "").strip()
    out = _LABEL_RE.sub("", out).strip()
    return out.splitlines()[0].strip() if out else ""


def translate_segments(content_segments: List[dict], source_language: str,
                       output_lang: str, llm_call: Callable[[str, str], str]) -> List[dict]:
    """1:1 MT of content segments -> output language. New list; inputs untouched.

    Guard: an empty or prompt-leaked LLM reply falls back to the SOURCE text so a
    pathological cue never ships (never empty, never the prompt template)."""
    sysp = build_mt_system_prompt(source_language, output_lang)
    out: List[dict] = []
    for s in content_segments:
        txt = (s.get("text") or "").strip()
        tr = _clean(llm_call(sysp, txt)) if txt else ""
        if txt and (not tr or _LEAK_RE.search(tr)):
            tr = txt
        out.append({"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": tr})
    return out
