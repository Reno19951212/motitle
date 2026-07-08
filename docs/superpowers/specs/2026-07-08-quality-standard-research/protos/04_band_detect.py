#!/usr/bin/env python3
"""Task C (d) BAND DETECTION — where do burnt subs actually sit across renders?

Auto-detection probe: sample K full frames spread over the video, full-frame
OCR each (Apple Vision), keep CJK-bearing boxes in the bottom half, cluster
box y-centers across frames, and pick the cluster that RECURS in the most
frames (subtitles are bottom-anchored at a fixed margin; other graphics move
or appear once). Reports the subtitle band y-range per video.

Usage: python 04_band_detect.py <out_json> <video1> [video2 ...]
"""
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ocrmac import ocrmac

K_PROBES = 12
CJK = re.compile(r"[一-鿿㐀-䶿]")


def probe_video(video: str) -> dict:
    dur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video]).strip())
    h = int(subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=height", "-of", "csv=p=0", video]).strip())
    t0 = time.time()
    hits = []  # (probe_idx, y_top_px, y_bot_px, text)
    with tempfile.TemporaryDirectory() as td:
        for i in range(K_PROBES):
            t = dur * (i + 0.5) / K_PROBES
            png = Path(td) / f"p{i}.png"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1",
                            str(png), "-y"], check=True)
            res = ocrmac.OCR(str(png), recognition_level="accurate",
                             language_preference=["zh-Hant", "en-US"]).recognize()
            for text, _, (x, y, w, bh) in res:
                if not CJK.search(text):
                    continue
                y_top = h * (1 - y - bh)   # Vision bbox is bottom-origin normalized
                y_bot = h * (1 - y)
                if y_top < h * 0.5:        # only bottom half
                    continue
                hits.append((i, round(y_top), round(y_bot), text))
    # cluster y-centers (25px tolerance), count DISTINCT probe frames per cluster
    clusters = []  # {yc, y_top_min, y_bot_max, probes:set, texts}
    for i, yt, yb, text in hits:
        yc = (yt + yb) / 2
        for c in clusters:
            if abs(c["yc"] - yc) < 25:
                c["yc"] = (c["yc"] + yc) / 2
                c["y_top"] = min(c["y_top"], yt)
                c["y_bot"] = max(c["y_bot"], yb)
                c["probes"].add(i)
                c["texts"].append(text)
                break
        else:
            clusters.append({"yc": yc, "y_top": yt, "y_bot": yb,
                             "probes": {i}, "texts": [text]})
    clusters.sort(key=lambda c: -len(c["probes"]))
    wall = time.time() - t0
    out = {
        "video": Path(video).name, "duration_s": round(dur, 1), "height": h,
        "probe_wall_s": round(wall, 1),
        "clusters": [{
            "y_top": c["y_top"], "y_bot": c["y_bot"],
            "n_probe_frames": len(c["probes"]),
            "sample_texts": c["texts"][:3],
        } for c in clusters[:4]],
    }
    if clusters:
        best = clusters[0]
        out["subtitle_band"] = {
            "y_top": best["y_top"], "y_bot": best["y_bot"],
            "pct_of_height": [round(best["y_top"] / h, 3), round(best["y_bot"] / h, 3)],
        }
    return out


def main() -> None:
    out_json, videos = sys.argv[1], sys.argv[2:]
    results = [probe_video(v) for v in videos]
    Path(out_json).write_text(json.dumps(results, ensure_ascii=False, indent=2))
    for r in results:
        band = r.get("subtitle_band", {})
        print(f"{r['video']}: band y={band.get('y_top')}..{band.get('y_bot')} "
              f"({band.get('pct_of_height')}) probes hit "
              f"{r['clusters'][0]['n_probe_frames'] if r['clusters'] else 0}/{K_PROBES}, "
              f"wall {r['probe_wall_s']}s")
        for c in r["clusters"]:
            print(f"    cluster y {c['y_top']}..{c['y_bot']} in {c['n_probe_frames']} frames: "
                  f"{c['sample_texts'][:2]}")


if __name__ == "__main__":
    main()
