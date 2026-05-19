"""
End-to-end V5 prototype: dual-ASR + Verifier + Refiner + Translator.

Reads: out/verified.json
Outputs:
  out/v5_polished_zh.srt   — final Cantonese (verified + refined)
  out/v5_translated_en.srt — English translation
  out/v5_combined.json     — per-segment by_lang dict
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from llm_engine import LLMConfig, LLMEngine
from refiner import RefinerEngine
from translator import Segment, TranslatorEngine


VERIFIED_JSON = Path(__file__).parent / "out" / "verified.json"
OUT_DIR = Path(__file__).parent / "out"


def fmt_srt_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segs: list[Segment], path: Path) -> None:
    lines = []
    for i, seg in enumerate(segs, start=1):
        txt = seg.text or "(略)"
        lines.append(str(i))
        lines.append(f"{fmt_srt_time(seg.start)} --> {fmt_srt_time(seg.end)}")
        lines.append(txt)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def progress_cb(label: str):
    def cb(idx: int, total: int, text: str):
        preview = (text[:60] + "…") if len(text) > 60 else text
        print(f"  {label} [{idx:3d}/{total}] {preview}", flush=True)
    return cb


def main():
    verified = json.loads(VERIFIED_JSON.read_text(encoding="utf-8"))
    print(f"Loaded {len(verified)} verified segments")

    # Build Segments from verified text (skip [EMPTY] / [HALLUC] markers)
    verified_segs = [
        Segment(
            start=v["start"],
            end=v["end"],
            text="" if v["verified_text"] in ("[EMPTY]", "[HALLUC]") else v["verified_text"],
        )
        for v in verified
    ]

    llm = LLMEngine(LLMConfig())

    # Phase 1: Refiner (light-touch, since verifier already polished)
    print("\n=== Phase 1: Refiner (light-touch polish) ===")
    t0 = time.time()
    refiner = RefinerEngine(llm, lang="zh", style="broadcast-hk")
    refined_segs = refiner.refine_segments(verified_segs, progress=progress_cb("refine"))
    t_refine = time.time() - t0
    write_srt(refined_segs, OUT_DIR / "v5_polished_zh.srt")
    print(f"  refiner done in {t_refine:.1f}s")

    # Phase 2: Translator (ZH → EN)
    print("\n=== Phase 2: Translator (ZH → EN) ===")
    t0 = time.time()
    translator = TranslatorEngine(llm, source_lang="zh", target_lang="en")
    translated_segs = translator.translate_segments(refined_segs, progress=progress_cb("xlate "))
    t_xlate = time.time() - t0
    write_srt(translated_segs, OUT_DIR / "v5_translated_en.srt")
    print(f"  translator done in {t_xlate:.1f}s")

    # Combined output
    combined = []
    for i, v in enumerate(verified):
        combined.append({
            "idx": v["idx"],
            "start": v["start"],
            "end": v["end"],
            "whisper_text": v["whisper_text"],
            "qwen_text": v["qwen_text"],
            "verified_text": v["verified_text"],
            "verifier_method": v["method"],
            "by_lang": {
                "zh": {
                    "text": refined_segs[i].text,
                    "stage": "refined",
                },
                "en": {
                    "text": translated_segs[i].text,
                    "stage": "translated",
                },
            },
        })

    (OUT_DIR / "v5_combined.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nCombined JSON: {OUT_DIR / 'v5_combined.json'}")
    print(f"Polished ZH:   {OUT_DIR / 'v5_polished_zh.srt'}")
    print(f"Translated EN: {OUT_DIR / 'v5_translated_en.srt'}")


if __name__ == "__main__":
    main()
