"""
Build final comparison report: v4 baseline (single Whisper ASR) vs v5 (dual ASR + verifier + refiner + translator).
"""
import json
from pathlib import Path

V5_COMBINED = Path(__file__).parent / "out" / "v5_combined.json"
OUT = Path(__file__).parent / "out" / "FINAL_COMPARISON.md"


def main():
    data = json.loads(V5_COMBINED.read_text(encoding="utf-8"))

    lines = []
    lines.append("# V5 Prototype Final Comparison\n")
    lines.append(f"## Source: HK racing clip (b9b9e4fad18c.mp4, 261s, 97 Whisper segments)\n")
    lines.append(f"## Pipeline: Whisper + Qwen3-ASR-1.7B → Verifier (LLM-as-judge) → Refiner → Translator\n\n")

    # Key correction cases
    lines.append("## 🎯 Key Corrections (Whisper vs V5 verified)\n\n")
    lines.append("| # | Time | Whisper (single ASR) | V5 Verified | Issue Fixed |\n")
    lines.append("|---|---|---|---|---|\n")

    highlight = [0, 7, 14, 16, 36, 40, 45, 46, 47, 49, 64, 68, 69, 70, 76, 80, 90, 91]
    for d in data:
        if d["idx"] not in highlight:
            continue
        w = d["whisper_text"][:60]
        v = d["verified_text"][:80]
        lines.append(
            f"| {d['idx']} | {d['start']:.1f}-{d['end']:.1f}s | {w} | {v} | |\n"
        )
    lines.append("\n")

    # Full side-by-side
    lines.append("## 📜 Full 97-segment side-by-side\n\n")
    lines.append("Columns: Whisper raw | Qwen3 raw | Verified (canonical) | Refined ZH | Translated EN\n\n")
    for d in data:
        lines.append(f"### #{d['idx']:3d} · {d['start']:6.2f}-{d['end']:6.2f}s · `{d['verifier_method']}`\n")
        lines.append(f"- **Whisper**:  `{d['whisper_text']}`\n")
        lines.append(f"- **Qwen3**:    `{d['qwen_text']}`\n")
        lines.append(f"- **Verified**: `{d['verified_text']}`\n")
        lines.append(f"- **Refined**:  `{d['by_lang']['zh']['text']}`\n")
        lines.append(f"- **EN**:       `{d['by_lang']['en']['text']}`\n\n")

    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"\nSummary:")
    print(f"  Total segments: {len(data)}")
    methods = {}
    for d in data:
        methods[d["verifier_method"]] = methods.get(d["verifier_method"], 0) + 1
    for m, c in sorted(methods.items()):
        print(f"  Verifier method '{m}': {c}")


if __name__ == "__main__":
    main()
