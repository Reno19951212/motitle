"""Post-process correction for ZH-direct ASR output via glossary zh_aliases.

When the active profile runs mlx-whisper with ``language="zh"`` against
English source audio (cross-lingual zero-shot), the model frequently emits
Cantonese / Mandarin transliterations of proper nouns that disagree with the
team's preferred form (e.g. ``拉爾馬德里`` instead of ``皇家馬德里``). The glossary
already encodes the canonical pair (``Real Madrid`` → ``皇家馬德里``); ``zh_aliases``
extends each entry with the wrong-form transliterations Whisper actually
produces, so we can deterministically rewrite them at post-process time.

Design notes:
- Pure-string replacement (no LLM round-trip) — runs in microseconds and
  carries no risk of cascading drift.
- Aliases are sorted by length DESC so longer matches always win over
  shorter overlapping prefixes (avoids partial-match corruption).
- Chinese has no word boundaries — we cannot use ``\\b`` lookarounds; this
  is by design and per Whisper output's inherent character-stream shape.
- Only triggered for ``language == "zh"`` paths in the orchestrator; the
  EN-direct route is unaffected.

Public surface:
- ``correct_zh_segment(text, alias_map)`` — single-string correction.
- ``build_alias_map(glossary_entries)`` — derive ``{wrong: canonical}`` map.
- ``correct_segments(segments, glossary_entries, ws_emit=None)`` — apply to
  a full segment list (mutates in place + returns); also rewrites words[]
  glyphs when present so downstream alignment stays consistent.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple


def correct_zh_segment(
    text: str, alias_to_canonical: dict
) -> Tuple[str, List[str]]:
    """Replace each alias occurrence in ``text`` with its canonical zh form.

    Args:
        text: Whisper output (Traditional or Simplified Chinese, no normalisation).
        alias_to_canonical: ``{wrong_zh_form: correct_zh_form}`` (built via
            :func:`build_alias_map`).

    Returns:
        ``(corrected_text, applied_aliases)`` — ``applied_aliases`` lists
        every alias key that produced at least one replacement (useful for
        telemetry / WS emit).
    """
    if not text or not alias_to_canonical:
        return text, []
    applied: List[str] = []
    out = text
    # Length-DESC sort → longest match wins. Critical when two aliases share
    # a prefix, e.g. {"皇馬": ..., "皇馬球迷": ...} — we want the longer one
    # rewritten first, otherwise the inner "皇馬" hit corrupts it.
    for alias in sorted(alias_to_canonical.keys(), key=len, reverse=True):
        if not alias:
            continue
        canonical = alias_to_canonical[alias]
        if alias == canonical:
            continue
        if alias in out:
            out = out.replace(alias, canonical)
            applied.append(alias)
    return out, applied


def build_alias_map(glossary_entries: list) -> dict:
    """Build a ``{alias: canonical_zh}`` lookup from a glossary entry list.

    Skips entries with no ``zh`` value, no ``zh_aliases`` list, or aliases
    equal to the canonical form (no-op replacements). Also skips empty /
    whitespace-only aliases.
    """
    out: dict = {}
    for entry in glossary_entries or []:
        canonical_zh = (entry.get("zh") or "").strip()
        if not canonical_zh:
            continue
        for alias in entry.get("zh_aliases") or []:
            if not isinstance(alias, str):
                continue
            alias_clean = alias.strip()
            if alias_clean and alias_clean != canonical_zh:
                # Last-write-wins: if two glossary entries claim the same
                # alias, the later one in the list takes precedence.
                out[alias_clean] = canonical_zh
    return out


def correct_segments(
    segments: list,
    glossary_entries: list,
    ws_emit: Optional[Callable[[str, str], None]] = None,
) -> list:
    """Apply alias corrections to every segment's ``text`` (and ``words[]``).

    Args:
        segments: List of segment dicts. Each must have a ``text`` key;
            optional ``words`` list (per-word dicts with ``word`` field) is
            also rewritten so glyph-level alignment stays consistent.
        glossary_entries: List of glossary entry dicts (each with ``zh`` and
            optional ``zh_aliases``).
        ws_emit: Optional callback ``(kind, message)`` for WebSocket
            telemetry. Called once with kind ``"zh_alias_corrected"`` if any
            corrections were applied across the whole pass.

    Returns:
        The (mutated) ``segments`` list. Returned as-is so the call site
        can chain it through fluent pipelines.
    """
    if not segments or not glossary_entries:
        return segments
    alias_map = build_alias_map(glossary_entries)
    if not alias_map:
        return segments

    total_applied = 0
    for seg in segments:
        text = seg.get("text", "")
        if text:
            corrected, applied = correct_zh_segment(text, alias_map)
            if applied:
                seg["text"] = corrected
                total_applied += len(applied)
        # Rewrite per-word tokens too — keeps word-level alignment glyphs
        # in sync with the segment-level text.
        words = seg.get("words")
        if words:
            for w in words:
                wt = w.get("word", "")
                if not wt:
                    continue
                new_wt, _ = correct_zh_segment(wt, alias_map)
                if new_wt != wt:
                    w["word"] = new_wt

    if total_applied and ws_emit is not None:
        try:
            ws_emit(
                "zh_alias_corrected",
                f"applied {total_applied} glossary correction(s)",
            )
        except Exception:
            # Telemetry failure should never break the ASR pipeline.
            pass
    return segments
