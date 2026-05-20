"""v5 file registry translations shape converter.

v4 shape:
  [{idx, en_text, zh_text, status, flags}]

v5 shape:
  [{idx, start, end, source_lang, source_text,
    by_lang: {lang: {text, status, flags}}}]

Two-way converter:
  - normalize_translations_for_v5() — v4 → v5 (used when ?shape=v5 query param)
  - downgrade_translations_to_v4() — v5 → v4 (used by default GET for live v4 frontend compat)

v5-shaped input passes through normalize_translations_for_v5 unchanged.
v4-shaped input passes through downgrade_translations_to_v4 unchanged.
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


def downgrade_translations_to_v4(raw: list) -> list:
    """Flatten v5 [{by_lang: {lang: {text}}}] → v4 [{en_text, zh_text, status, flags}].

    Used at GET response time when caller wants v4 shape (default behavior, so
    the live v4 React frontend reading `zh_text` / `en_text` directly keeps
    working without code changes).

    Per-entry rule (also preserves v5 source_text / start / end / source_lang
    as harmless extra fields — v4 frontend ignores them):
      - en_text = by_lang.en.text, OR source_text if source_lang == 'en', OR existing en_text
      - zh_text = by_lang.zh.text, OR source_text if source_lang == 'zh', OR existing zh_text
      - status  = by_lang.zh.status (v4 was implicitly ZH-focused), OR existing status
      - flags   = by_lang.zh.flags, OR existing flags

    Entries lacking `by_lang` (already v4) pass through unchanged.
    """
    if not raw:
        return []
    out: list = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if "by_lang" not in entry:
            out.append(entry)
            continue
        by_lang = entry["by_lang"] or {}
        source_lang = entry.get("source_lang")
        source_text = entry.get("source_text", "")
        en_payload = by_lang.get("en") or {}
        zh_payload = by_lang.get("zh") or {}

        en_text = en_payload.get("text") or (source_text if source_lang == "en" else entry.get("en_text", ""))
        zh_text = zh_payload.get("text") or (source_text if source_lang == "zh" else entry.get("zh_text", ""))
        status = zh_payload.get("status") or entry.get("status", "pending")
        flags = zh_payload.get("flags") or entry.get("flags", [])

        downgraded = {
            **{k: v for k, v in entry.items() if k != "by_lang"},
            "en_text": en_text,
            "zh_text": zh_text,
            "status": status,
            "flags": flags,
        }
        out.append(downgraded)
    return out
