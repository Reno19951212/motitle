"""v3.17 validation: snapshot capture + diff metric helpers.

Usage:
  # Capture baseline for two videos
  python backend/scripts/v317_validation.py snapshot --file-id <id1> --output baseline-<id1>.json
  python backend/scripts/v317_validation.py snapshot --file-id <id2> --output baseline-<id2>.json

  # Re-run ASR+MT on a file (after Part A+B applied)
  python backend/scripts/v317_validation.py rerun --file-id <id>

  # Compute diff + render markdown report
  python backend/scripts/v317_validation.py diff --baseline-glob 'baseline-*.json' \\
      --post-glob 'post-*.json' --output v3.17-diff-report.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_URL = "http://localhost:5001"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "AdminPass1!"


def _login_session() -> requests.Session:
    """Login as admin and return authenticated session."""
    s = requests.Session()
    r = s.post(f"{BASE_URL}/login", data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    return s


def capture_snapshot(session: requests.Session, file_id: str) -> Dict[str, Any]:
    """Capture comprehensive snapshot of file state for diff comparison."""
    file_resp = session.get(f"{BASE_URL}/api/files")
    file_resp.raise_for_status()
    files = file_resp.json().get("files", [])
    file_entry = next((f for f in files if f["id"] == file_id), None)
    if file_entry is None:
        raise ValueError(f"file_id {file_id} not found in /api/files")

    segments_resp = session.get(f"{BASE_URL}/api/files/{file_id}/segments")
    segments_resp.raise_for_status()
    segments = segments_resp.json().get("segments", [])

    translations_resp = session.get(f"{BASE_URL}/api/files/{file_id}/translations")
    translations_resp.raise_for_status()
    translations = translations_resp.json().get("translations", [])

    profile_id = file_entry.get("profile_id")
    profile_snapshot = None
    if profile_id:
        prof_resp = session.get(f"{BASE_URL}/api/profiles/{profile_id}")
        if prof_resp.ok:
            profile_snapshot = prof_resp.json()

    glossary_scan = None
    if profile_snapshot:
        glossary_id = profile_snapshot.get("translation", {}).get("glossary_id")
        if glossary_id:
            scan_resp = session.post(
                f"{BASE_URL}/api/files/{file_id}/glossary-scan",
                json={"glossary_id": glossary_id},
            )
            if scan_resp.ok:
                glossary_scan = scan_resp.json()

    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "file": file_entry,
        "segments": segments,
        "translations": translations,
        "profile_snapshot": profile_snapshot,
        "glossary_scan": glossary_scan,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1: Core metrics
# ─────────────────────────────────────────────────────────────────────────────

def latency_delta(baseline: Dict[str, Any], post: Dict[str, Any]) -> Dict[str, Any]:
    """ASR + MT + total seconds, normalized to per-minute-of-video."""
    b_file = baseline["file"]
    p_file = post["file"]
    duration = (b_file.get("duration_seconds") or p_file.get("duration_seconds") or 0.0) / 60.0 or None

    def _norm(seconds, duration_min):
        if not seconds or not duration_min:
            return None
        return round(seconds / duration_min, 2)

    return {
        "baseline_asr_seconds": b_file.get("asr_seconds"),
        "post_asr_seconds": p_file.get("asr_seconds"),
        "baseline_asr_sec_per_min": _norm(b_file.get("asr_seconds"), duration),
        "post_asr_sec_per_min": _norm(p_file.get("asr_seconds"), duration),
        "baseline_mt_seconds": b_file.get("translation_seconds"),
        "post_mt_seconds": p_file.get("translation_seconds"),
        "baseline_total": (b_file.get("asr_seconds") or 0) + (b_file.get("translation_seconds") or 0),
        "post_total": (p_file.get("asr_seconds") or 0) + (p_file.get("translation_seconds") or 0),
        "video_duration_seconds": b_file.get("duration_seconds") or p_file.get("duration_seconds"),
    }


def segmentation_delta(baseline: Dict, post: Dict) -> Dict[str, Any]:
    """Count, duration, word stats."""
    def _stats(segments):
        if not segments:
            return {"count": 0, "avg_duration": None, "min_duration": None, "max_duration": None, "avg_word_count": None}
        durs = [s["end"] - s["start"] for s in segments]
        words = [len((s.get("text") or "").split()) for s in segments]
        return {
            "count": len(segments),
            "avg_duration": round(sum(durs) / len(durs), 2),
            "min_duration": round(min(durs), 2),
            "max_duration": round(max(durs), 2),
            "avg_word_count": round(sum(words) / len(words), 1),
        }
    return {"baseline": _stats(baseline["segments"]), "post": _stats(post["segments"])}


def asr_text_delta(baseline: Dict, post: Dict, time_tolerance: float = 0.5) -> Dict[str, Any]:
    """Pair segments by start_time (±tolerance); count identical/changed/new/dropped."""
    b_segs = baseline["segments"]
    p_segs = post["segments"]
    b_unmatched = list(range(len(b_segs)))

    identical = 0
    changed = []  # list of (baseline_text, post_text, timestamp)
    new_segments = []  # in post not in baseline

    for p_idx, p in enumerate(p_segs):
        match_idx = None
        for bi in b_unmatched:
            if abs(b_segs[bi]["start"] - p["start"]) <= time_tolerance:
                match_idx = bi
                break
        if match_idx is None:
            new_segments.append({"start": p["start"], "text": p.get("text", "")})
        else:
            b_unmatched.remove(match_idx)
            if b_segs[match_idx].get("text", "") == p.get("text", ""):
                identical += 1
            else:
                changed.append({
                    "start": p["start"],
                    "baseline": b_segs[match_idx].get("text", ""),
                    "post": p.get("text", ""),
                })

    dropped = [{"start": b_segs[bi]["start"], "text": b_segs[bi].get("text", "")} for bi in b_unmatched]

    return {
        "identical": identical,
        "changed_count": len(changed),
        "new_count": len(new_segments),
        "dropped_count": len(dropped),
        "top_changes": changed[:10],
        "top_new": new_segments[:5],
        "top_dropped": dropped[:5],
    }


def mt_text_delta(baseline: Dict, post: Dict) -> Dict[str, Any]:
    """Pair translations by index; count identical/changed."""
    b_t = baseline["translations"]
    p_t = post["translations"]
    n = min(len(b_t), len(p_t))
    identical = 0
    changed = []
    for i in range(n):
        b_zh = b_t[i].get("zh_text", "")
        p_zh = p_t[i].get("zh_text", "")
        if b_zh == p_zh:
            identical += 1
        else:
            changed.append({
                "index": i,
                "en": p_t[i].get("en_text", ""),
                "baseline_zh": b_zh,
                "post_zh": p_zh,
            })
    return {
        "identical": identical,
        "changed_count": len(changed),
        "length_baseline": len(b_t),
        "length_post": len(p_t),
        "top_changes": changed[:10],
    }


def glossary_scan_delta(baseline: Dict, post: Dict) -> Dict[str, Any]:
    """Compare violation counts before/after."""
    b = baseline.get("glossary_scan") or {}
    p = post.get("glossary_scan") or {}
    if not b and not p:
        return {"skipped": True, "reason": "neither baseline nor post had glossary_id in profile"}
    return {
        "baseline_strict_count": b.get("strict_violation_count", 0),
        "post_strict_count": p.get("strict_violation_count", 0),
        "baseline_loose_count": b.get("loose_violation_count", 0),
        "post_loose_count": p.get("loose_violation_count", 0),
        "top_strict_baseline": (b.get("strict_violations") or [])[:5],
        "top_strict_post": (p.get("strict_violations") or [])[:5],
        "top_loose_baseline": (b.get("loose_violations") or [])[:5],
        "top_loose_post": (p.get("loose_violations") or [])[:5],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2: Broadcast Quality metrics
# ─────────────────────────────────────────────────────────────────────────────

_CJK_RE = re.compile(r"[一-鿿]")
_LATIN_WORD_RE = re.compile(r"[a-zA-Z]{3,}")
_BRAND_WHITELIST = {"NBA", "FIFA", "UEFA", "BBC", "CNN", "AI", "GPS", "USA", "UK"}


def subtitle_length_distribution(translations: List[Dict]) -> Dict[str, int]:
    """ZH char-count histogram."""
    buckets = {"0-10": 0, "11-15": 0, "16-20": 0, "21-28": 0, "29-40": 0, ">40": 0}
    for t in translations:
        n = len(t.get("zh_text", "") or "")
        if n <= 10:
            buckets["0-10"] += 1
        elif n <= 15:
            buckets["11-15"] += 1
        elif n <= 20:
            buckets["16-20"] += 1
        elif n <= 28:
            buckets["21-28"] += 1
        elif n <= 40:
            buckets["29-40"] += 1
        else:
            buckets[">40"] += 1
    return buckets


def reading_speed_cps(translations: List[Dict], segments: List[Dict]) -> Dict[str, Any]:
    """Chars-per-second per segment. Broadcast band 12-17 CPS."""
    # Pair translations to segments by index
    n = min(len(translations), len(segments))
    cps_values = []
    too_slow = []  # <8 CPS
    too_fast = []  # >20 CPS
    for i in range(n):
        zh = translations[i].get("zh_text", "") or ""
        dur = segments[i]["end"] - segments[i]["start"]
        if dur <= 0 or not zh:
            continue
        cps = len(zh) / dur
        cps_values.append(cps)
        if cps < 8:
            too_slow.append({"index": i, "zh": zh, "duration": round(dur, 2), "cps": round(cps, 1)})
        elif cps > 20:
            too_fast.append({"index": i, "zh": zh, "duration": round(dur, 2), "cps": round(cps, 1)})
    if not cps_values:
        return {"skipped": True, "reason": "no paired segments with translation"}
    return {
        "avg_cps": round(sum(cps_values) / len(cps_values), 1),
        "min_cps": round(min(cps_values), 1),
        "max_cps": round(max(cps_values), 1),
        "in_broadcast_band_12_17": sum(1 for c in cps_values if 12 <= c <= 17),
        "too_slow_count": len(too_slow),
        "too_fast_count": len(too_fast),
        "top_too_slow": too_slow[:5],
        "top_too_fast": too_fast[:5],
    }


def language_consistency(segments: List[Dict], translations: List[Dict]) -> Dict[str, Any]:
    """EN-with-CJK contamination + ZH-with-Latin words + simplified-leak."""
    en_with_cjk = []
    for s in segments:
        text = s.get("text", "") or ""
        if _CJK_RE.search(text):
            en_with_cjk.append({"start": s.get("start"), "text": text})

    zh_with_latin = []
    for i, t in enumerate(translations):
        zh = t.get("zh_text", "") or ""
        latins = _LATIN_WORD_RE.findall(zh)
        leaked = [w for w in latins if w.upper() not in _BRAND_WHITELIST]
        if leaked:
            zh_with_latin.append({"index": i, "zh": zh, "latin_words": leaked})

    # Simplified leak: use OpenCC s2hk if available; segments where s2hk(zh) != zh contain simplified chars
    simplified_leak = []
    opencc_available = True
    try:
        from opencc import OpenCC
        cc = OpenCC("s2hk")
        for i, t in enumerate(translations):
            zh = t.get("zh_text", "") or ""
            converted = cc.convert(zh)
            if converted != zh and zh:
                simplified_leak.append({"index": i, "original": zh, "converted": converted})
    except ImportError:
        opencc_available = False
        simplified_leak = [{"error": "OpenCC not installed"}]

    return {
        "en_with_cjk_count": len(en_with_cjk),
        "zh_with_latin_count": len(zh_with_latin),
        "simplified_leak_count": len(simplified_leak) if opencc_available else None,
        "top_en_with_cjk": en_with_cjk[:5],
        "top_zh_with_latin": zh_with_latin[:5],
        "top_simplified_leak": simplified_leak[:5] if opencc_available else [],
    }


def repetition_detect(translations: List[Dict], min_overlap_ratio: float = 0.7) -> List[Dict]:
    """Adjacent segments where ZH text overlap >= ratio (cascade signal)."""
    pairs = []
    for i in range(len(translations) - 1):
        a = (translations[i].get("zh_text") or "").strip()
        b = (translations[i + 1].get("zh_text") or "").strip()
        if not a or not b:
            continue
        # Simple metric: longest common substring length / max(len)
        # For perf, use set-of-chars Jaccard as cheap proxy
        sa, sb = set(a), set(b)
        if not sa or not sb:
            continue
        jaccard = len(sa & sb) / len(sa | sb)
        if jaccard >= min_overlap_ratio or a == b or a in b or b in a:
            pairs.append({"index": i, "next": i + 1, "zh_a": a, "zh_b": b, "jaccard": round(jaccard, 2)})
    return pairs


# ─────────────────────────────────────────────────────────────────────────────
# Tier 3: Diagnostic metrics
# ─────────────────────────────────────────────────────────────────────────────

def segment_timing_health(segments: List[Dict]) -> Dict[str, Any]:
    """Count of too-short / too-long segments + gap distribution."""
    if not segments:
        return {"skipped": True, "reason": "no segments"}
    too_short = [s for s in segments if s["end"] - s["start"] < 0.3]
    too_long = [s for s in segments if s["end"] - s["start"] > 7.0]
    gaps = []
    for i in range(1, len(segments)):
        gap = segments[i]["start"] - segments[i - 1]["end"]
        if gap > 0:
            gaps.append(gap)
    return {
        "too_short_count": len(too_short),
        "too_long_count": len(too_long),
        "avg_gap": round(sum(gaps) / len(gaps), 2) if gaps else None,
        "max_gap": round(max(gaps), 2) if gaps else None,
        "top_too_short": [{"start": s["start"], "duration": round(s["end"] - s["start"], 2), "text": s.get("text", "")} for s in too_short[:5]],
        "top_too_long": [{"start": s["start"], "duration": round(s["end"] - s["start"], 2), "text": s.get("text", "")} for s in too_long[:5]],
    }


def flag_rates(translations: List[Dict]) -> Dict[str, Any]:
    """Counts of [LONG], [NEEDS REVIEW] flags + hallucination heuristic."""
    long_count = sum(1 for t in translations if "long" in (t.get("flags") or []))
    review_count = sum(1 for t in translations if "review" in (t.get("flags") or []))
    hallucinated = [t for t in translations if len(t.get("zh_text", "") or "") > 40]
    return {
        "total_count": len(translations),
        "long_flag_count": long_count,
        "long_flag_pct": round(100 * long_count / len(translations), 1) if translations else 0,
        "review_flag_count": review_count,
        "hallucination_count": len(hallucinated),
        "hallucination_pct": round(100 * len(hallucinated) / len(translations), 1) if translations else 0,
    }


def batch_boundary_check(translations: List[Dict], batch_size: int) -> Dict[str, Any]:
    """Check for repetition + abrupt context at batch edges (only if batch_size > 1)."""
    if not batch_size or batch_size <= 1:
        return {"skipped": True, "reason": f"batch_size={batch_size}, no boundaries to check"}
    boundaries = list(range(batch_size, len(translations), batch_size))
    edge_repetition = []
    for b in boundaries:
        if b == 0 or b >= len(translations):
            continue
        prev_zh = (translations[b - 1].get("zh_text") or "").strip()
        curr_zh = (translations[b].get("zh_text") or "").strip()
        if prev_zh and curr_zh and (prev_zh == curr_zh or prev_zh in curr_zh or curr_zh in prev_zh):
            edge_repetition.append({"boundary": b, "prev_zh": prev_zh, "curr_zh": curr_zh})
    return {
        "boundary_count": len(boundaries),
        "edge_repetition_count": len(edge_repetition),
        "top_edge_repetition": edge_repetition[:5],
    }


def word_level_alignment(segments: List[Dict]) -> Dict[str, Any]:
    """% segments with words[] populated + avg word count."""
    if not segments:
        return {"skipped": True}
    with_words = [s for s in segments if s.get("words")]
    word_counts = [len(s["words"]) for s in with_words]
    return {
        "total_segments": len(segments),
        "with_words_count": len(with_words),
        "with_words_pct": round(100 * len(with_words) / len(segments), 1),
        "avg_word_count": round(sum(word_counts) / len(word_counts), 1) if word_counts else None,
    }


def approval_state(baseline_translations: List[Dict], post_translations: List[Dict]) -> Dict[str, Any]:
    """Baseline approved/pending vs post (post resets to all pending)."""
    def _count(t_list):
        approved = sum(1 for t in t_list if t.get("status") == "approved")
        pending = sum(1 for t in t_list if t.get("status") != "approved")
        return {"approved": approved, "pending": pending}
    return {
        "baseline": _count(baseline_translations),
        "post": _count(post_translations),
        "note": "Post re-run resets all approvals to pending; baseline counts are ground-truth pre-v3.17 reviewer state.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def cmd_snapshot(args):
    s = _login_session()
    snap = capture_snapshot(s, args.file_id)
    Path(args.output).write_text(json.dumps(snap, ensure_ascii=False, indent=2))
    print(f"Wrote snapshot to {args.output}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("snapshot")
    sp.add_argument("--file-id", required=True)
    sp.add_argument("--output", required=True)
    sp.set_defaults(func=cmd_snapshot)

    # (rerun and diff subcommands added in later tasks)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
