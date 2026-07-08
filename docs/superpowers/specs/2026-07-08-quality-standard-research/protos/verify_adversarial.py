#!/usr/bin/env python3
"""Adversarial verification (2026-07-08): re-run OCR claims on FRESH cues of a
DIFFERENT render (ac22373f4908.mp4 -> registry file 98383e00aa62, zh track,
mapped independently by duration 180.047s + on-screen content match).

Runs BOTH PaddleOCR (chinese_cht) and Apple Vision (ocrmac) on the same 5
cue-midpoint crops; records per-frame OCR wall time; computes CER vs the
current registry text. Crops are saved for visual screen-truth verification.

READ-ONLY on backend data. Run with the ocr-venv python.
"""
import json
import subprocess
import time
import unicodedata
from pathlib import Path

REPO = Path("/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai")
RENDER = REPO / "backend/data/renders/ac22373f4908.mp4"
REGISTRY = REPO / "backend/data/registry.json"
FILE_ID = "98383e00aa62"
LANG = "zh"
CUE_IDXS = [6, 11, 22, 32, 43]
CROP = "1920:130:0:930"
SCRATCH = Path(
    "/private/tmp/claude-501/-Users-renocheung-Documents-GitHub---Remote-Repo-"
    "whisper-subtitle-ai--claude-worktrees-packaging-license-sync/"
    "b2d423dd-4d0c-42ac-969d-72a2a7b1d4c8/scratchpad/verify_frames"
)
OUT = Path(__file__).parent / "verify_adversarial_results.json"

PUNCT = set("，。、：；！？…—·「」『』（）〈〉《》,.:;!?()[]{}\"'~-‥⋯ ")


def has_cjk(s):
    return any(0x4E00 <= ord(c) <= 0x9FFF or 0x3400 <= ord(c) <= 0x4DBF for c in s)


def levenshtein(a, b):
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


def norm_ws(s):
    s = unicodedata.normalize("NFC", s)
    return "".join(c for c in s if not c.isspace())


def norm_np(s):
    return "".join(c for c in norm_ws(s) if c not in PUNCT)


def cer(gt, hyp):
    return (levenshtein(gt, hyp) / len(gt)) if gt else (0.0 if not hyp else 1.0)


def main():
    reg = json.loads(REGISTRY.read_text())
    rows = reg[FILE_ID]["translations"]
    SCRATCH.mkdir(parents=True, exist_ok=True)

    cues = []
    for i in CUE_IDXS:
        r = rows[i]
        txt = (r.get("by_lang", {}).get(LANG, {}) or {}).get("text") or r.get(f"{LANG}_text")
        cues.append((i, float(r["start"]), float(r["end"]), txt.strip()))

    frames = []
    for i, s, e, _ in cues:
        mid = (s + e) / 2.0
        png = SCRATCH / f"ver_cue{i:03d}_t{mid:.2f}.png"
        t0 = time.perf_counter()
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{mid:.3f}", "-i", str(RENDER),
             "-frames:v", "1", "-vf", f"crop={CROP}", str(png)],
            check=True, capture_output=True)
        frames.append((png, time.perf_counter() - t0))

    # ---------------- Apple Vision ----------------
    from ocrmac import ocrmac
    vis_out = []
    for png, _ in frames:
        t0 = time.perf_counter()
        res = ocrmac.OCR(str(png), recognition_level="accurate",
                         language_preference=["zh-Hant", "en-US"]).recognize()
        dt = time.perf_counter() - t0
        lines = [t for (t, conf, bbox) in res if has_cjk(t)]
        vis_out.append({"lines_all": [t for (t, c, b) in res],
                        "hyp": "".join(lines), "secs": round(dt, 3)})

    # ---------------- PaddleOCR ----------------
    from paddleocr import PaddleOCR
    t0 = time.perf_counter()
    pocr = PaddleOCR(lang="chinese_cht", use_doc_orientation_classify=False,
                     use_doc_unwarping=False, use_textline_orientation=False)
    init_secs = time.perf_counter() - t0
    # warm-up on first frame (excluded from timing rows, mirrors prior protocol)
    t0 = time.perf_counter()
    pocr.predict(str(frames[0][0]))
    warm = time.perf_counter() - t0
    pad_out = []
    for png, _ in frames:
        t0 = time.perf_counter()
        texts = []
        for r in pocr.predict(str(png)):
            texts.extend(r.get("rec_texts") or [])
        dt = time.perf_counter() - t0
        kept = [ln for ln in texts if has_cjk(ln)]
        pad_out.append({"lines_all": texts, "hyp": "".join(kept), "secs": round(dt, 3)})

    result = {"render": str(RENDER), "file_id": FILE_ID, "crop": CROP,
              "paddle_init_secs": round(init_secs, 2), "paddle_warmup_secs": round(warm, 2),
              "cues": []}
    for (i, s, e, gt), (png, ff), v, p in zip(cues, frames, vis_out, pad_out):
        row = {"idx": i, "start": s, "end": e, "gt_registry": gt,
               "frame": str(png), "ffmpeg_secs": round(ff, 3),
               "vision": v, "paddle": p}
        for name, o in (("vision", v), ("paddle", p)):
            row[f"{name}_cer_ws"] = round(cer(norm_ws(gt), norm_ws(o["hyp"])), 4)
            row[f"{name}_cer_np"] = round(cer(norm_np(gt), norm_np(o["hyp"])), 4)
        result["cues"].append(row)

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    for r in result["cues"]:
        print(f"cue{r['idx']:03d}  GT: {r['gt_registry']}")
        print(f"  vision ({r['vision']['secs']}s, cer_ws {r['vision_cer_ws']}): {r['vision']['hyp']}")
        print(f"  paddle ({r['paddle']['secs']}s, cer_ws {r['paddle_cer_ws']}): {r['paddle']['hyp']}")
    print("paddle init", result["paddle_init_secs"], "warm", result["paddle_warmup_secs"])


if __name__ == "__main__":
    main()
