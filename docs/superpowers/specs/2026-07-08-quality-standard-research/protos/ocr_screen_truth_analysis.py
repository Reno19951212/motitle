#!/usr/bin/env python3
"""Screen-truth re-analysis of the Apple Vision OCR harness results (TASK A).

The raw harness compares OCR output against registry.json cue text. Visual
inspection of zoomed frame crops (frames_evidence/zoom*.png) showed that part
of the registry-vs-OCR disagreement is NOT Vision's fault:

  1. RENDER GLYPH DROPS -- the burnt-in subtitle itself is missing glyphs
     (內/錶/佔/沒/為: blank gaps visible on screen). The render-time font
     (an uploaded custom font, since deleted from assets/fonts/) apparently
     lacked those glyphs. Vision read exactly what is on screen.
  2. GROUND-TRUTH DRIFT -- registry cue text was edited AFTER the 2026-06-17
     render (cue 23: screen shows 「...開始加速。」, registry has 「...開始。」).

This script recomputes CER against manually verified SCREEN text for the 12
visually inspected cues (all cues with nonzero registry-CER were inspected;
exact-match cues need no correction), yielding a vision-only CER that
isolates true OCR error. Run with any python3:

    python3 ocr_screen_truth_analysis.py
"""

import json
import re
import statistics
from pathlib import Path

HERE = Path(__file__).parent
RESULTS = HERE / "ocr_apple_vision_results.json"
OUT = HERE / "ocr_screen_truth_analysis.json"

# Screen text transcribed from zoomed frame crops (frames_evidence/zoomNN.png),
# human/agent visually verified 2026-07-08. Spaces (glyph gaps) stripped later.
# Only cues whose registry CER was nonzero needed inspection.
SCREEN_TRUTH = {
    1:  "好的，起步時，幸運有您領先。",                    # zoom01: matches registry
    3:  "欄位置的 之星河",                                # zoom03: 內+錶 glyphs MISSING on screen
    5:  "留守於第五、六位的是好友心得。",                  # not zoomed; punct-only diff, screen==registry assumed
    7:  "倒數第三、穿紅色賽衣的是翠紅。",                  # not zoomed; punct-only diff, screen==registry assumed
    11: "倒數第二、靠近 欄的是幸運有您。",                # zoom11: 內 glyph MISSING on screen
    19: "倒數第二、穿橙色賽衣的是笑傲江湖",                # zoom19: matches registry
    23: "位於中間位置的信心星開始加速。",                  # zoom23: GT DRIFT (registry edited post-render)
    25: "之星河亦在追趕",                                  # zoom25: 錶 MISSING on screen
    31: "精算暴雪持續衝上",                                # zoom31: matches registry
    33: "之星河仍 先機",                                  # zoom33: 錶+佔 MISSING on screen
    35: "獲勝的馬匹是 之星河",                            # zoom35: 錶 MISSING on screen
    37: "檢視是否有機會奪得沙田銀瓶",                      # zoom37: matches registry
    45: "錯。精算暴雪山來遲，跑過第二；",                  # zoom45: 沒 MISSING on screen
    47: "推進小步亦不可，因步步緊迫，即 精算暴雪。",      # zoom47: 為 MISSING on screen
}

RENDER_GLYPH_DROP_CUES = {3: "內錶", 11: "內", 25: "錶", 33: "錶佔", 35: "錶", 45: "沒", 47: "為"}
GT_DRIFT_CUES = {23: "registry edited post-render (加速 removed)"}

_PUNCT_RE = re.compile(r"[　-〿＀-￯‘-‟.,!?;:'\"()\[\]{}<>…·-]")


def strip_spaces(s: str) -> str:
    return "".join(ch for ch in s if not ch.isspace())


def levenshtein(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def main() -> None:
    data = json.loads(RESULTS.read_text())
    rows = []
    for c in data["cues"]:
        idx = c["cue_idx"]
        ocr = strip_spaces(c["ocr"].replace("\n", ""))
        screen = strip_spaces(SCREEN_TRUTH.get(idx, c["gt"]))
        dist = levenshtein(ocr, screen)
        cer = dist / len(screen) if screen else None
        a2, b2 = _PUNCT_RE.sub("", ocr), _PUNCT_RE.sub("", screen)
        cer_np = levenshtein(a2, b2) / len(b2) if b2 else None
        rows.append(
            {
                "cue_idx": idx,
                "registry_gt": c["gt"],
                "screen_gt": screen,
                "ocr": c["ocr"],
                "registry_cer": c["cer"],
                "vision_cer": round(cer, 4),
                "vision_cer_no_punct": round(cer_np, 4),
                "render_glyph_drop": RENDER_GLYPH_DROP_CUES.get(idx),
                "gt_drift": GT_DRIFT_CUES.get(idx),
                "screen_gt_verified_visually": idx in SCREEN_TRUTH and idx not in (5, 7),
            }
        )

    v = [r["vision_cer"] for r in rows]
    vnp = [r["vision_cer_no_punct"] for r in rows]
    reg = [r["registry_cer"] for r in rows]
    summary = {
        "n_cues": len(rows),
        "registry_cer_mean": round(statistics.mean(reg), 4),
        "vision_cer_mean": round(statistics.mean(v), 4),
        "vision_cer_median": round(statistics.median(v), 4),
        "vision_cer_max": round(max(v), 4),
        "vision_cer_no_punct_mean": round(statistics.mean(vnp), 4),
        "vision_exact_match": sum(1 for x in v if x == 0),
        "vision_exact_match_no_punct": sum(1 for x in vnp if x == 0),
        "cues_with_render_glyph_drops": len(RENDER_GLYPH_DROP_CUES),
        "total_glyphs_dropped_by_render": sum(len(g) for g in RENDER_GLYPH_DROP_CUES.values()),
        "cues_with_gt_drift": len(GT_DRIFT_CUES),
        "note": (
            "vision_cer = OCR vs manually verified on-screen text (12 cues zoomed & "
            "inspected; evidence pngs in frames_evidence/). registry_cer = OCR vs "
            "registry.json cue text, which conflates render glyph drops + post-render "
            "registry edits with true OCR error."
        ),
    }
    OUT.write_text(json.dumps({"summary": summary, "cues": rows}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for r in rows:
        if r["vision_cer"] or r["registry_cer"]:
            print(f"cue {r['cue_idx']:3d}  reg={r['registry_cer']:.3f} vision={r['vision_cer']:.3f}"
                  f"  drop={r['render_glyph_drop'] or '-'}  drift={'Y' if r['gt_drift'] else '-'}")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
