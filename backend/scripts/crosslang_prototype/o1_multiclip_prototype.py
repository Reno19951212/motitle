"""O1 multi-clip prototype + drift check (2026-06-02).

Runs O1 (one content-language base ASR -> all outputs as 1:1 transforms -> shared
cues) across multiple clips + content languages, and verifies the 1:1 paired
alignment holds END-TO-END (first AND last cues paired, equal counts, monotonic
timing) — i.e. NO drift in the later part of long clips.

Derivations (all 1:1, preserve count + base timing):
  - output == base language     -> passthrough (the base text)
  - same Chinese family, 書面語  -> formal refiner (register, 1:1)
  - cross-language              -> MT (1:1)
  then OpenCC (繁 s2hk) for Chinese outputs.

Writes /tmp/o1_<tag>.srt per clip. Production: mlx large-v3 + Ollama qwen3.5:35b.
Run: cd backend && PYTHONPATH=. python scripts/crosslang_prototype/o1_multiclip_prototype.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

import mlx_whisper

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from translation import crosslang_mt          # noqa: E402
import output_lang_postprocess as olp          # noqa: E402

REPO = "mlx-community/whisper-large-v3-mlx"
OLLAMA = "http://localhost:11434"
MT_MODEL = "qwen3.5:35b-a3b-mlx-bf16"
FOLDER = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音"

# tag, clip, content_whisper_lang, clip_sec(0=full), [(out_lang, derivation)]
#   derivation: 'pass'=passthrough, 'refine'=formal書面 refiner, 'mt'=cross-lang MT
CLIPS = [
    ("WF_full", "The-Winning-Factor-Season 1 - （英文語音）.mp4", "en", 0,
     [("en", "pass"), ("zh", "mt")]),
    ("police_full", "香港警察結業會操（中文語音）.mp4", "yue", 0,
     [("yue", "pass"), ("zh", "refine")]),
    ("ato_150", "阿土 YouTube 爆旋陀螺（普通話語音）.mp4", "zh", 150,
     [("cmn", "pass"), ("en", "mt")]),
]


def _ollama(system, user):
    body = {"model": MT_MODEL, "stream": False, "think": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0.3}}
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode()).get("message", {}).get("content", "") or ""


def _ts(s):
    h = int(s // 3600); m = int((s % 3600) // 60); sec = int(s % 60); ms = int(round((s - int(s)) * 1000))
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def _derive(base, content_lang, out_lang, mode):
    if mode == "mt":
        d = crosslang_mt.translate_segments(base, content_lang, out_lang, _ollama)
    elif mode == "refine":
        d = olp.formal_refine(base, _ollama)
    else:  # pass
        d = [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in base]
    if out_lang in ("yue", "zh", "cmn"):
        d = olp.apply_script(d, "trad")
    return d


def main():
    summary = []
    for tag, clip, clang, sec, outs in CLIPS:
        wav = f"/tmp/o1_{tag}.wav"
        cmd = ["ffmpeg", "-y", "-i", f"{FOLDER}/{clip}"]
        if sec:
            cmd += ["-t", str(sec)]
        cmd += ["-ar", "16000", "-ac", "1", wav]
        subprocess.run(cmd, capture_output=True)
        print(f"\n{'='*72}\n## {tag}  base={clang}  outs={[o for o,_ in outs]}  ({'full' if not sec else str(sec)+'s'})\n{'='*72}", flush=True)
        t0 = time.time()
        r = mlx_whisper.transcribe(wav, path_or_hf_repo=REPO, language=clang, task="transcribe",
                                   condition_on_previous_text=False)
        base = [{"start": s["start"], "end": s["end"], "text": (s["text"] or "").strip()} for s in r.get("segments", [])]
        print(f"[base ASR {clang}] {len(base)} cues ({round(time.time()-t0,1)}s)", flush=True)

        derived = {}
        for ol, mode in outs:
            t1 = time.time()
            derived[ol] = _derive(base, clang, ol, mode)
            print(f"  -> {ol} ({mode}): {len(derived[ol])} cues ({round(time.time()-t1,1)}s)", flush=True)

        o1, o2 = outs[0][0], outs[1][0]
        d1, d2 = derived[o1], derived[o2]
        n = len(base)
        aligned = (len(d1) == n and len(d2) == n)
        # drift check: timing monotonic + last cue present in BOTH
        mono = all(base[i]["start"] <= base[i+1]["start"] for i in range(n-1))
        e1 = sum(1 for s in d1 if not s["text"].strip()); e2 = sum(1 for s in d2 if not s["text"].strip())
        print(f"\n  ALIGNMENT: base={n} {o1}={len(d1)} {o2}={len(d2)} -> {'PERFECT 1:1 ✅' if aligned else 'MISMATCH ❌'}", flush=True)
        print(f"  DRIFT CHECK: timing monotonic={mono}  empties: {o1}={e1} {o2}={e2}", flush=True)
        print(f"  --- FIRST 2 cues ---", flush=True)
        for i in range(min(2, n)):
            print(f"    [{_ts(base[i]['start'])}] {o1}: {d1[i]['text'][:46]}", flush=True)
            print(f"                 {o2}: {d2[i]['text'][:46]}", flush=True)
        print(f"  --- LAST 3 cues (後段 — drift would show here) ---", flush=True)
        for i in range(max(0, n-3), n):
            print(f"    [{_ts(base[i]['start'])}–{_ts(base[i]['end'])}] {o1}: {d1[i]['text'][:46]}", flush=True)
            print(f"                 {o2}: {d2[i]['text'][:46]}", flush=True)

        # write bilingual SRT (o1 top / o2 bottom)
        srt = []
        for i in range(n):
            srt.append(f"{i+1}\n{_ts(base[i]['start'])} --> {_ts(base[i]['end'])}\n{d1[i]['text']}\n{d2[i]['text']}\n")
        open(f"/tmp/o1_{tag}.srt", "w").write("\n".join(srt))
        print(f"  # wrote /tmp/o1_{tag}.srt ({n} paired cues)", flush=True)
        summary.append((tag, n, aligned, mono, e1, e2))

    print(f"\n{'='*72}\n## SUMMARY\n{'='*72}", flush=True)
    for tag, n, al, mo, e1, e2 in summary:
        print(f"  {tag}: cues={n} aligned={'✅' if al else '❌'} monotonic={mo} empties={e1}/{e2}", flush=True)


if __name__ == "__main__":
    main()
