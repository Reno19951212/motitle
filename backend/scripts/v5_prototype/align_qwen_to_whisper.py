"""
Align Qwen3-ASR word-level output to Whisper 97-segment time anchors.

Strategy:
  For each Whisper segment [w_start, w_end]:
    Collect all Qwen3 words whose midpoint falls within [w_start, w_end].
    Concatenate into one string (no spaces — Chinese).

Output: list of {idx, start, end, whisper_text, qwen_text}
        — ready for verifier consumption.

Also handles s2hk simplified→traditional Hong Kong conversion on Qwen3 output.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

try:
    from opencc import OpenCC
    _cc = OpenCC("s2hk")
    def s2hk(s: str) -> str:
        return _cc.convert(s)
except ImportError:
    def s2hk(s: str) -> str:
        return s


REGISTRY_PATH = Path(__file__).resolve().parents[3] / "backend" / "data" / "registry.json"
QWEN_JSON = Path(__file__).parent / "out" / "qwen3_full.json"
OUT = Path(__file__).parent / "out" / "aligned.json"


def load_whisper_segments(fid: str) -> list[dict]:
    with open(REGISTRY_PATH) as f:
        reg = json.load(f)
    return [
        {"idx": i, "start": s["start"], "end": s["end"], "text": s.get("text", "")}
        for i, s in enumerate(reg[fid]["segments"])
    ]


def collect_qwen_text_for_range(words: list[dict], start: float, end: float) -> str:
    """Collect Qwen3 words whose midpoint falls within [start, end]."""
    out = []
    for w in words:
        ws = w.get("start")
        we = w.get("end")
        if ws is None or we is None:
            continue
        mid = (ws + we) / 2
        if start <= mid < end:
            out.append(w.get("text", ""))
    return "".join(out)


def main():
    fid = "b9b9e4fad18c"
    whisper_segs = load_whisper_segments(fid)
    print(f"Loaded {len(whisper_segs)} Whisper segments")

    qwen_data = json.loads(QWEN_JSON.read_text(encoding="utf-8"))
    qwen_words = qwen_data["words"]
    print(f"Loaded {len(qwen_words)} Qwen3 word-level segments")
    print(f"Qwen3 language: {qwen_data['language']}")

    # Pre-extension: handle Whisper "ghost segments" where Whisper missed content
    # For each Whisper segment, collect Qwen3 text within its time range.
    aligned = []
    for ws in whisper_segs:
        q_text_simp = collect_qwen_text_for_range(qwen_words, ws["start"], ws["end"])
        q_text = s2hk(q_text_simp)
        aligned.append({
            "idx": ws["idx"],
            "start": ws["start"],
            "end": ws["end"],
            "whisper_text": ws["text"],
            "qwen_text": q_text,
            "qwen_text_simplified": q_text_simp,
        })

    # Diagnostics
    print()
    print("=== Whisper-Qwen alignment diagnostics ===")
    print(f"Segments where Whisper EMPTY but Qwen has text: ", end="")
    empty_whisper_filled_qwen = sum(
        1 for a in aligned
        if not a["whisper_text"].strip() and a["qwen_text"].strip()
    )
    print(empty_whisper_filled_qwen)

    print(f"Segments where Qwen EMPTY but Whisper has text: ", end="")
    empty_qwen_filled_whisper = sum(
        1 for a in aligned
        if a["whisper_text"].strip() and not a["qwen_text"].strip()
    )
    print(empty_qwen_filled_whisper)

    print(f"Segments where BOTH have text: ", end="")
    both = sum(
        1 for a in aligned
        if a["whisper_text"].strip() and a["qwen_text"].strip()
    )
    print(both)

    # Show first 5 + segments where they DIFFER notably
    print()
    print("=== First 5 aligned segments ===")
    for a in aligned[:5]:
        print(f"  #{a['idx']:2d} {a['start']:6.2f}-{a['end']:6.2f}")
        print(f"    Whisper: {a['whisper_text']}")
        print(f"    Qwen3:   {a['qwen_text']}")

    OUT.write_text(json.dumps(aligned, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(Path.cwd()) if str(Path.cwd()) in str(OUT) else OUT}")


if __name__ == "__main__":
    main()
