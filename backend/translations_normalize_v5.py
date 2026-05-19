"""v5 file registry translations shape converter.

v4 shape:
  [{idx, en_text, zh_text, status, flags}]

v5 shape:
  [{idx, start, end, source_lang, source_text,
    by_lang: {lang: {text, status, flags}}}]

normalize_translations_for_v5() converts v4 → v5 at read time. v5-shaped
input passes through. Used in GET /api/files/<id>/translations response
so frontend can rely on a single shape.
"""
from __future__ import annotations

from typing import Any


def normalize_translations_for_v5(raw: list) -> list:
    """Convert v4 [{en_text, zh_text}] → v5 [{by_lang}]. v5 input passes through."""
    if not raw:
        return []
    out: list = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if "by_lang" in entry:
            # Already v5
            out.append(entry)
            continue
        out.append({
            "idx": entry.get("idx", 0),
            "start": entry.get("start"),
            "end": entry.get("end"),
            "source_lang": "en",  # v4 implicit assumption
            "source_text": entry.get("en_text", ""),
            "by_lang": {
                "zh": {
                    "text": entry.get("zh_text", ""),
                    "status": entry.get("status", "pending"),
                    "flags": entry.get("flags", []),
                },
            },
        })
    return out
