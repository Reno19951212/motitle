"""
Run ASR Verifier (LLM-as-judge) over aligned segments.
Output verified canonical Cantonese segments → fed downstream to Refiner.

Reads:  out/aligned.json
Writes: out/verified.json
        out/verified.srt
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from llm_engine import LLMConfig, LLMEngine
from verifier_prompt import VERIFIER_SYSTEM


ALIGNED_JSON = Path(__file__).parent / "out" / "aligned.json"
OUT_JSON = Path(__file__).parent / "out" / "verified.json"
OUT_SRT = Path(__file__).parent / "out" / "verified.srt"


def fmt_srt_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    aligned = json.loads(ALIGNED_JSON.read_text(encoding="utf-8"))
    print(f"Loaded {len(aligned)} aligned segments")

    llm = LLMEngine(LLMConfig())  # think:false default
    verified = []
    n = len(aligned)
    t0 = time.time()

    for i, a in enumerate(aligned):
        wt = (a["whisper_text"] or "").strip()
        qt = (a["qwen_text"] or "").strip()

        # Pre-filter: if both identical (or near-identical) → skip LLM, use Qwen3 (better Cantonese)
        if wt == qt and wt:
            decision = qt
            method = "AGREE"
        elif not wt and not qt:
            decision = "[EMPTY]"
            method = "BOTH_EMPTY"
        elif not wt:
            decision = qt
            method = "QWEN_ONLY"
        elif not qt:
            decision = wt
            method = "WHISPER_ONLY"
        else:
            user_prompt = (
                f"時間: {a['start']:.2f}-{a['end']:.2f}s\n"
                f"Whisper: {wt}\n"
                f"Qwen3:   {qt}"
            )
            result = llm.call(VERIFIER_SYSTEM, user_prompt)
            # Defensive cleanup
            for prefix in ("輸出:", "輸出：", "結果:", "結果："):
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
        print(f"  [{i+1:3d}/{n}] {method:13s} {a['start']:6.2f}s  {preview}", flush=True)

    elapsed = time.time() - t0
    print(f"\nVerifier done in {elapsed:.1f}s")

    # Stats
    methods = {}
    for v in verified:
        methods[v["method"]] = methods.get(v["method"], 0) + 1
    print("\n=== Method counts ===")
    for m, c in sorted(methods.items()):
        print(f"  {m}: {c}")

    OUT_JSON.write_text(json.dumps(verified, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_JSON.name}")

    # SRT output — using verified text
    srt_lines = []
    for i, v in enumerate(verified, start=1):
        txt = v["verified_text"]
        if txt in ("[EMPTY]", "[HALLUC]"):
            txt = "(略)"
        srt_lines.append(str(i))
        srt_lines.append(f"{fmt_srt_time(v['start'])} --> {fmt_srt_time(v['end'])}")
        srt_lines.append(txt)
        srt_lines.append("")
    OUT_SRT.write_text("\n".join(srt_lines), encoding="utf-8")
    print(f"Wrote {OUT_SRT.name}")


if __name__ == "__main__":
    main()
