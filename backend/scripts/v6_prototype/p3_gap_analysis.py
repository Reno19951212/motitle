#!/usr/bin/env python3
"""V6 segmentation Validation Prototype 3 (2026-05-30).

Hypothesis: the over-cap segments that have NO internal Chinese punctuation
(clause-split can't break them) contain CLEAR acoustic pauses (inter-character
time gaps in Qwen3's per-char timestamps) that could serve as split points.

Cheap — reuses the P2 dump (backend/scripts/v6_prototype/seg_data/qwen3_chars_vtdown.json,
681 per-char items with absolute start/end). Live over-cap segments fetched from
the running backend. No ASR re-run.

Run: python3 backend/scripts/v6_prototype/p3_gap_analysis.py
"""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
CHARS = os.path.join(HERE, "seg_data", "qwen3_chars_vtdown.json")
CAP = 24
_PUNCT = "。！？，、；：!?,;:"


def login_cookie():
    out = subprocess.run(
        ["curl", "-s", "-i", "-X", "POST", "http://localhost:5001/login",
         "-H", "Content-Type: application/json",
         "-d", '{"username":"admin_p3","password":"AdminPass1!"}'],
        capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.lower().startswith("set-cookie:"):
            return line.split(":", 1)[1].strip().split(";")[0]
    return ""


def fetch_overcap_segments(cookie):
    out = subprocess.run(
        ["curl", "-s", "http://localhost:5001/api/files/601db8e1e240/translations",
         "-H", f"Cookie: {cookie}"], capture_output=True, text=True).stdout
    items = json.loads(out).get("translations", [])
    segs = []
    for it in items:
        zh = (it.get("zh_text") or "").strip()
        if len(zh) > CAP:
            has_punct = any(p in zh[:-1] for p in _PUNCT)
            segs.append({"start": float(it["start"]), "end": float(it["end"]),
                         "text": zh, "has_internal_punct": has_punct})
    return segs


def main():
    chars = json.load(open(CHARS))
    print("=" * 78)
    print("P3 — acoustic-gap analysis for over-cap NO-PUNCTUATION segments")
    print("=" * 78)

    cookie = login_cookie()
    overcap = fetch_overcap_segments(cookie)
    no_punct = [s for s in overcap if not s["has_internal_punct"]]
    print(f"\nLive VTDown: {len(overcap)} over-cap(>{CAP}) segments, "
          f"{len(no_punct)} of them have NO internal punctuation (the targets).\n")

    # Global gap distribution (for picking a threshold)
    gaps_all = []
    for a, b in zip(chars, chars[1:]):
        g = float(b.get("start") or 0) - float(a.get("end") or 0)
        if g > 0:
            gaps_all.append(g)
    gaps_all.sort(reverse=True)
    print(f"Global inter-char gaps (681 chars): max {gaps_all[0]:.2f}s, "
          f"top-10 {[round(g,2) for g in gaps_all[:10]]}")
    big = [g for g in gaps_all if g >= 0.30]
    print(f"Gaps >= 0.30s: {len(big)}  | >= 0.50s: {len([g for g in gaps_all if g>=0.5])}\n")

    for s in no_punct:
        seg_chars = [c for c in chars
                     if s["start"] - 0.05 <= float(c.get("start") or 0) <= s["end"] + 0.05]
        print("-" * 78)
        print(f"[{s['start']:.1f}-{s['end']:.1f}s] ({len(s['text'])}字) {s['text']}")
        if not seg_chars:
            print("  (no qwen3 chars matched this window — text may differ from P2 run)")
            continue
        # inter-char gaps within this segment
        ranked = []
        for a, b in zip(seg_chars, seg_chars[1:]):
            g = float(b.get("start") or 0) - float(a.get("end") or 0)
            ranked.append((g, a.get("text", ""), b.get("text", ""),
                           float(a.get("end") or 0)))
        ranked.sort(reverse=True)
        print(f"  chars matched: {len(seg_chars)} | top gaps:")
        for g, at, bt, t in ranked[:4]:
            mark = "  <== SPLIT?" if g >= 0.30 else ""
            print(f"     gap {g:.2f}s @ {t:.2f}s  …{at}|{bt}…{mark}")


if __name__ == "__main__":
    main()
