"""Shared subtitle-text resolver — picks EN / ZH / bilingual line(s) for any
subtitle output (ASS burn-in, SRT, VTT, TXT, live preview)."""
from __future__ import annotations

import re
from typing import Optional

VALID_SUBTITLE_SOURCES = {"auto", "en", "zh", "bilingual"}
VALID_BILINGUAL_ORDERS = {"en_top", "zh_top"}

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


def resolve_segment_text(
    seg: dict,
    mode: str = "auto",
    order: str = "en_top",
    line_break: str = "\\N",
) -> str:
    """Return the text string a renderer/exporter should emit for this segment.

    Args:
        seg: dict with `text` or `en_text`, and optional `zh_text`.
        mode: "auto" | "en" | "zh" | "bilingual"
        order: bilingual stacking — "en_top" or "zh_top"
        line_break: ASS callers pass "\\N"; SRT/VTT/TXT/preview pass "\n".

    Behavior:
        - en              → always EN (even if ZH exists)
        - zh              → ZH if non-empty, else EN (per-segment fallback)
        - bilingual       → both stacked; if one side empty, single line
        - auto (default)  → ZH if non-empty, else EN (matches legacy behavior)
    """
    en = (seg.get("text") or seg.get("en_text") or "").strip()
    zh = strip_qa_prefixes(seg.get("zh_text") or "")

    if mode == "en":
        return en
    if mode == "zh":
        return zh or en
    if mode == "bilingual":
        if not en:
            return zh
        if not zh:
            return en
        return f"{en}{line_break}{zh}" if order == "en_top" else f"{zh}{line_break}{en}"
    # default + "auto"
    return zh or en


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
