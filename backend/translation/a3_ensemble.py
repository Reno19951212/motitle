"""A3 ensemble selector — pick max entity recall winner per segment with CPS gate."""
from typing import List, Dict
from translation.entity_recall import find_en_entities, check_zh_has_name
from translation.proxy_entities import (
    extract_proxy_entities,
    has_translit_run,
    TRANSLIT_CHARS,
)


def _count_translit_runs(zh_text: str, min_run: int = 3) -> int:
    """Count distinct >=min_run translit-character runs in zh_text (· allowed in run)."""
    if not zh_text:
        return 0
    runs = 0
    cur = 0
    for ch in zh_text:
        if ch in TRANSLIT_CHARS or ch == "·":
            cur += 1
        else:
            if cur >= min_run:
                runs += 1
            cur = 0
    if cur >= min_run:
        runs += 1
    return runs


def _compute_recall(en_text, zh_text, name_index):
    """Combined recall: known entities (NAME_INDEX) + proxy entities (capitalized + translit).

    Proxy recall counts distinct translit runs in zh_text, capped at the number of
    proxy candidates in en_text — so a translation that preserves both names as
    separate runs (阿拉巴 ... 盧迪加) scores higher than one that fuses them
    (阿拉巴盧迪加).
    """
    en_ents = find_en_entities(en_text, name_index)
    known_score = sum(1 for k in en_ents if check_zh_has_name(zh_text, k, name_index))
    known_total = len(en_ents)

    proxy_ents = extract_proxy_entities(en_text)
    proxy_total = len(proxy_ents)
    if proxy_total > 0:
        proxy_score = min(_count_translit_runs(zh_text), proxy_total)
    else:
        proxy_score = 0

    return known_score + proxy_score, known_total + proxy_total


def _compute_cps(zh_text, duration):
    if not zh_text or duration <= 0:
        return 0.0
    return len(zh_text) / max(0.001, duration)


def apply_a3_ensemble(k0_segs, k2_segs, k4_segs, name_index, cps_limit=9.0):
    """Per-segment: pick max recall winner with CPS gate.

    Returns list of merged segments with `source` field in {k0, k2, k4, k4_unrescuable}.
    Adds `flags` for cps-overflow / k4_unrescuable.
    """
    n = len(k4_segs)
    assert len(k0_segs) == len(k2_segs) == n
    out = []
    priority = {"k4": 0, "k2": 1, "k0": 2}

    for i in range(n):
        en = k4_segs[i].get("en_text", "")
        duration = max(0.001, float(k4_segs[i].get("end", 0)) - float(k4_segs[i].get("start", 0)))

        candidates = [("k0", k0_segs[i]), ("k2", k2_segs[i]), ("k4", k4_segs[i])]
        scored = []
        for src, seg in candidates:
            zh = (seg.get("zh_text") or "").strip()
            recall_n, recall_d = _compute_recall(en, zh, name_index)
            cps = _compute_cps(zh, duration)
            scored.append({
                "src": src,
                "seg": seg,
                "zh": zh,
                "recall": recall_n,
                "cps": cps,
                "len": len(zh),
            })

        # No entities? pick K4 directly (skip recall comparisons)
        en_has_known = bool(find_en_entities(en, name_index))
        en_has_proxy = bool(extract_proxy_entities(en))
        if not en_has_known and not en_has_proxy:
            chosen = scored[2]  # K4
            out.append({
                **chosen["seg"],
                "source": "k4",
                "zh_text": chosen["zh"],
                "flags": list(chosen["seg"].get("flags") or []),
            })
            continue

        # CPS gate — filter to valid candidates
        valid = [s for s in scored if s["cps"] <= cps_limit]
        cps_overflow = (len(valid) == 0)
        if cps_overflow:
            valid = scored

        # Pick max recall; tie -> prefer K4 then K2 then K0
        max_recall = max(s["recall"] for s in valid)
        top = [s for s in valid if s["recall"] == max_recall]
        top.sort(key=lambda s: priority[s["src"]])
        chosen = top[0]

        # Build flags
        flags = list(chosen["seg"].get("flags") or [])
        if cps_overflow and "cps-overflow" not in flags:
            flags.append("cps-overflow")

        # Length safety: if winner > 32, fall back
        if chosen["len"] > 32:
            ordered = sorted(
                scored,
                key=lambda s: (s["len"] > 32, -s["recall"], priority[s["src"]]),
            )
            chosen = ordered[0]
            if chosen["len"] > 32:
                # All too long — accept K4 + flag k4_unrescuable
                chosen = scored[2]
                flags.append("k4_unrescuable")
                out.append({
                    **chosen["seg"],
                    "source": "k4_unrescuable",
                    "zh_text": chosen["zh"],
                    "flags": flags,
                })
                continue

        out.append({
            **chosen["seg"],
            "source": chosen["src"],
            "zh_text": chosen["zh"],
            "flags": flags,
        })

    return out
