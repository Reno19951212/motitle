#!/usr/bin/env python3
"""Task C (c) DEDUP/MERGE — full band->cues pipeline + eval vs registry ground truth.

Stages (self-contained):
  1. change detection on downscaled band crops (outline-constrained text mask,
     XOR/union > CHANGE_FRAC segments into stable runs; presence gate skips
     no-text runs)
  2. OCR (Apple Vision via ocrmac, accurate, zh-Hant) on ONE representative
     frame per text run, tight native-res crop
  3. dedup/merge: adjacent runs with identical/fuzzy-equal text merged into
     cues; boundary estimate start = t_first - dt/2, end = t_last + dt/2
  4. eval vs registry cues: match by time-IoU, report |dStart|, |dEnd|, CER

Usage:
  python 03_ocr_merge_eval.py <small_band_dir> <native_band_dir> <fps> \
      <file_id> <out_json> [srt_out]
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from ocrmac import ocrmac

REGISTRY = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/data/registry.json"
# tight subtitle band inside the 270px-high band crop (y810..1080 of 1080p);
# override via CLI arg 7 "native_lo:native_hi" (small rows derived by /2)
ROWS_SMALL = slice(95, 135)     # 960x135 downscaled band
ROWS_NATIVE = slice(190, 270)   # 1920x270 native band
BRIGHT_T, DARK_T = 190, 70
MIN_MASK_PX = 40                # presence gate (downscaled tight band).
                                # 80 missed a real 2-char cue (雙方 = 55 px);
                                # no-text background maxed at 30 px.
CHANGE_FRAC = 0.20
FUZZY_SAME = 0.70               # similarity above which two OCR texts are "same cue"
                                # (busy-background OCR wobble needs a loose gate;
                                #  0.85 left fragments unmerged in run 1)
X_FILTER = None                 # (lo, hi): keep only OCR lines whose x-center is
                                # inside; drops off-center lower-thirds/watermarks
                                # (subtitles here are ASS alignment=2, centered)


def dilate(m: np.ndarray, k: int = 2) -> np.ndarray:
    out = np.zeros_like(m)
    H, W = m.shape
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            ys = slice(max(dy, 0), H + min(dy, 0)); yd = slice(max(-dy, 0), H + min(-dy, 0))
            xs = slice(max(dx, 0), W + min(dx, 0)); xd = slice(max(-dx, 0), W + min(-dx, 0))
            out[yd, xd] |= m[ys, xs]
    return out


def text_mask(gray_band: np.ndarray) -> np.ndarray:
    """Subtitle glyph mask: bright fill with a dark outline within 2px."""
    return (gray_band >= BRIGHT_T) & dilate(gray_band < DARK_T, 2)


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    m = max(len(a), len(b))
    return 1.0 - levenshtein(a, b) / m if m else 1.0


def norm_text(s: str) -> str:
    return "".join(s.split())


def ocr_band(png: Path) -> str:
    """OCR the tight subtitle band and reconstruct READING ORDER.

    Vision often splits one visual line into several boxes with slight y
    jitter; naive y-sort scrambles the characters (measured run 1: CER 15.7%
    almost entirely from this). Group boxes into lines by y-center proximity,
    sort lines top->bottom, boxes left->right within a line.
    """
    img = Image.open(png).convert("RGB").crop(
        (0, ROWS_NATIVE.start, 1920, ROWS_NATIVE.stop))
    res = ocrmac.OCR(img, recognition_level="accurate",
                     language_preference=["zh-Hant", "en-US"]).recognize()
    if not res:
        return ""
    boxes = [(t, x, x + w, y + h / 2, h) for t, _, (x, y, w, h) in res]
    med_h = sorted(b[4] for b in boxes)[len(boxes) // 2]
    lines: list = []  # [y_center, [(x0, x1, text), ...]]
    for t, x0, x1, yc, _ in sorted(boxes, key=lambda b: -b[3]):  # top first (bottom-origin y)
        if lines and abs(lines[-1][0] - yc) < 0.6 * med_h:
            lines[-1][1].append((x0, x1, t))
        else:
            lines.append([yc, [(x0, x1, t)]])
    parts = []
    for _, items in lines:
        items.sort()
        # split a y-line into segments at big x-gaps (left+right straps share a
        # y-line; their x-union is accidentally "centered" — measured on run 2)
        segs, seg = [], [items[0]]
        for it in items[1:]:
            if it[0] - seg[-1][1] > 0.15:
                segs.append(seg)
                seg = [it]
            else:
                seg.append(it)
        segs.append(seg)
        for seg in segs:
            if X_FILTER:
                xc = (seg[0][0] + seg[-1][1]) / 2
                if not (X_FILTER[0] <= xc <= X_FILTER[1]):
                    continue
            parts.extend(t for _, _, t in seg)
    return norm_text(" ".join(parts))


def main() -> None:
    global ROWS_SMALL, ROWS_NATIVE
    small_dir, native_dir = Path(sys.argv[1]), Path(sys.argv[2])
    fps, file_id, out_json = float(sys.argv[3]), sys.argv[4], sys.argv[5]
    srt_out = sys.argv[6] if len(sys.argv) > 6 else None
    if len(sys.argv) > 7:
        lo, hi = (int(x) for x in sys.argv[7].split(":"))
        ROWS_NATIVE = slice(lo, hi)
        ROWS_SMALL = slice(lo // 2, hi // 2)
    if len(sys.argv) > 8:      # e.g. "0.35:0.65"
        global X_FILTER
        X_FILTER = tuple(float(x) for x in sys.argv[8].split(":"))
    dt = 1.0 / fps

    small = sorted(small_dir.glob("*.png"))
    native = sorted(native_dir.glob("*.png"))
    assert len(small) == len(native), "frame count mismatch"
    n = len(small)

    # --- stage 1: change detection ---
    t0 = time.time()
    masks = [text_mask(np.asarray(Image.open(f).convert("L"), dtype=np.uint8)[ROWS_SMALL, :])
             for f in small]
    px = [int(m.sum()) for m in masks]
    runs = []
    cur = {"first": 0, "last": 0}
    for i in range(1, n):
        xor = int((masks[i] ^ masks[i - 1]).sum())
        union = int((masks[i] | masks[i - 1]).sum())
        frac = xor / union if union else 0.0
        has_a, has_b = px[i - 1] >= MIN_MASK_PX, px[i] >= MIN_MASK_PX
        if frac > CHANGE_FRAC or has_a != has_b:
            runs.append(cur)
            cur = {"first": i, "last": i}
        else:
            cur["last"] = i
    runs.append(cur)
    for r in runs:
        r["has_text"] = max(px[r["first"]:r["last"] + 1]) >= MIN_MASK_PX
    detect_s = time.time() - t0
    text_runs = [r for r in runs if r["has_text"]]

    # --- stage 2: OCR one representative frame per text run ---
    t0 = time.time()
    for r in text_runs:
        rep = (r["first"] + r["last"]) // 2
        r["text"] = ocr_band(native[rep])
    ocr_s = time.time() - t0

    # --- stage 3: merge adjacent same-text runs into cues ---
    cues = []
    for r in text_runs:
        if not r["text"]:
            continue
        run_len = r["last"] - r["first"]
        if cues and r["first"] - cues[-1]["last_idx"] <= 1 and \
                similarity(r["text"], cues[-1]["text"]) >= FUZZY_SAME:
            prev = cues[-1]
            if run_len > prev["best_len"]:
                # keep text of the LONGEST run (most stable OCR view)
                prev["text"], prev["best_len"] = r["text"], run_len
            prev["last_idx"] = r["last"]
        else:
            cues.append({"first_idx": r["first"], "last_idx": r["last"],
                         "text": r["text"], "best_len": run_len})
    # sandwich-absorb: a very short cue (<= 2 frames) whose text is garbled
    # OCR wobble gets attached to the more-similar neighbour (measured: busy
    # backgrounds produce 0.25-0.5s garble runs that the fuzzy gate rejects)
    changed = True
    while changed:
        changed = False
        for i, c in enumerate(cues):
            if c["last_idx"] - c["first_idx"] > 2:
                continue
            sim_prev = similarity(c["text"], cues[i - 1]["text"]) if i > 0 and \
                c["first_idx"] - cues[i - 1]["last_idx"] <= 1 else -1.0
            sim_next = similarity(c["text"], cues[i + 1]["text"]) if i + 1 < len(cues) and \
                cues[i + 1]["first_idx"] - c["last_idx"] <= 1 else -1.0
            if max(sim_prev, sim_next) < 0.30:
                continue
            target = cues[i - 1] if sim_prev >= sim_next else cues[i + 1]
            target["first_idx"] = min(target["first_idx"], c["first_idx"])
            target["last_idx"] = max(target["last_idx"], c["last_idx"])
            del cues[i]
            changed = True
            break

    for c in cues:
        c["start"] = round(max(0.0, c["first_idx"] * dt - dt / 2), 3)
        c["end"] = round(c["last_idx"] * dt + dt / 2, 3)

    # --- stage 4: eval vs registry ---
    reg = json.load(open(REGISTRY))
    gts = []
    for row in reg[file_id]["translations"]:
        txt = (row.get("by_lang") or {}).get("zh", {}).get("text") or row.get("zh_text") or ""
        txt = norm_text(txt)
        if txt:
            gts.append({"start": row["start"], "end": row["end"], "text": txt})

    def iou(a, b):
        inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
        union = max(a["end"], b["end"]) - min(a["start"], b["start"])
        return inter / union if union > 0 else 0.0

    pairs, used = [], set()
    for g in gts:
        best, bi = 0.0, None
        for i, c in enumerate(cues):
            if i in used:
                continue
            v = iou(g, c)
            if v > best:
                best, bi = v, i
        if bi is not None and best > 0.1:
            used.add(bi)
            c = cues[bi]
            pairs.append({
                "gt": g, "det": {"start": c["start"], "end": c["end"], "text": c["text"]},
                "d_start": round(c["start"] - g["start"], 3),
                "d_end": round(c["end"] - g["end"], 3),
                "cer": round(levenshtein(c["text"], g["text"]) / max(1, len(g["text"])), 4),
            })
    ds = np.array([abs(p["d_start"]) for p in pairs])
    de = np.array([abs(p["d_end"]) for p in pairs])
    cer_w = sum(levenshtein(p["det"]["text"], p["gt"]["text"]) for p in pairs) / \
        max(1, sum(len(p["gt"]["text"]) for p in pairs))

    metrics = {
        "fps": fps,
        "n_frames": n,
        "n_runs": len(runs),
        "n_text_runs": len(text_runs),
        "ocr_calls": len(text_runs),
        "ocr_savings_vs_every_frame_pct": round(100 * (1 - len(text_runs) / n), 1),
        "detect_wall_s": round(detect_s, 2),
        "ocr_wall_s": round(ocr_s, 2),
        "ocr_s_per_call": round(ocr_s / max(1, len(text_runs)), 3),
        "n_detected_cues": len(cues),
        "n_gt_cues": len(gts),
        "n_matched": len(pairs),
        "n_gt_missed": len(gts) - len(pairs),
        "n_spurious": len(cues) - len(pairs),
        "abs_d_start": {"mean": round(float(ds.mean()), 3), "median": round(float(np.median(ds)), 3),
                        "p90": round(float(np.percentile(ds, 90)), 3), "max": round(float(ds.max()), 3)},
        "abs_d_end": {"mean": round(float(de.mean()), 3), "median": round(float(np.median(de)), 3),
                      "p90": round(float(np.percentile(de, 90)), 3), "max": round(float(de.max()), 3)},
        "corpus_cer": round(cer_w, 4),
    }
    Path(out_json).write_text(json.dumps({"metrics": metrics, "pairs": pairs,
                                          "cues": cues}, ensure_ascii=False, indent=2))
    print(json.dumps(metrics, indent=2))

    if srt_out:
        def ts(t):
            h, rem = divmod(t, 3600); m, s = divmod(rem, 60)
            return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"
        with open(srt_out, "w") as fh:
            for i, c in enumerate(cues, 1):
                fh.write(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n\n")
        print("wrote", srt_out)


if __name__ == "__main__":
    main()
