"""Shared subtitle-text resolver — picks EN / ZH / bilingual line(s) for any
subtitle output (ASS burn-in, SRT, VTT, TXT, live preview)."""
from __future__ import annotations

import re
from typing import List, Optional

VALID_SUBTITLE_SOURCES = {"auto", "en", "zh", "bilingual", "first", "second"}
VALID_BILINGUAL_ORDERS = {"en_top", "zh_top"}

# Human-readable labels for output_lang language codes.
OUTPUT_LANG_LABELS = {
    "yue": "口語廣東話",
    "zh": "中文書面語",
    "cmn": "普通話",
    "en": "英文",
    "ja": "日文",
}

# Frozenset of all supported output language codes (deduplicated from OUTPUT_LANG_LABELS).
SUPPORTED_OUTPUT_LANGS: frozenset = frozenset(OUTPUT_LANG_LABELS)

# QA flag prefixes left over from legacy registry data; never burn into output.
# Matches [LONG], [long], [REVIEW], [review], [NEEDS REVIEW] — possibly stacked.
_QA_PREFIX_RE = re.compile(
    r"^\s*(?:\[(?:NEEDS\s+REVIEW|long|review|LONG|REVIEW)\]\s*)+"
)


def strip_qa_prefixes(text: str) -> str:
    """Remove leading [long]/[review]/[NEEDS REVIEW] markers from legacy zh_text values."""
    if not text:
        return ""
    return _QA_PREFIX_RE.sub("", text).strip()


def _resolve_role_text(seg: dict, field: Optional[str], legacy_fallbacks: List[str]) -> str:
    """Return text from an explicit field or walk legacy fallback fields."""
    if field:
        return (seg.get(field) or "").strip()
    for f in legacy_fallbacks:
        v = seg.get(f)
        if v:
            return v.strip()
    return ""


def resolve_segment_text(
    seg: dict,
    mode: str = "auto",
    order: str = "en_top",
    line_break: str = "\\N",
    *,
    first_field: Optional[str] = None,
    second_field: Optional[str] = None,
) -> str:
    """Return the text string a renderer/exporter should emit for this segment.

    Args:
        seg: dict with `text` or `en_text`, and optional `zh_text`.
        mode: "auto" | "en" | "zh" | "bilingual" | "first" | "second"
        order: bilingual stacking — "en_top" or "zh_top"
        line_break: ASS callers pass "\\N"; SRT/VTT/TXT/preview pass "\n".
        first_field: explicit dict key for the "first" role (default: text/en_text).
        second_field: explicit dict key for the "second" role (default: zh_text).

    Behavior (legacy modes en/zh/bilingual/auto are preserved exactly):
        - en / first      → first-role text; falls back to second if empty
        - zh / second     → second-role text; falls back to first if empty
        - bilingual       → both stacked; if one side empty, single line
        - auto (default)  → second (ZH) if non-empty, else first (EN)
    """
    first = _resolve_role_text(seg, first_field, ["text", "en_text"])
    second = strip_qa_prefixes(_resolve_role_text(seg, second_field, ["zh_text"]))

    m = (mode or "auto").lower()
    # Map legacy names to role names
    if m == "en":
        m = "first"
    elif m == "zh":
        m = "second"

    if m == "first":
        return first or second
    if m == "second":
        return second or first
    if m == "bilingual":
        # Preserve exact legacy bilingual behavior: empty side → return other side
        if not first:
            return second
        if not second:
            return first
        a, b = (first, second) if order == "en_top" else (second, first)
        return f"{a}{line_break}{b}"
    # default + "auto": prefer second (translation) when present, else first
    return second or first


def resolve_subtitle_source(
    file_entry: dict,
    profile: Optional[dict],
    override: Optional[str] = None,
) -> str:
    """Pick the active subtitle_source via 3-layer fallback:
    render-modal override → file → profile → "auto".
    """
    if override and override in VALID_SUBTITLE_SOURCES:
        return override
    file_val = (file_entry or {}).get("subtitle_source")
    if file_val in VALID_SUBTITLE_SOURCES:
        return file_val
    prof_val = ((profile or {}).get("font") or {}).get("subtitle_source")
    if prof_val in VALID_SUBTITLE_SOURCES:
        return prof_val
    return "auto"


def resolve_bilingual_order(
    file_entry: dict,
    profile: Optional[dict],
    override: Optional[str] = None,
) -> str:
    """Pick the active bilingual_order — same fallback chain as subtitle_source.
    Default "en_top" matches Western-broadcast convention."""
    if override and override in VALID_BILINGUAL_ORDERS:
        return override
    file_val = (file_entry or {}).get("bilingual_order")
    if file_val in VALID_BILINGUAL_ORDERS:
        return file_val
    prof_val = ((profile or {}).get("font") or {}).get("bilingual_order")
    if prof_val in VALID_BILINGUAL_ORDERS:
        return prof_val
    return "en_top"


def resolve_language_descriptor(
    file_entry: Optional[dict],
    active_cfg: Optional[dict] = None,
) -> List[dict]:
    """Return an ordered list of [{role, lang, label}] for a file's language tracks.

    Profile pipeline: first=ASR source language (原文), second=zh (譯文).
    V6 pipeline: first=source_lang from translations (原文); second added only
                 when a second distinct by_lang key exists in translations.
    """
    entry = file_entry or {}
    kind = entry.get("active_kind", "profile")
    translations = entry.get("translations") or []

    if kind == "output_lang":
        outs = entry.get("output_languages") or []
        roles = ["first", "second"]
        return [
            {"role": roles[i], "lang": lang, "label": OUTPUT_LANG_LABELS.get(lang, lang)}
            for i, lang in enumerate(outs[:2])
        ]

    if kind == "pipeline_v6":
        # Derive source_lang: prefer translations[0].source_lang (processed file),
        # then active_cfg.source_lang (fresh file from pipeline config), then "zh".
        src = (translations[0].get("source_lang") if translations else None)
        if not src and active_cfg:
            src = active_cfg.get("source_lang")
        src = src or "zh"

        langs: List[dict] = [{"role": "first", "lang": src, "label": "原文"}]

        # Collect second lang from by_lang keys in existing translations.
        extra: List[str] = []
        for row in translations:
            for k in (row.get("by_lang") or {}):
                if k != src and k not in extra:
                    extra.append(k)

        if extra:
            langs.append({"role": "second", "lang": extra[0], "label": "譯文"})
        elif not extra:
            # No real by_lang second lang yet — surface the pre-selection if any.
            pre = entry.get("second_lang_preselect")
            if pre and pre != src:
                langs.append({"role": "second", "lang": pre, "label": "譯文"})

        return langs

    # Profile (and any other kind) — first=ASR source, second=zh
    src = "en"
    if active_cfg and active_cfg.get("asr"):
        src = active_cfg["asr"].get("language", "en")
    return [
        {"role": "first", "lang": src, "label": "原文"},
        {"role": "second", "lang": "zh", "label": "譯文"},
    ]
