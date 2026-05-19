"""
V5 Prototype Runner — HK racing clip (b9b9e4fad18c).

Loads existing v4 ZH segments from registry, then:
  1. RefinerEngine (zh-broadcast-hk) → polished ZH
  2. TranslatorEngine (zh→en)        → English subtitle (NEW capability)

Outputs:
  - prototype_output.json (segments with by_lang dict)
  - prototype_polished.srt (refined ZH)
  - prototype_translated.srt (translated EN)
  - v4_baseline.srt (raw v4 ZH for side-by-side compare)

Usage (from repo root):
  cd backend/scripts/v5_prototype
  python run_prototype.py --fid b9b9e4fad18c --output-dir ./out
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from llm_engine import LLMConfig, LLMEngine
from refiner import RefinerEngine
from translator import Segment, TranslatorEngine


REGISTRY_PATH = Path(__file__).resolve().parents[3] / "backend" / "data" / "registry.json"


def load_segments(fid: str) -> tuple[list[Segment], dict]:
    with open(REGISTRY_PATH) as f:
        reg = json.load(f)
    if fid not in reg:
        raise SystemExit(f"file id {fid} not found in registry")
    e = reg[fid]
    raw_segs = e.get("segments") or []
    if not raw_segs:
        raise SystemExit(f"file {fid} has 0 segments — cannot prototype")
    segs = [Segment(s["start"], s["end"], s.get("text", "")) for s in raw_segs]
    return segs, {"name": e.get("original_name"), "fid": fid}


def fmt_srt_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segs: list[Segment], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for i, seg in enumerate(segs, start=1):
        lines.append(str(i))
        lines.append(f"{fmt_srt_time(seg.start)} --> {fmt_srt_time(seg.end)}")
        lines.append(seg.text or "")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def progress_cb(label: str):
    def cb(idx: int, total: int, text: str):
        bar = f"[{idx:3d}/{total}]"
        preview = (text[:60] + "…") if len(text) > 60 else text
        print(f"  {label} {bar} {preview}", flush=True)
    return cb


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fid", default="b9b9e4fad18c", help="file id in registry")
    p.add_argument(
        "--output-dir",
        default=str(Path(__file__).parent / "out"),
        help="output dir",
    )
    p.add_argument(
        "--limit", type=int, default=0,
        help="limit segment count for fast iteration (0 = all)",
    )
    p.add_argument(
        "--skip-translate", action="store_true",
        help="skip ZH→EN translator stage (test refiner only)",
    )
    p.add_argument(
        "--skip-refine", action="store_true",
        help="skip ZH refiner stage (test translator only)",
    )
    p.add_argument(
        "--model", default="qwen3.5:35b-a3b-mlx-bf16",
        help="Ollama model name",
    )
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"V5 Prototype — file {args.fid}", flush=True)
    print(f"  output: {out_dir}", flush=True)
    print(f"  model:  {args.model}", flush=True)

    segs, meta = load_segments(args.fid)
    if args.limit > 0:
        segs = segs[: args.limit]
    print(f"  loaded {len(segs)} segments ({meta['name'][:60]}…)", flush=True)

    write_srt(segs, out_dir / "v4_baseline_raw_zh.srt")
    print(f"  baseline SRT written: v4_baseline_raw_zh.srt", flush=True)

    llm = LLMEngine(LLMConfig(model=args.model))

    refined_segs: list[Segment] = segs
    if not args.skip_refine:
        print("\n=== Phase 1: Refiner (ZH broadcast register cleanup) ===", flush=True)
        t0 = time.time()
        refiner = RefinerEngine(llm, lang="zh", style="broadcast-hk")
        refined_segs = refiner.refine_segments(segs, progress=progress_cb("refine"))
        t_refine = time.time() - t0
        write_srt(refined_segs, out_dir / "prototype_polished_zh.srt")
        print(f"  refiner done in {t_refine:.1f}s — wrote prototype_polished_zh.srt", flush=True)
    else:
        print("\n=== Phase 1: Refiner SKIPPED ===", flush=True)

    if not args.skip_translate:
        print("\n=== Phase 2: Translator (ZH → EN) ===", flush=True)
        t0 = time.time()
        translator = TranslatorEngine(llm, source_lang="zh", target_lang="en")
        # Translator takes the REFINED ZH as input (better source quality)
        translated_segs = translator.translate_segments(
            refined_segs, progress=progress_cb("xlate "),
        )
        t_translate = time.time() - t0
        write_srt(translated_segs, out_dir / "prototype_translated_en.srt")
        print(f"  translator done in {t_translate:.1f}s — wrote prototype_translated_en.srt", flush=True)
    else:
        print("\n=== Phase 2: Translator SKIPPED ===", flush=True)
        translated_segs = []

    # Combined JSON (v5 schema preview)
    combined = {
        "fid": args.fid,
        "source_lang": "zh",
        "segments": [
            {
                "idx": i,
                "start": segs[i].start,
                "end": segs[i].end,
                "source_text": segs[i].text,
                "by_lang": {
                    "zh": {"text": refined_segs[i].text if not args.skip_refine else segs[i].text,
                            "stage": "refined" if not args.skip_refine else "raw"},
                    **(
                        {"en": {"text": translated_segs[i].text, "stage": "translated"}}
                        if not args.skip_translate else {}
                    ),
                },
            }
            for i in range(len(segs))
        ],
    }
    (out_dir / "prototype_output.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"\n  combined output written: prototype_output.json", flush=True)
    print("\nDone. Compare files in:", out_dir, flush=True)


if __name__ == "__main__":
    main()
