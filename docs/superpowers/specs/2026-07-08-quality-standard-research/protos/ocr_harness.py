#!/usr/bin/env python3
"""Apple Vision OCR feasibility harness (TASK A, 2026-07-08 quality-standard research).

Reads burnt-in subtitles from a rendered MP4 with Apple's Vision framework
(VNRecognizeTextRequest via the `ocrmac` pip package), compares against the
ground-truth cue text in backend/data/registry.json, and reports per-cue CER.

Run with the scratch venv python (python3.11 + ocrmac):
    <ocr-venv>/bin/python ocr_harness.py

READ-ONLY on backend data. Frames go to a scratch dir; results JSON is written
next to this script.

Pipeline per sampled cue:
  1. ffmpeg -ss <cue midpoint> -i render.mp4 -frames:v 1, crop bottom 28% band
  2. Vision OCR (recognitionLanguages ['zh-Hant','en-US'], level accurate)
  3. Keep only fragments whose bbox top (y+h, bottom-origin normalized) is
     <= SUBTITLE_BAND_TOP of the crop -- burnt subtitle sits at top<=0.245,
     broadcast graphics (horse names/odds) sit at top>=0.35 (calibrated
     empirically on this render).
  4. Re-join fragments: group into rows by y, rows top-to-bottom, fragments
     left-to-right (Vision splits one visual line into >=1 fragments).
  5. CER = levenshtein(ocr, gt) / len(gt) after stripping all whitespace.
     Secondary metric: CER after also stripping CJK/latin punctuation.
"""

import json
import re
import statistics
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

from ocrmac import ocrmac

# ---------------------------------------------------------------- constants
REPO = Path("/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai")
REGISTRY = REPO / "backend/data/registry.json"
RENDER_MP4 = REPO / "backend/data/renders/26a39e99ddf3.mp4"  # newest render (2026-06-17)
FILE_ID = "48c1657e7ec1"  # zh (書面語) track of YTDown_YouTube_Media_9p0b_SlvsT4_001_1080p.mp4
LANG = "zh"

SCRATCH = Path(
    "/private/tmp/claude-501/-Users-renocheung-Documents-GitHub---Remote-Repo-"
    "whisper-subtitle-ai--claude-worktrees-packaging-license-sync/"
    "b2d423dd-4d0c-42ac-969d-72a2a7b1d4c8/scratchpad"
)
FRAMES_DIR = SCRATCH / "frames" / "harness"
OUT_JSON = Path(__file__).parent / "ocr_apple_vision_results.json"

CROP_FRACTION = 0.28        # bottom band height as fraction of frame height
SUBTITLE_BAND_TOP = 0.30    # keep OCR fragments whose bbox top <= this (crop-normalized)
                            # (subtitle top observed <=0.263; graphics top >=0.35)
N_SAMPLES = 24              # cues to sample (spread across the video)
ROW_GROUP_TOL = 0.06        # fragments within this y distance belong to one visual row

_PUNCT_RE = re.compile(r"[　-〿＀-￯‘-‟.,!?;:'\"()\[\]{}<>…·-]")


# ---------------------------------------------------------------- helpers
def strip_spaces(s: str) -> str:
    return "".join(ch for ch in s if not ch.isspace())


def strip_punct(s: str) -> str:
    return _PUNCT_RE.sub("", s)


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


def extract_frame(ts: float, out_png: Path) -> float:
    """Extract one bottom-band frame at ts; returns ffmpeg wall seconds."""
    t0 = time.perf_counter()
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", f"{ts:.3f}", "-i", str(RENDER_MP4),
            "-frames:v", "1",
            "-vf", f"crop=iw:ih*{CROP_FRACTION}:0:ih*{1 - CROP_FRACTION}",
            "-y", str(out_png),
        ],
        check=True,
    )
    return time.perf_counter() - t0


def ocr_frame(png: Path):
    """Run Vision OCR; returns (raw fragments, ocr wall seconds)."""
    t0 = time.perf_counter()
    raw = ocrmac.OCR(
        str(png),
        language_preference=["zh-Hant", "en-US"],
        recognition_level="accurate",
    ).recognize()
    return raw, time.perf_counter() - t0


def pick_subtitle_text(raw) -> str:
    """Filter to the subtitle band and re-join fragments in reading order."""
    frags = [
        {"text": t, "conf": c, "x": b[0], "y": b[1], "w": b[2], "h": b[3]}
        for (t, c, b) in raw
        if (b[1] + b[3]) <= SUBTITLE_BAND_TOP
    ]
    if not frags:
        return ""
    # group into visual rows by y (bottom-origin); rows rendered top-first
    frags.sort(key=lambda f: -f["y"])
    rows = []
    for f in frags:
        if rows and abs(rows[-1][0][ "y"] - f["y"]) <= ROW_GROUP_TOL:
            rows[-1].append(f)
        else:
            rows.append([f])
    lines = []
    for row in rows:  # already top row first (higher y first)
        row.sort(key=lambda f: f["x"])
        lines.append("".join(f["text"] for f in row))
    return "\n".join(lines)


# ---------------------------------------------------------------- main
def main() -> None:
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    registry = json.loads(REGISTRY.read_text())
    entry = registry[FILE_ID]
    rows = entry["translations"]

    def gt_text(r):
        by = (r.get("by_lang") or {}).get(LANG) or {}
        return by.get("text") or r.get(f"{LANG}_text") or ""

    candidates = [(i, r) for i, r in enumerate(rows) if strip_spaces(gt_text(r))]
    # spread N_SAMPLES evenly across the candidate list
    step = max(1, len(candidates) // N_SAMPLES)
    picks = candidates[::step][:N_SAMPLES]

    results = []
    for idx, row in picks:
        mid = (row["start"] + row["end"]) / 2.0
        gt = gt_text(row)
        png = FRAMES_DIR / f"cue{idx:03d}_{mid:.2f}.png"
        ff_sec = extract_frame(mid, png)
        raw, ocr_sec = ocr_frame(png)
        ocr_text = pick_subtitle_text(raw)

        a, b = strip_spaces(ocr_text.replace("\n", "")), strip_spaces(gt)
        dist = levenshtein(a, b)
        cer = dist / len(b) if b else None
        a2, b2 = strip_punct(a), strip_punct(b)
        dist2 = levenshtein(a2, b2)
        cer_np = dist2 / len(b2) if b2 else None

        results.append(
            {
                "cue_idx": idx,
                "midpoint_sec": round(mid, 3),
                "start": row["start"],
                "end": row["end"],
                "gt": gt,
                "ocr": ocr_text,
                "edit_distance": dist,
                "gt_len": len(b),
                "cer": round(cer, 4),
                "cer_no_punct": round(cer_np, 4) if cer_np is not None else None,
                "ffmpeg_sec": round(ff_sec, 3),
                "ocr_sec": round(ocr_sec, 3),
                "raw_fragments": [
                    {"text": t, "conf": c, "bbox": [round(v, 4) for v in bb]}
                    for (t, c, bb) in raw
                ],
            }
        )
        print(f"cue {idx:3d} @ {mid:7.2f}s  CER={cer:.3f}  ocr={ocr_sec:.2f}s  "
              f"gt={gt[:24]!r} ocr={ocr_text[:24]!r}")

    cers = [r["cer"] for r in results]
    cers_np = [r["cer_no_punct"] for r in results]
    ocr_times = [r["ocr_sec"] for r in results]
    ff_times = [r["ffmpeg_sec"] for r in results]
    summary = {
        "render_mp4": str(RENDER_MP4),
        "source_file_id": FILE_ID,
        "lang_track": LANG,
        "n_cues": len(results),
        "cer_mean": round(statistics.mean(cers), 4),
        "cer_median": round(statistics.median(cers), 4),
        "cer_max": round(max(cers), 4),
        "cer_min": round(min(cers), 4),
        "cer_no_punct_mean": round(statistics.mean(cers_np), 4),
        "cer_no_punct_median": round(statistics.median(cers_np), 4),
        "cues_exact_match": sum(1 for c in cers if c == 0),
        "cues_exact_match_no_punct": sum(1 for c in cers_np if c == 0),
        "ocr_sec_mean": round(statistics.mean(ocr_times), 3),
        "ocr_sec_median": round(statistics.median(ocr_times), 3),
        "ffmpeg_sec_mean": round(statistics.mean(ff_times), 3),
        "config": {
            "crop_fraction": CROP_FRACTION,
            "subtitle_band_top": SUBTITLE_BAND_TOP,
            "recognition_level": "accurate",
            "language_preference": ["zh-Hant", "en-US"],
            "ocrmac_backend": "VNRecognizeTextRequest (Vision.framework)",
        },
    }
    OUT_JSON.write_text(json.dumps({"summary": summary, "cues": results},
                                   ensure_ascii=False, indent=2))
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nresults -> {OUT_JSON}")


if __name__ == "__main__":
    main()
