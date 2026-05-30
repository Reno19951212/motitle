#!/usr/bin/env python3
"""V6 segmentation Validation-First Prototype 1 (2026-05-30).

Goal: validate that a DETERMINISTIC punctuation-aware split of the over-coarse
V6 subtitle segments improves segmentation on the VTDown file WITHOUT harming
the already-good 賽馬 file. Operates on PERSISTED refined ZH text only — no ASR
re-run, no LLM. Timing here is proportional-by-char (Prototype 2 will validate
Qwen3 real-timestamp timing; P1 only judges the SEGMENTATION quality).

Algorithm (clause-packing):
  1. Split a segment's refined ZH into atomic clauses at clause-boundary
     punctuation (。！？，、；) — each clause keeps its trailing punctuation.
  2. Greedily re-pack consecutive clauses into lines so each line <= char_cap.
     A single clause longer than cap stays whole (we never break mid-clause
     without punctuation — preserves meaning; cite: jieba word-split REJECTED).
  3. Timing: each output line gets a [start,end] slice proportional to its
     char length within the original segment span (P1 approximation).

Run: python3 backend/scripts/v6_prototype/p1_punctuation_split.py
"""
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "seg_data")

# Clause-boundary punctuation. Sentence-enders + clause separators.
_SENTENCE_END = "。！？!?"
_CLAUSE_SEP = "，、；：,;:"
_SPLIT_PUNCT = _SENTENCE_END + _CLAUSE_SEP


def load(name):
    d = json.load(open(os.path.join(DATA, f"{name}.json")))
    items = d if isinstance(d, list) else (d.get("translations") or d.get("segments") or [])
    segs = []
    for it in items:
        zh = (it.get("zh_text") or (it.get("by_lang", {}).get("zh", {}) or {}).get("text") or "").strip()
        segs.append({"start": float(it["start"]), "end": float(it["end"]), "text": zh})
    return segs


def atomic_clauses(text):
    """Split text into clauses; each clause keeps its trailing split punctuation."""
    clauses, buf = [], ""
    for ch in text:
        buf += ch
        if ch in _SPLIT_PUNCT:
            clauses.append(buf)
            buf = ""
    if buf:
        clauses.append(buf)
    return clauses


def pack_lines(clauses, char_cap):
    """Greedy: merge consecutive clauses into lines <= char_cap.
    A single clause > cap becomes its own line (never broken mid-clause)."""
    lines, cur = [], ""
    for c in clauses:
        if not cur:
            cur = c
        elif len(cur) + len(c) <= char_cap:
            cur += c
        else:
            lines.append(cur)
            cur = c
    if cur:
        lines.append(cur)
    return lines


def split_segment(seg, char_cap):
    """Return list of sub-segments. No split if text already <= cap."""
    text = seg["text"]
    if len(text) <= char_cap:
        return [dict(seg)]
    lines = pack_lines(atomic_clauses(text), char_cap)
    if len(lines) <= 1:
        return [dict(seg)]  # single over-cap clause, can't split safely
    # proportional timing by char length
    total_chars = sum(len(l) for l in lines)
    span = seg["end"] - seg["start"]
    out, acc = [], 0
    for i, l in enumerate(lines):
        s = seg["start"] + span * (acc / total_chars)
        acc += len(l)
        e = seg["start"] + span * (acc / total_chars)
        out.append({"start": round(s, 3), "end": round(e, 3), "text": l})
    return out


def apply_split(segs, char_cap):
    out = []
    for s in segs:
        out.extend(split_segment(s, char_cap))
    return out


def has_internal_punct(text):
    return any(p in text[:-1] for p in _SPLIT_PUNCT)


def stats(segs, char_cap):
    lens = [len(s["text"]) for s in segs if s["text"]]
    durs = [s["end"] - s["start"] for s in segs]
    return {
        "count": len(segs),
        "char_min": min(lens) if lens else 0,
        "char_median": round(statistics.median(lens), 1) if lens else 0,
        "char_max": max(lens) if lens else 0,
        "over_cap": sum(1 for l in lens if l > char_cap),
        "internal_comma": sum(1 for s in segs if has_internal_punct(s["text"])),
        "tiny_frag_lt4": sum(1 for l in lens if l < 4),
        "dur_max": round(max(durs), 1) if durs else 0,
        "dur_median": round(statistics.median(durs), 2) if durs else 0,
    }


def main():
    vt = load("vtdown")
    sm = load("saima")
    print("=" * 78)
    print("V6 SEGMENTATION PROTOTYPE 1 — deterministic punctuation clause-packing")
    print("=" * 78)
    for cap in (16, 18, 20, 24, 28):
        print(f"\n────── char_cap = {cap} ──────")
        for name, segs in (("VTDown (problem)", vt), ("賽馬   (good)", sm)):
            before = stats(segs, cap)
            after_segs = apply_split(segs, cap)
            after = stats(after_segs, cap)
            churn = sum(1 for s in segs if len(split_segment(s, cap)) > 1)
            print(f"  {name}:")
            print(f"    before: {before['count']} segs | char med {before['char_median']} max {before['char_max']} | >cap {before['over_cap']} | internal-punct {before['internal_comma']} | dur max {before['dur_max']}s")
            print(f"    after : {after['count']} segs | char med {after['char_median']} max {after['char_max']} | >cap {after['over_cap']} | internal-punct {after['internal_comma']} | tiny(<4) {after['tiny_frag_lt4']} | dur max {after['dur_max']}s")
            print(f"    churn : {churn}/{len(segs)} segments were split")

    # Concrete VTDown before->after at the recommended cap
    CAP = 20
    print("\n" + "=" * 78)
    print(f"VTDown worst segments  before → after  (char_cap={CAP})")
    print("=" * 78)
    worst = sorted(vt, key=lambda s: len(s["text"]), reverse=True)[:6]
    for s in worst:
        pieces = split_segment(s, CAP)
        print(f"\n  [{s['start']:.1f}-{s['end']:.1f}s] ({len(s['text'])}字) {s['text']}")
        if len(pieces) > 1:
            for p in pieces:
                print(f"      → [{p['start']:.1f}-{p['end']:.1f}s] ({len(p['text'])}字) {p['text']}")
        else:
            print("      → (unchanged)")


if __name__ == "__main__":
    main()
