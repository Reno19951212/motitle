#!/usr/bin/env python3
"""Profile alignment Validation Prototype — merge over-merge guard (2026-05-30).

Root cause of the off-by-one: merge_to_sentences groups by time-gap (>1.5s) then
runs an ENGLISH pySBD segmenter on the (here Chinese) source — it can't find
Chinese sentence enders, so a run of ~13 short pause-less fragments merges into
ONE giant "sentence". The LLM marker alignment then fails → time-proportion
fallback misdistributes → off-by-one.

Validate two guards on the REAL 104 ASR segments (no LLM):
  G1: cap merged-sentence segment count at N (post-merge split).
  G2: also split each merged group at Chinese sentence-enders (。！？) present
      in the source text.
Check: (a) the monster (segs ~6-19) is broken up, (b) the legitimate early
sentences (segs 0-5) stay reasonably merged.

Run from backend/: python3 scripts/profile_prototype/p_merge_guard.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))  # backend/ on path

from translation.sentence_pipeline import merge_to_sentences  # noqa: E402

ASR = os.path.join(HERE, "out", "asr_segments.json")
_ZH_END = "。！？!?"


def load_segs():
    d = json.load(open(ASR))
    segs = d if isinstance(d, list) else d.get("segments", [])
    return [{"start": float(s["start"]), "end": float(s["end"]), "text": s["text"]} for s in segs]


def cap_split(merged, segs, cap):
    """G1: split any merged sentence spanning > cap segments into <=cap chunks."""
    out = []
    for m in merged:
        idx = m["seg_indices"]
        if len(idx) <= cap:
            out.append(idx)
        else:
            for i in range(0, len(idx), cap):
                out.append(idx[i:i + cap])
    return out


def show(label, groups, segs):
    multi = [g for g in groups if len(g) > 1]
    sizes = [len(g) for g in groups]
    print(f"\n{label}: {len(groups)} sentences | multi-seg {len(multi)} | max span {max(sizes)} segs")
    big = [g for g in groups if len(g) >= 5]
    for g in big:
        txt = "".join(segs[i]["text"] for i in g)
        print(f"   ⚠ {len(g)}-seg span [{g[0]}..{g[-1]}]: {txt[:60]}")


def main():
    segs = load_segs()
    print("=" * 78)
    print(f"MERGE GUARD VALIDATION — {len(segs)} real ASR segments (zh source)")
    print("=" * 78)

    merged = merge_to_sentences(segs)
    cur_groups = [m["seg_indices"] for m in merged]
    show("CURRENT (English pySBD)", cur_groups, segs)
    # Show the monster's per-segment breakdown
    monster = max(merged, key=lambda m: len(m["seg_indices"]))
    print(f"\n   biggest merged sentence spans {len(monster['seg_indices'])} segments:")
    for i in monster["seg_indices"]:
        print(f"      seg {i:3d} [{segs[i]['start']:.1f}-{segs[i]['end']:.1f}s] {segs[i]['text']}")

    for cap in (3, 4, 5):
        show(f"G1 cap={cap}", cap_split(merged, segs, cap), segs)


if __name__ == "__main__":
    main()
