"""
Side-by-side comparison: v4 raw ZH vs v5 polished ZH vs v5 translated EN.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--json", default=str(Path(__file__).parent / "out" / "prototype_output.json"),
    )
    p.add_argument("--n", type=int, default=20, help="how many segments to show")
    p.add_argument("--start", type=int, default=0, help="start segment idx")
    args = p.parse_args()

    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    segs = data["segments"]
    print(f"# v5 Prototype side-by-side ({len(segs)} segments total)\n")
    print(f"Source lang: {data.get('source_lang')}")
    print(f"FID: {data.get('fid')}\n")

    end = min(len(segs), args.start + args.n)
    halluc_count = 0
    for s in segs[args.start : end]:
        zh_raw = s["source_text"]
        by = s.get("by_lang", {})
        zh_pol = by.get("zh", {}).get("text", "")
        en = by.get("en", {}).get("text", "")
        is_halluc = "[HALLUC]" in zh_pol
        if is_halluc:
            halluc_count += 1
        marker = " ⚠️" if is_halluc else ""
        print(f"--- #{s['idx']:3d}  {s['start']:6.2f}-{s['end']:6.2f}s{marker}")
        print(f"  v4 raw ZH:  {zh_raw}")
        print(f"  v5 pol ZH:  {zh_pol}")
        if en:
            print(f"  v5 xlat EN: {en}")
        print()

    print(f"\n=== Summary (first {end - args.start} segments) ===")
    print(f"  Hallucination flagged: {halluc_count}")
    # Overall stats
    all_pol = [s["by_lang"].get("zh", {}).get("text", "") for s in segs]
    all_en = [s["by_lang"].get("en", {}).get("text", "") for s in segs]
    halluc_all = sum(1 for t in all_pol if "[HALLUC]" in t)
    empty_zh = sum(1 for t in all_pol if not t.strip())
    empty_en = sum(1 for t in all_en if not t.strip())
    print(f"  Total segments: {len(segs)}")
    print(f"  ZH polished empty:    {empty_zh}/{len(segs)}")
    print(f"  EN translated empty:  {empty_en}/{len(segs)}")
    print(f"  ZH [HALLUC] flagged:  {halluc_all}/{len(segs)}")


if __name__ == "__main__":
    main()
