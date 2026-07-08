#!/usr/bin/env python3
"""Task C (b) CHANGE DETECTION — frame-diff on the subtitle band.

Loads the downscaled band crops (960x135), computes two diff signals
between consecutive frames:

  raw    : mean abs grayscale diff (fires on any background motion)
  mask   : XOR of bright-pixel masks (luma >= BRIGHT_T) normalized by the
           union — targets the subtitle fill (white/yellow), ignores the
           moving mid-gray background

Groups frames into stable runs; one OCR call per run (representative =
middle frame). Reports how many OCR calls that saves vs OCR-every-frame.

Usage: python 02_change_detect.py <small_band_dir> <fps> <out_json> [rows lo:hi]
  rows lo:hi — optional row slice within the band image (tight subtitle band);
  e.g. "99:135" on the 960x135 small band = y 1008..1080 of the 1080p frame.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

BRIGHT_T = 200          # luma threshold for subtitle fill pixels
MIN_MASK_PX = 40        # below this the band is considered "no text"
CHANGE_FRAC = 0.25      # XOR/union fraction above which the text changed


def load_gray(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("L"), dtype=np.uint8)


def main() -> None:
    band_dir, fps, out_json = Path(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
    rows = slice(None)
    if len(sys.argv) > 4:
        lo, hi = sys.argv[4].split(":")
        rows = slice(int(lo), int(hi))
    files = sorted(band_dir.glob("*.png"))
    n = len(files)
    dt = 1.0 / fps
    grays = [load_gray(f)[rows, :] for f in files]
    masks = [g >= BRIGHT_T for g in grays]

    raw_diffs, mask_changes, mask_px = [], [], [int(m.sum()) for m in masks]
    for i in range(1, n):
        raw_diffs.append(float(np.abs(grays[i].astype(np.int16) - grays[i - 1].astype(np.int16)).mean()))
        xor = int((masks[i] ^ masks[i - 1]).sum())
        union = int((masks[i] | masks[i - 1]).sum())
        mask_changes.append(xor / union if union else 0.0)

    # --- segmentation into stable runs using the mask signal ---
    runs = []  # each: {first_idx, last_idx, has_text}
    cur = {"first": 0, "last": 0, "has_text": mask_px[0] >= MIN_MASK_PX}
    for i in range(1, n):
        has_text = mask_px[i] >= MIN_MASK_PX
        changed = (mask_changes[i - 1] > CHANGE_FRAC) or (has_text != cur["has_text"])
        if changed:
            runs.append(cur)
            cur = {"first": i, "last": i, "has_text": has_text}
        else:
            cur["last"] = i
    runs.append(cur)

    text_runs = [r for r in runs if r["has_text"]]
    for r in runs:
        mid = (r["first"] + r["last"]) // 2
        r.update(
            t_first=round(r["first"] * dt, 3),
            t_last=round(r["last"] * dt, 3),
            rep_idx=mid,
            rep_file=files[mid].name,
        )

    # raw-diff baseline: how many events would a naive raw-pixel diff fire?
    raw_arr = np.array(raw_diffs)
    raw_events_at = {str(t): int((raw_arr > t).sum()) for t in (2, 4, 6, 8, 10)}

    out = {
        "n_frames": n,
        "fps": fps,
        "params": {"BRIGHT_T": BRIGHT_T, "MIN_MASK_PX": MIN_MASK_PX, "CHANGE_FRAC": CHANGE_FRAC},
        "raw_diff": {
            "mean": round(float(raw_arr.mean()), 2),
            "p50": round(float(np.percentile(raw_arr, 50)), 2),
            "p90": round(float(np.percentile(raw_arr, 90)), 2),
            "events_gt_threshold": raw_events_at,
        },
        "mask_change_events": int(sum(c > CHANGE_FRAC for c in mask_changes)),
        "n_runs": len(runs),
        "n_text_runs": len(text_runs),
        "ocr_calls_needed": len(text_runs),
        "ocr_calls_every_frame": n,
        "savings_pct": round(100 * (1 - len(text_runs) / n), 1),
        "runs": runs,
    }
    Path(out_json).write_text(json.dumps(out, indent=2))
    print(f"frames={n}  runs={len(runs)} (text runs={len(text_runs)})  "
          f"OCR calls {len(text_runs)} vs {n} every-frame  savings={out['savings_pct']}%")
    print("raw-diff mean=%.2f p50=%.2f p90=%.2f -> naive raw diff events at thresholds: %s"
          % (raw_arr.mean(), np.percentile(raw_arr, 50), np.percentile(raw_arr, 90), raw_events_at))


if __name__ == "__main__":
    main()
