"""
output_lang_persist.py — pure helper for the output-language pipeline.

Provides a single public function ``build_output_translations`` that builds
the translation-row list consumed by the file registry (``/api/files``
translations endpoint, renderer, and export routes).

Design notes
------------
* **Pure function only.**  No imports from ``app.py`` or ``pipeline_runner.py``
  — zero coupling to the Flask app or the V6 pipeline internals.  The registry
  write stays in ``app.py`` (Task T5 will wire it there), keeping this module
  single-responsibility and independently testable.

* **Immutability.**  Every row is a freshly constructed dict.  ``source_segments``
  and the input ``segs`` lists are never mutated.

* **Authoritative mirror.**  The ``{lang}_text`` top-level key is set *last*,
  directly from the translation text — never copied from a source-segment field
  that might happen to share the same key (the "B2 9e3ef67 lesson").

* **by_lang + role-based shape.**  The output is shape-compatible with V6/B1/B2:
  ``row["by_lang"][lang] = {"text": ..., "status": "pending", "flags": []}``
  plus the ``{lang}_text`` mirror used by export/render.
"""

from typing import Any, Dict, List, Tuple


def build_output_translations(
    source_segments: List[Dict[str, Any]],
    lang_segment_pairs: List[Tuple[str, List[Dict[str, Any]]]],
) -> List[Dict[str, Any]]:
    """Build translation rows from one or more per-language segment lists.

    Parameters
    ----------
    source_segments:
        The canonical timing list — each entry must have at least ``start``
        and ``end`` keys.  Length determines the number of output rows.
    lang_segment_pairs:
        Ordered list of ``(lang_code, segs)`` tuples.  Index 0 is the first /
        primary language, index 1 is the second language (matches V6 B1/B2
        role ordering).  ``segs`` may be shorter than ``source_segments``; any
        missing index yields an empty string for that row.

    Returns
    -------
    List[dict]
        A new list of new dicts.  Each row has:
        ``idx``, ``start``, ``end``, ``status``, ``by_lang``,
        ``glossary_changes`` (collected from the per-language derived segments;
        ``[]`` when no glossary stage ran), and ``{lang}_text`` mirror keys for
        every language provided.
    """
    rows: List[Dict[str, Any]] = []

    for i, src in enumerate(source_segments):
        row: Dict[str, Any] = {
            "idx": i,
            "start": src.get("start"),
            "end": src.get("end"),
            "status": "pending",
            "by_lang": {},
        }

        # Aggregate glossary changes across every derived language at this index.
        # glossary_stage attaches seg["glossary_changes"] per output segment; rows
        # are the proofread unit, so we union them here (empty list when none).
        glossary_changes: List[Dict[str, Any]] = []

        for lang, segs in lang_segment_pairs:
            # Safe access: if segs is shorter than source_segments, yield "".
            seg = segs[i] if i < len(segs) else {}
            text: str = seg.get("text", "")

            # AUTHORITATIVE write: by_lang entry first, then the top-level
            # mirror — both from the same variable so they can never diverge.
            row["by_lang"][lang] = {
                "text": text,
                "status": "pending",
                "flags": [],
            }
            # Mirror written LAST, after by_lang, to prevent any stale value
            # already present in row (e.g. copied from source_segments) from
            # masking the translation output (B2 9e3ef67 lesson).
            row[f"{lang}_text"] = text

            for ch in (seg.get("glossary_changes") or []):
                glossary_changes.append(ch)

        row["glossary_changes"] = glossary_changes
        rows.append(row)

    return rows
