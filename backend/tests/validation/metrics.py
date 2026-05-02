"""Compute KPIs (M1-M5, L1, Q1-Q3) for one (candidate, file) trial.

Ported from /tmp/loop/metrics.py (proven through 45 validation rounds).
Adapted for in-tree path: imports from production translation/sentence_pipeline
and subtitle_wrap rather than the throwaway /tmp/loop copies.

Used by `run_regression.py` (G3 gate). Pure metric code — no LLM calls.
"""
from typing import Any, Dict, List

from translation.sentence_pipeline import _build_full_lock
from subtitle_wrap import wrap_hybrid, wrap_zh

import re


_HARD_END = "。！？!?"
_ZH_CHAR_RE = re.compile(r'[一-鿿]')


def _is_zh(s: str) -> bool:
    return bool(_ZH_CHAR_RE.search(s or ""))


def _name_split_count(zh_text: str) -> int:
    """Count newline split points that fall inside a locked region.

    Uses the V_R11 full-lock chain (middle-dot + bracket + number + translit
    + dot-heuristic + glossary) — same lock the renderer uses at burn-in time.
    """
    if not zh_text or "\n" not in zh_text:
        return 0
    flat = zh_text.replace("\n", "")
    locked = _build_full_lock(flat)
    splits: List[int] = []
    pos = 0
    for ln in zh_text.split("\n")[:-1]:
        pos += len(ln)
        splits.append(pos)
    return sum(1 for sp in splits if 0 < sp < len(locked) and locked[sp])


def _wrap_text(zh_text: str, candidate_id: str) -> Dict[str, Any]:
    """Apply candidate's wrap logic to one cue. Returns wrap result + flags.

    Candidate map:
        K0 / K2 → broadcast baseline 28/2/2 via production wrap_zh
        K1 / K3 / K4 / A4 → hybrid 14 soft / 16 hard / max-2-lines + V_R11 lock
    """
    text = (zh_text or "").strip()
    locked = _build_full_lock(text) if text else []

    if candidate_id in ("K0", "K2"):
        r = wrap_zh(text, cap=28, max_lines=2, tail_tolerance=2)
        soft_overflow = any(len(ln) > 14 for ln in r.lines)
        bh_viol = (len(r.lines) == 2 and len(r.lines[0]) > len(r.lines[1]))
        lines = list(r.lines)
        return {
            "lines": lines,
            "n_lines": len(lines),
            "max_line_len": max((len(ln) for ln in lines), default=0),
            "total_chars": sum(len(ln) for ln in lines),
            "hard_cut": r.hard_cut,
            "soft_overflow": soft_overflow,
            "bottom_heavy_violation": bh_viol,
        }

    if candidate_id in (
        "K1", "K3", "K4",
        "K4_cap10", "K4_cap12", "K4_cap16",
        "K4_safe", "K4_safe_cap16",
        "A4", "A4_cap14", "A4_cap16",
    ):
        r2 = wrap_hybrid(text, soft_cap=14, hard_cap=16, max_lines=2,
                         tail_tolerance=2, locked=locked)
        return {
            "lines": list(r2.lines),
            "n_lines": len(r2.lines),
            "max_line_len": max((len(ln) for ln in r2.lines), default=0),
            "total_chars": sum(len(ln) for ln in r2.lines),
            "hard_cut": r2.hard_cut,
            "soft_overflow": r2.soft_overflow,
            "bottom_heavy_violation": r2.bottom_heavy_violation,
        }

    raise ValueError(f"unknown candidate {candidate_id}")


def compute_kpis(translations: List[Dict[str, Any]], candidate_id: str) -> Dict[str, Any]:
    """Run wrap on every translation and compute KPI dict.

    translations: list of dicts with 'zh_text', 'start', 'end'.
    candidate_id: which wrap variant to apply (see _wrap_text).
    """
    n = len(translations)
    if n == 0:
        return {"n": 0, "error": "empty"}

    results = []
    for t in translations:
        zh = (t.get("zh_text") or "").strip()
        wr = _wrap_text(zh, candidate_id)
        wr["zh_text"] = zh
        wr["zh_len"] = len(zh)
        wr["duration"] = max(0.001, float(t.get("end", 0)) - float(t.get("start", 0)))
        wr["cps"] = wr["zh_len"] / wr["duration"]
        results.append(wr)

    n_le14_single = sum(1 for r in results if r["n_lines"] == 1 and r["max_line_len"] <= 14)
    n_le16_le2 = sum(1 for r in results if r["n_lines"] <= 2 and r["max_line_len"] <= 16)
    n_2line = sum(1 for r in results if r["n_lines"] == 2)
    n_bh_compliant = sum(1 for r in results if r["n_lines"] == 2 and not r["bottom_heavy_violation"])
    n_hard_cut = sum(1 for r in results if r["hard_cut"])
    n_soft_overflow = sum(1 for r in results if r["soft_overflow"])
    max_cps = max((r["cps"] for r in results if r["zh_len"] > 0), default=0)
    over_9cps = sum(1 for r in results if r["cps"] > 9.0)

    name_splits = sum(
        _name_split_count("\n".join(r["lines"]))
        for r in results
        if r["n_lines"] > 1
    )

    mid_cut = sum(
        1 for r in results
        if r["zh_len"] > 0 and r["zh_text"][-1] not in _HARD_END
    )
    single_char = sum(1 for r in results if r["zh_len"] <= 1)
    empty = sum(1 for r in results if r["zh_len"] == 0)

    return {
        "n": n,
        "M1_pct_le14_single": round(n_le14_single / n * 100, 2),
        "M2_pct_le16_le2lines": round(n_le16_le2 / n * 100, 2),
        "M3_pct_bottom_heavy": round((n_bh_compliant / n_2line * 100) if n_2line else 100.0, 2),
        "M4_max_cps": round(max_cps, 2),
        "M4_pct_over_9cps": round(over_9cps / n * 100, 2),
        "M5_hard_cut_pct": round(n_hard_cut / n * 100, 2),
        "M5_soft_overflow_pct": round(n_soft_overflow / n * 100, 2),
        "L1_name_split_count": name_splits,
        "Q1_mid_cut_pct": round(mid_cut / n * 100, 2),
        "Q2_single_char_count": single_char,
        "Q3_empty_count": empty,
        "n_2line": n_2line,
        "n_1line": n - n_2line - empty,
    }
