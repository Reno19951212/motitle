"""V6 clause-split — post-refiner Chinese-punctuation segmentation (2026-05-30).

V6 subtitle boundaries come from mlx-whisper acoustic segmentation; continuous
narration (no pauses) yields over-coarse segments spanning several comma-
separated clauses. This module splits an over-long refined segment at Chinese
clause punctuation, assigns proportional timing, and applies a minimum-duration
guard so no sub-second flash line is produced.

Pure + immutable: every function returns new lists/dicts; inputs are never
mutated. Wired into pipeline_runner._run_v6 AFTER the refiner — refined text has
punctuation; qwen3 raw does not (see validation tracker P2).
"""
from __future__ import annotations
import copy
from typing import List, Tuple

DEFAULT_CHAR_CAP = 24
DEFAULT_MIN_DUR = 1.0
# Chinese + ASCII clause-boundary punctuation. Each clause keeps its trailing mark.
_SPLIT_PUNCT = "。！？，、；：!?,;:"


def _atomic_clauses(text: str) -> List[str]:
    """Split text into clauses at _SPLIT_PUNCT; each clause keeps its trailing mark."""
    clauses: List[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in _SPLIT_PUNCT:
            clauses.append(buf)
            buf = ""
    if buf:
        clauses.append(buf)
    return clauses


def _pack_lines(clauses: List[str], char_cap: int) -> List[str]:
    """Greedy: merge consecutive clauses into lines <= char_cap. A single clause
    longer than cap becomes its own line (never broken mid-clause)."""
    lines: List[str] = []
    cur = ""
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


def _proportional_pieces(lines: List[str], start: float, end: float) -> List[dict]:
    """Assign each line a [start,end] slice proportional to its char length."""
    total = sum(len(l) for l in lines) or 1
    span = end - start
    out: List[dict] = []
    acc = 0
    for l in lines:
        s = start + span * (acc / total)
        acc += len(l)
        e = start + span * (acc / total)
        out.append({"start": round(s, 3), "end": round(e, 3), "text": l})
    return out


def _apply_min_dur_guard(pieces: List[dict], min_dur: float) -> List[dict]:
    """Merge any piece shorter than min_dur into a neighbour (forward-merge
    preferred; last piece merges backward). Returns a new list. May exceed
    char_cap after merge — readability beats cap."""
    out = [dict(p) for p in pieces]
    changed = True
    while changed and len(out) > 1:
        changed = False
        for i, p in enumerate(out):
            if (p["end"] - p["start"]) < min_dur:
                if i < len(out) - 1:
                    nxt = out[i + 1]
                    nxt["start"] = p["start"]
                    nxt["text"] = p["text"] + nxt["text"]
                    out.pop(i)
                else:
                    prev = out[i - 1]
                    prev["end"] = p["end"]
                    prev["text"] = prev["text"] + p["text"]
                    out.pop(i)
                changed = True
                break
    return out


def clause_split_segment(seg: dict, char_cap: int = DEFAULT_CHAR_CAP,
                         min_dur: float = DEFAULT_MIN_DUR) -> List[dict]:
    """Split one {start,end,text} segment at Chinese punctuation. Returns a list
    of {start,end,text} pieces (>=1). No split when text <= char_cap or it packs
    to a single line (e.g. one over-cap clause with no internal punctuation).
    Pure — does not mutate seg."""
    text = seg.get("text", "") or ""
    start = float(seg.get("start") or 0.0)
    end = float(seg.get("end") or 0.0)
    if len(text) <= char_cap:
        return [copy.deepcopy(seg)]
    lines = _pack_lines(_atomic_clauses(text), char_cap)
    if len(lines) <= 1:
        return [copy.deepcopy(seg)]
    pieces = _proportional_pieces(lines, start, end)
    return _apply_min_dur_guard(pieces, min_dur)


def split_v6_aligned(source_segs: List[dict], refined_segs: List[dict],
                     char_cap: int = DEFAULT_CHAR_CAP,
                     min_dur: float = DEFAULT_MIN_DUR) -> Tuple[List[dict], List[dict]]:
    """Split refined segments at punctuation, expanding source segments in
    lockstep so persist's index-zip stays aligned (spec 4.2). Split timing lives
    on BOTH source and refined pieces (persist reads start/end from source).
    source_text is sliced proportionally by the same char fractions. Returns
    (new_source, new_refined), index-aligned + equal length. Pure."""
    new_source: List[dict] = []
    new_refined: List[dict] = []
    for i, refined in enumerate(refined_segs):
        src = dict(source_segs[i]) if i < len(source_segs) else {
            "start": refined.get("start") or 0.0, "end": refined.get("end") or 0.0, "text": ""}
        pieces = clause_split_segment(refined, char_cap, min_dur)
        if len(pieces) == 1:
            new_source.append(src)
            new_refined.append(dict(refined))
            continue
        src_text = src.get("text", "") or ""
        total = sum(len(p["text"]) for p in pieces) or 1
        acc = 0
        for p in pieces:
            lo = int(round(len(src_text) * (acc / total)))
            acc += len(p["text"])
            hi = int(round(len(src_text) * (acc / total)))
            sp = dict(src)
            sp["start"] = p["start"]
            sp["end"] = p["end"]
            sp["text"] = src_text[lo:hi]
            new_source.append(sp)
            new_refined.append({
                "start": p["start"], "end": p["end"], "text": p["text"],
                "flags": list(refined.get("flags", []) or []),
            })
    return new_source, new_refined
