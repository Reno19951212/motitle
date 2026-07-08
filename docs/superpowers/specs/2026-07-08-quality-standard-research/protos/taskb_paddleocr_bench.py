#!/usr/bin/env python3
"""TASK B — Open-source Chinese OCR benchmark (PaddleOCR) against burnt-in subtitle renders.

Protocol (mirrors Task A so numbers are comparable):
  1. Map a rendered MP4 (backend/data/renders/<render_id>.mp4) to a registry file entry
     (done out-of-band; mapping verified by frame text match — see notes in results JSON).
  2. Pick N non-empty cues evenly spaced across the ground-truth track.
  3. Extract ONE frame at each cue midpoint with ffmpeg, cropped to the bottom subtitle band.
  4. OCR each crop; measure per-frame wall time (OCR call only) and per-cue CER
     (Levenshtein distance / len(ground truth)).

READ-ONLY on backend/data + config. All outputs go next to this script / --frames-dir.

Usage (from the ocr-venv):
  python taskb_paddleocr_bench.py \
      --render /path/to/renders/335ed02ff40f.mp4 \
      --registry /path/to/backend/data/registry.json \
      --file-id 48c1657e7ec1 --lang zh --n 24 \
      --crop 1920:100:0:980 \
      --frames-dir /tmp/frames --out results.json
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

PUNCT = set("，。、：；！？…—·「」『』（）〈〉《》,.:;!?()[]{}\"'~-‥⋯ ")


def has_cjk(s: str) -> bool:
    """True if the line contains at least one CJK ideograph.

    Used to drop the Latin-only race-graphics banner (horse-name strip) that
    intrudes into the bottom band during mid-race shots. The ground truth is a
    Chinese subtitle track, so every real subtitle line contains CJK.
    """
    return any(0x4E00 <= ord(ch) <= 0x9FFF or 0x3400 <= ord(ch) <= 0x4DBF for ch in s)


def levenshtein(a: str, b: str) -> int:
    """Plain O(len(a)*len(b)) edit distance — cue strings are short."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1,          # deletion
                           cur[j - 1] + 1,       # insertion
                           prev[j - 1] + (ca != cb)))  # substitution
        prev = cur
    return prev[-1]


def norm_ws(s: str) -> str:
    """NFC + strip ALL whitespace (subtitle join artifacts)."""
    s = unicodedata.normalize("NFC", s)
    return "".join(ch for ch in s if not ch.isspace())


def norm_nopunct(s: str) -> str:
    """norm_ws + drop punctuation (both CJK fullwidth and ASCII)."""
    return "".join(ch for ch in norm_ws(s) if ch not in PUNCT)


def cer(gt: str, hyp: str) -> float:
    if not gt:
        return 0.0 if not hyp else 1.0
    return levenshtein(gt, hyp) / len(gt)


def pick_cues(rows, lang, n):
    """Evenly-spaced sample of non-empty cues (returns list of (idx, start, end, text))."""
    nonempty = []
    for i, r in enumerate(rows):
        by = r.get("by_lang") or {}
        v = by.get(lang)
        text = (v.get("text") if isinstance(v, dict) else v) or r.get(f"{lang}_text") or ""
        text = text.strip()
        if text:
            nonempty.append((i, float(r["start"]), float(r["end"]), text))
    if len(nonempty) <= n:
        return nonempty
    step = (len(nonempty) - 1) / (n - 1)
    return [nonempty[round(k * step)] for k in range(n)]


def extract_crop(video, t, crop, out_png):
    """One cue-midpoint frame, bottom-band cropped. Returns ffmpeg wall seconds."""
    t0 = time.perf_counter()
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
         "-frames:v", "1", "-vf", f"crop={crop}", str(out_png)],
        check=True, capture_output=True)
    return time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", required=True)
    ap.add_argument("--registry", required=True)
    ap.add_argument("--file-id", required=True)
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--crop", default="1920:100:0:980",
                    help="ffmpeg crop w:h:x:y for the subtitle band")
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", default="paddle", choices=["paddle", "rapidocr"])
    ap.add_argument("--ocr-lang", default="chinese_cht")
    ap.add_argument("--missing-glyphs", default="內錶沒為",
                    help="chars the RENDER font lacks (verified visually on frames: "
                         "the burnt-in line shows a blank gap). Removed from GT for "
                         "the render-aware CER variant, isolating pure OCR accuracy.")
    args = ap.parse_args()
    missing = set(args.missing_glyphs)

    registry = json.loads(Path(args.registry).read_text())
    entry = registry.get(args.file_id)
    if entry is None:
        sys.exit(f"file id {args.file_id} not in registry")
    cues = pick_cues(entry.get("translations") or [], args.lang, args.n)
    if len(cues) < 5:
        sys.exit(f"only {len(cues)} usable cues — aborting")

    frames_dir = Path(args.frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    # ---- extract frames (not part of OCR timing) -------------------------
    frame_paths, extract_secs = [], []
    for idx, start, end, _ in cues:
        mid = (start + end) / 2.0
        png = frames_dir / f"cue{idx:03d}_t{mid:.2f}.png"
        if not png.exists():
            extract_secs.append(extract_crop(args.render, mid, args.crop, png))
        frame_paths.append(png)

    # ---- OCR engine ------------------------------------------------------
    if args.engine == "paddle":
        from paddleocr import PaddleOCR  # deferred: heavy import
        t0 = time.perf_counter()
        ocr = PaddleOCR(lang=args.ocr_lang,
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False)
        init_secs = time.perf_counter() - t0

        def run_ocr(png_path):
            texts = []
            for r in ocr.predict(str(png_path)):
                texts.extend(r.get("rec_texts") or [])
            return texts
    else:  # rapidocr (onnxruntime backend, PP-OCRv4/v5 ch models)
        from rapidocr_onnxruntime import RapidOCR
        t0 = time.perf_counter()
        ocr = RapidOCR()
        init_secs = time.perf_counter() - t0

        def run_ocr(png_path):
            result, _elapse = ocr(str(png_path))
            return [item[1] for item in (result or [])]

    # warm-up (first predict pays one-off graph build; measured separately)
    t0 = time.perf_counter()
    run_ocr(frame_paths[0])
    warmup_secs = time.perf_counter() - t0

    rows, ocr_secs = [], []
    for (idx, start, end, gt), png in zip(cues, frame_paths):
        t0 = time.perf_counter()
        all_lines = run_ocr(png)
        dt = time.perf_counter() - t0
        ocr_secs.append(dt)
        kept = [ln for ln in all_lines if has_cjk(ln)]  # drop Latin-only banner strip
        hyp = "".join(kept)
        g_ws, h_ws = norm_ws(gt), norm_ws(hyp)
        g_np, h_np = norm_nopunct(gt), norm_nopunct(hyp)
        # render-aware GT: drop chars the burn-in font could not draw
        g_ws_r = "".join(ch for ch in g_ws if ch not in missing)
        g_np_r = "".join(ch for ch in g_np if ch not in missing)
        rows.append({
            "idx": idx, "start": start, "end": end,
            "gt": gt, "ocr": hyp, "ocr_all_lines": all_lines,
            "banner_lines_dropped": len(all_lines) - len(kept),
            "cer_ws": round(cer(g_ws, h_ws), 4),
            "cer_nopunct": round(cer(g_np, h_np), 4),
            "cer_ws_render_aware": round(cer(g_ws_r, h_ws), 4),
            "cer_nopunct_render_aware": round(cer(g_np_r, h_np), 4),
            "ocr_secs": round(dt, 3),
        })

    # ---- corpus-level metrics -------------------------------------------
    def strip_missing(s):
        return "".join(ch for ch in s if ch not in missing)

    tot_ed_ws = sum(levenshtein(norm_ws(r["gt"]), norm_ws(r["ocr"])) for r in rows)
    tot_len_ws = sum(len(norm_ws(r["gt"])) for r in rows)
    tot_ed_np = sum(levenshtein(norm_nopunct(r["gt"]), norm_nopunct(r["ocr"])) for r in rows)
    tot_len_np = sum(len(norm_nopunct(r["gt"])) for r in rows)
    tot_ed_ws_r = sum(levenshtein(strip_missing(norm_ws(r["gt"])), norm_ws(r["ocr"])) for r in rows)
    tot_len_ws_r = sum(len(strip_missing(norm_ws(r["gt"]))) for r in rows)
    tot_ed_np_r = sum(levenshtein(strip_missing(norm_nopunct(r["gt"])), norm_nopunct(r["ocr"])) for r in rows)
    tot_len_np_r = sum(len(strip_missing(norm_nopunct(r["gt"]))) for r in rows)

    summary = {
        "engine": "PaddleOCR" if args.engine == "paddle" else "RapidOCR(onnxruntime)",
        "render": args.render,
        "file_id": args.file_id,
        "lang_track": args.lang,
        "ocr_lang": args.ocr_lang,
        "crop": args.crop,
        "missing_glyphs_in_render_font": args.missing_glyphs,
        "n_cues": len(rows),
        "corpus_cer_ws": round(tot_ed_ws / tot_len_ws, 4),
        "corpus_cer_nopunct": round(tot_ed_np / tot_len_np, 4),
        "corpus_cer_ws_render_aware": round(tot_ed_ws_r / tot_len_ws_r, 4),
        "corpus_cer_nopunct_render_aware": round(tot_ed_np_r / tot_len_np_r, 4),
        "mean_cue_cer_ws": round(statistics.mean(r["cer_ws"] for r in rows), 4),
        "exact_match_ws": sum(1 for r in rows if r["cer_ws"] == 0.0),
        "exact_match_nopunct": sum(1 for r in rows if r["cer_nopunct"] == 0.0),
        "exact_match_ws_render_aware": sum(1 for r in rows if r["cer_ws_render_aware"] == 0.0),
        "frames_with_banner": sum(1 for r in rows if r["banner_lines_dropped"] > 0),
        "ocr_secs_mean": round(statistics.mean(ocr_secs), 3),
        "ocr_secs_median": round(statistics.median(ocr_secs), 3),
        "ocr_secs_min": round(min(ocr_secs), 3),
        "ocr_secs_max": round(max(ocr_secs), 3),
        "init_secs": round(init_secs, 2),
        "warmup_first_predict_secs": round(warmup_secs, 2),
        "ffmpeg_extract_secs_mean": round(statistics.mean(extract_secs), 3) if extract_secs else None,
        "gt_chars_total_ws": tot_len_ws,
        "edit_distance_total_ws": tot_ed_ws,
    }
    out = {"summary": summary, "cues": rows}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for r in rows:
        flag = "" if r["cer_ws_render_aware"] == 0 else "  <-- diff"
        print(f'#{r["idx"]:3d} cer_ws={r["cer_ws"]:.3f} raw={r["cer_ws_render_aware"]:.3f} '
              f'{r["ocr_secs"]:.2f}s GT={r["gt"]!r} OCR={r["ocr"]!r}{flag}')


if __name__ == "__main__":
    main()
