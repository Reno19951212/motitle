#!/usr/bin/env python3
"""Controlled standard-font test: burn the SAME registry zh track with Heiti TC
onto sub-free busy video (top 810px of the racing render, stretched to 1080p),
then the GT is exact by construction. Answers: is the 7.3% CER on render
26a39e99ddf3 a handwriting-FONT ceiling or a pipeline ceiling?

Writes the synthetic clip + ASS to scratch, then reuses 01/03 prototypes.

Usage: python 05_synth_standard_font.py <scratch_dir>
"""
import json
import subprocess
import sys
from pathlib import Path

REGISTRY = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/data/registry.json"
SRC = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/data/renders/26a39e99ddf3.mp4"
FILE_ID = "48c1657e7ec1"
FONT = "Heiti TC"       # daemon-safe standard CJK font used by production
SIZE = 60               # production-like size at PlayResY 1080


def ass_time(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def main() -> None:
    scratch = Path(sys.argv[1])
    scratch.mkdir(parents=True, exist_ok=True)
    reg = json.load(open(REGISTRY))
    rows = reg[FILE_ID]["translations"]

    lines = [
        "[Script Info]", "ScriptType: v4.00+",
        "PlayResX: 1920", "PlayResY: 1080", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
        "Bold, Italic, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV",
        f"Style: Default,{FONT},{SIZE},&H00FFFFFF,&H00000000,0,0,1,3,0,2,60,60,25",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for r in rows:
        txt = (r.get("by_lang") or {}).get("zh", {}).get("text") or ""
        if not txt.strip():
            continue
        lines.append(f"Dialogue: 0,{ass_time(r['start'])},{ass_time(r['end'])},"
                     f"Default,0,0,0,,{txt}")
    ass = scratch / "synth.ass"
    ass.write_text("\n".join(lines))

    out = scratch / "synth_heiti.mp4"
    vf = (f"crop=1920:810:0:0,scale=1920:1080,"
          f"subtitles={ass}:fontsdir=/System/Library/Fonts")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", SRC,
                    "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "20", str(out), "-y"], check=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
