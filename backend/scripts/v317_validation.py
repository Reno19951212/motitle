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
