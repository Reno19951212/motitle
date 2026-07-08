#!/usr/bin/env python3
"""Task C (a) SAMPLING — measure frame-extraction cost at 2fps vs 4fps.

Extracts band-cropped frames from a rendered MP4 via ffmpeg and measures
wall time. Two crop variants:
  - native band crop  (1920x270 @ y=810)  — what we feed to OCR
  - downscaled band   (960x135)           — what we feed to change detection

Usage: python 01_sampling_extract.py <video> <out_root> <results_json>
"""
import json
import subprocess
import sys
import time
from pathlib import Path

BAND_FILTER_NATIVE = "crop=1920:270:0:810"
BAND_FILTER_SMALL = "crop=1920:270:0:810,scale=960:135"


def extract(video: str, out_dir: Path, fps: float, vf: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", video,
        "-vf", f"fps={fps},{vf}",
        "-fps_mode", "vfr",
        str(out_dir / "f%06d.png"), "-y",
    ]
    t0 = time.time()
    subprocess.run(cmd, check=True)
    wall = time.time() - t0
    frames = sorted(out_dir.glob("*.png"))
    total_bytes = sum(f.stat().st_size for f in frames)
    return {
        "fps": fps,
        "vf": vf,
        "wall_seconds": round(wall, 2),
        "n_frames": len(frames),
        "total_mb": round(total_bytes / 1e6, 1),
        "out_dir": str(out_dir),
    }


def main() -> None:
    video, out_root, results_json = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    dur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video]).strip())
    runs = []
    for fps in (2, 4):
        for label, vf in (("native", BAND_FILTER_NATIVE), ("small", BAND_FILTER_SMALL)):
            r = extract(video, out_root / f"{int(fps)}fps_{label}", fps, vf)
            r["label"] = label
            r["realtime_factor"] = round(dur / r["wall_seconds"], 1)
            runs.append(r)
            print(f"fps={fps} {label}: {r['wall_seconds']}s wall for {dur:.0f}s video "
                  f"({r['realtime_factor']}x realtime), {r['n_frames']} frames, {r['total_mb']} MB")
    out = {"video": video, "duration_s": round(dur, 2), "runs": runs}
    Path(results_json).write_text(json.dumps(out, indent=2))
    print("wrote", results_json)


if __name__ == "__main__":
    main()
