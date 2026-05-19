"""
Winning Factor (EN source) end-to-end v5 prototype.

Pipeline:
  Whisper EN + Qwen3-ASR EN  →  Alignment  →  ASR Verifier (EN judge)
   →  Translator EN→ZH (HK Cantonese broadcast)

Reads:  out_winfactor/whisper.json + out_winfactor/qwen.json
Writes: out_winfactor/aligned.json
        out_winfactor/verified.json + .srt   (English canonical)
        out_winfactor/translated_zh.srt      (HK Cantonese subtitle)
        out_winfactor/combined.json
        out_winfactor/FINAL_COMPARISON.md
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from llm_engine import LLMConfig, LLMEngine
from translator import Segment
from prompts import TRANSLATOR_EN_TO_ZH_HK, ASR_VERIFIER_EN


OUT = Path(__file__).parent / "out_winfactor"
WHISPER_JSON = OUT / "whisper.json"
QWEN_JSON = OUT / "qwen.json"


def fmt_srt_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segs: list[Segment], path: Path) -> None:
    lines = []
    for i, seg in enumerate(segs, start=1):
        txt = (seg.text or "(略)").strip()
        lines.append(str(i))
        lines.append(f"{fmt_srt_time(seg.start)} --> {fmt_srt_time(seg.end)}")
        lines.append(txt or "(略)")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def collect_qwen_text_for_range(words: list[dict], start: float, end: float) -> str:
    """Collect Qwen3 word tokens whose midpoint falls within [start, end].
    For English: insert space between tokens.
    """
    out = []
    for w in words:
        ws = w.get("start")
        we = w.get("end")
        if ws is None or we is None:
            continue
        mid = (ws + we) / 2
        if start <= mid < end:
            out.append(w.get("text", ""))
    # English: re-join with spaces, then squeeze multiples
    s = "".join(out)
    # If tokens look space-separated already (English), keep as-is; else join with space
    import re
    s = re.sub(r"\s+", " ", s).strip()
    return s


def main():
    whisper = json.loads(WHISPER_JSON.read_text(encoding="utf-8"))
    qwen = json.loads(QWEN_JSON.read_text(encoding="utf-8"))

    w_segs = whisper["segments"]
    q_words = qwen["words"]

    print(f"Whisper: {len(w_segs)} segments  (lang: {whisper.get('language')})")
    print(f"Qwen3:   {len(q_words)} word tokens  (lang: {qwen.get('language')})")
    print()

    # Phase 1: Align
    print("=== Phase 1: Alignment ===")
    aligned = []
    for i, ws in enumerate(w_segs):
        q_text = collect_qwen_text_for_range(q_words, ws["start"], ws["end"])
        aligned.append({
            "idx": i,
            "start": ws["start"],
            "end": ws["end"],
            "whisper_text": ws["text"].strip(),
            "qwen_text": q_text,
        })
    (OUT / "aligned.json").write_text(json.dumps(aligned, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote aligned.json ({len(aligned)} segments)")

    # Phase 2: Verifier (EN judge)
    print("\n=== Phase 2: ASR Verifier (EN-vs-EN LLM judge) ===")
    llm = LLMEngine(LLMConfig())
    verified = []
    t0 = time.time()

    for i, a in enumerate(aligned):
        wt = a["whisper_text"]
        qt = a["qwen_text"]
        if wt == qt and wt:
            decision, method = qt, "AGREE"
        elif not wt and not qt:
            decision, method = "[EMPTY]", "BOTH_EMPTY"
        elif not wt:
            decision, method = qt, "QWEN_ONLY"
        elif not qt:
            decision, method = wt, "WHISPER_ONLY"
        else:
            user_prompt = (
                f"Time: {a['start']:.2f}-{a['end']:.2f}s\n"
                f"Whisper: {wt}\n"
                f"Qwen3:   {qt}"
            )
            result = llm.call(ASR_VERIFIER_EN, user_prompt)
            for prefix in ("Output:", "Result:"):
                if result.startswith(prefix):
                    result = result[len(prefix):].strip()
            decision = result.splitlines()[0].strip() if result else "[EMPTY]"
            method = "LLM_JUDGE"

        verified.append({
            "idx": a["idx"],
            "start": a["start"],
            "end": a["end"],
            "whisper_text": wt,
            "qwen_text": qt,
            "verified_text": decision,
            "method": method,
        })
        preview = (decision[:60] + "…") if len(decision) > 60 else decision
        print(f"  [{i+1:3d}/{len(aligned)}] {method:13s} {a['start']:6.2f}s  {preview}", flush=True)

    t_verify = time.time() - t0
    print(f"  verifier done in {t_verify:.1f}s")

    (OUT / "verified.json").write_text(json.dumps(verified, ensure_ascii=False, indent=2), encoding="utf-8")
    verified_segs = [
        Segment(v["start"], v["end"], "" if v["verified_text"] in ("[EMPTY]", "[HALLUC]") else v["verified_text"])
        for v in verified
    ]
    write_srt(verified_segs, OUT / "verified.srt")

    # Phase 3: Translator EN → ZH (HK Cantonese broadcast)
    print("\n=== Phase 3: Translator EN → ZH (HK Cantonese broadcast) ===")
    t0 = time.time()
    translated_segs: list[Segment] = []
    n = len(verified_segs)
    for i, seg in enumerate(verified_segs):
        src = (seg.text or "").strip()
        if not src:
            translated_segs.append(Segment(seg.start, seg.end, "[略]"))
            preview = "[略]"
        else:
            result = llm.call(TRANSLATOR_EN_TO_ZH_HK, src)
            for prefix in ("ZH:", "中文:", "Translation:"):
                if result.startswith(prefix):
                    result = result[len(prefix):].strip()
            first_line = next((ln for ln in result.splitlines() if ln.strip()), "[略]")
            translated_segs.append(Segment(seg.start, seg.end, first_line))
            preview = (first_line[:60] + "…") if len(first_line) > 60 else first_line
        print(f"  xlate [{i+1:3d}/{n}] {seg.start:6.2f}s  {preview}", flush=True)

    t_xlate = time.time() - t0
    print(f"  translator done in {t_xlate:.1f}s")
    write_srt(translated_segs, OUT / "translated_zh.srt")

    # Combined JSON
    combined = []
    for i, v in enumerate(verified):
        combined.append({
            "idx": v["idx"],
            "start": v["start"],
            "end": v["end"],
            "whisper_en": v["whisper_text"],
            "qwen_en": v["qwen_text"],
            "verified_en": v["verified_text"],
            "verifier_method": v["method"],
            "translated_zh": translated_segs[i].text,
        })
    (OUT / "combined.json").write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")

    # Stats
    methods = {}
    for v in verified:
        methods[v["method"]] = methods.get(v["method"], 0) + 1
    print("\n=== Method counts ===")
    for m, c in sorted(methods.items()):
        print(f"  {m}: {c}")
    print(f"\nWrote: verified.json + .srt, translated_zh.srt, combined.json")
    print(f"Total LLM time: verifier {t_verify:.1f}s + xlate {t_xlate:.1f}s")


if __name__ == "__main__":
    main()
