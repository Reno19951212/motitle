"""Content-fidelity metrics — F1 (entity recall), F2 (hallucination), F3 (per-seg histogram).

Ported from /tmp/loop/fidelity.py. Adapted to import the shared SEED_NAME_INDEX
+ recall helpers from `translation.entity_recall` rather than maintaining a
duplicate copy. The /tmp/loop NAME_INDEX had a couple of extra
keys (athletic/the athletic, kane synonyms) and lookups (rudiger,) that the
production index now exposes via glossary extension; we keep those as a small
local addendum so this file remains a one-stop fidelity layer for regression.

Outputs:
  F1_overall_recall_pct: % of EN proper-noun entities whose ZH equivalent
    appears in the corresponding ZH translation (recall ratio).
  F2_hallucination_count: count of ZH name-like tokens not justified by EN.
  F3_*: per-segment full / partial / dropped recall histograms.
"""
import json
import re
import sys
from typing import Any, Dict, List

from translation.entity_recall import SEED_NAME_INDEX


# Local addendum — entries the /tmp/loop validation harness used that aren't
# in SEED_NAME_INDEX. Folded in once at module import; no runtime mutation
# of the production index.
_ADDENDUM_NAME_INDEX: Dict[str, List[str]] = {
    "athletic":     ["The Athletic", "運動報"],
    "the athletic": ["The Athletic", "運動報"],
    "como":         ["科莫", "意乙科莫"],
    "nico paz":     ["帕斯", "尼科爾·帕斯", "尼科·帕斯"],
    "kroos":        ["告魯斯"],
}


def _build_index() -> Dict[str, List[str]]:
    idx = {k: list(v) for k, v in SEED_NAME_INDEX.items()}
    for k, vs in _ADDENDUM_NAME_INDEX.items():
        if k not in idx:
            idx[k] = []
        for v in vs:
            if v not in idx[k]:
                idx[k].append(v)
    return idx


NAME_INDEX = _build_index()


def find_en_entities(en_text: str) -> set:
    """Return set of normalized name keys present in EN text (word-boundary match)."""
    txt = (en_text or "").lower()
    found = set()
    for key in NAME_INDEX:
        if re.search(r'\b' + re.escape(key) + r'\b', txt):
            found.add(key)
    return found


def check_zh_has_name(zh_text: str, key: str) -> bool:
    """Return True if any ZH variant for `key` appears in `zh_text`."""
    for v in NAME_INDEX.get(key, []):
        if v in zh_text:
            return True
    return False


def detect_zh_names_not_in_en(en_text: str, zh_text: str) -> List[tuple]:
    """Detect ZH name-like tokens not justified by EN (hallucination heuristic)."""
    en_lower = (en_text or "").lower()
    extras = []
    for key, variants in NAME_INDEX.items():
        for v in variants:
            if v in zh_text:
                related = [k for k in NAME_INDEX if v in NAME_INDEX[k]]
                if not any(re.search(r'\b' + re.escape(k) + r'\b', en_lower) for k in related):
                    extras.append((v, key))
                    break
    return extras


def compute_fidelity(translations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-corpus fidelity metrics over a list of {en_text, zh_text}."""
    n = len(translations)
    total_expected = 0
    total_recalled = 0
    hallucinations: List[Dict[str, Any]] = []
    per_seg: List[Dict[str, Any]] = []
    seg_full_recall = 0
    seg_partial_recall = 0
    seg_no_entities = 0
    seg_dropped = 0

    for i, t in enumerate(translations):
        en = t.get("en_text", "") or ""
        zh = (t.get("zh_text") or "").strip()

        en_ents = find_en_entities(en)
        if not en_ents:
            seg_no_entities += 1
            per_seg.append({"i": i, "en_ents": [], "recall": None})
            continue

        unique_keys_recalled = set()
        for k in en_ents:
            if check_zh_has_name(zh, k):
                unique_keys_recalled.add(k)

        total_expected += len(en_ents)
        total_recalled += len(unique_keys_recalled)

        recall = len(unique_keys_recalled) / max(1, len(en_ents))
        per_seg.append({
            "i": i,
            "en": en[:80],
            "zh": zh,
            "en_ents": list(en_ents),
            "recalled": list(unique_keys_recalled),
            "missed": list(en_ents - unique_keys_recalled),
            "recall": round(recall, 2),
        })

        if recall == 1.0:
            seg_full_recall += 1
        elif recall == 0.0:
            seg_dropped += 1
        else:
            seg_partial_recall += 1

        extras = detect_zh_names_not_in_en(en, zh)
        if extras:
            hallucinations.append({"i": i, "en": en[:80], "zh": zh, "extras": extras})

    overall_recall = total_recalled / max(1, total_expected)

    return {
        "n_segs": n,
        "F1_overall_recall_pct": round(overall_recall * 100, 1),
        "n_segs_with_entities": n - seg_no_entities,
        "F2_hallucination_count": len(hallucinations),
        "F3_segs_full_recall": seg_full_recall,
        "F3_segs_partial_recall": seg_partial_recall,
        "F3_segs_dropped": seg_dropped,
        "F3_segs_no_entities": seg_no_entities,
        "total_expected_entities": total_expected,
        "total_recalled_entities": total_recalled,
        "hallucination_samples": hallucinations[:10],
        "missed_samples": [s for s in per_seg if s.get("missed")][:15],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: fidelity.py <result.json>")
        sys.exit(1)
    result = json.load(open(sys.argv[1]))
    fid = compute_fidelity(result.get("translations", []))
    print(json.dumps(fid, ensure_ascii=False, indent=2))
