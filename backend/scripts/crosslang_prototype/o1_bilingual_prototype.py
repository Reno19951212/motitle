"""O1 prototype — high-quality paired bilingual via ONE base ASR + 1:1 derivation.

Approach O1 (vs current index-merge): transcribe the CONTENT language once -> base
cues; derive every output language as a 1:1 transform of that base (cross-lang = MT,
書面語 = +formal refiner). Because all outputs share the base boundaries, paired
bilingual cue[i] = (en[i], zh[i]) aligns PERFECTLY — no index-zip, no truncation.
clause-split is applied ONLY to the single-language copy (readability), never the
bilingual one.

Demonstrates on real English content (Winning Factor) -> en + zh書面語, prints stats
+ samples, and writes an aligned bilingual SRT to /tmp/o1_bilingual.srt. Also shows
the divergence the CURRENT pipeline mishandles (clause-split zh count > en count).

Production stack: mlx-whisper large-v3 + Ollama qwen3.5:35b-a3b-mlx-bf16.
Run: cd backend && PYTHONPATH=. python scripts/crosslang_prototype/o1_bilingual_prototype.py
"""
import json
import os
import re
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
CLIP = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音/The-Winning-Factor-Season 1 - （英文語音）.mp4"
CLIP_SEC = int(os.environ.get("CLIP_SEC", "150"))


def _ollama(system, user):
    body = {"model": MT_MODEL, "stream": False, "think": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0.3}}
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode()).get("message", {}).get("content", "") or ""


def _srt_ts(sec):
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = int(sec % 60); ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    wav = "/tmp/o1_wf.wav"
    subprocess.run(["ffmpeg", "-y", "-i", CLIP, "-t", str(CLIP_SEC), "-ar", "16000", "-ac", "1", wav],
                   capture_output=True)
    print(f"## O1 bilingual prototype — Winning Factor {CLIP_SEC}s (English content -> en + zh書面語)\n", flush=True)

    # 1) ONE base ASR (content language = en)
    t0 = time.time()
    r = mlx_whisper.transcribe(wav, path_or_hf_repo=REPO, language="en", task="transcribe",
                               condition_on_previous_text=False)
    en_base = [{"start": s["start"], "end": s["end"], "text": (s["text"] or "").strip()}
               for s in r.get("segments", [])]
    print(f"[1] en base ASR: {len(en_base)} cues ({round(time.time()-t0,1)}s) — shared timeline\n", flush=True)

    # 2) zh = 1:1 MT of the SAME base + formal refiner + s2hk (count preserved at each step)
    t1 = time.time()
    zh_1to1 = crosslang_mt.translate_segments(en_base, "en", "zh", _ollama)
    zh_1to1 = olp.formal_refine(zh_1to1, _ollama)
    zh_1to1 = olp.apply_script(zh_1to1, "trad")
    print(f"[2] zh 1:1 (MT+refiner+s2hk): {len(zh_1to1)} cues ({round(time.time()-t1,1)}s)", flush=True)

    # 3) single-language zh copy gets clause-split (readability) — this DIVERGES in count
    zh_single = olp.clause_split_all(zh_1to1, char_cap=18)
    print(f"[3] zh single-lang (clause-split copy): {len(zh_single)} cues", flush=True)

    aligned = (len(en_base) == len(zh_1to1))
    print(f"\n=== ALIGNMENT ===")
    print(f"  O1 paired bilingual: en={len(en_base)} == zh_1to1={len(zh_1to1)} -> {'PERFECT 1:1 ✅' if aligned else 'MISMATCH ❌'}")
    print(f"  Current pipeline would clause-split zh -> {len(zh_single)} cues vs en {len(en_base)} "
          f"-> index-merge diverges by {len(zh_single)-len(en_base)} cues (misalign/truncate)\n", flush=True)

    # 4) sample paired cues (O1) — each cue both languages, same time
    print("=== O1 paired bilingual sample (cue = en top / zh bottom, shared timing) ===", flush=True)
    for i in range(min(6, len(en_base))):
        print(f"  #{i+1} [{_srt_ts(en_base[i]['start'])}–{_srt_ts(en_base[i]['end'])}]", flush=True)
        print(f"     EN: {en_base[i]['text'][:70]}", flush=True)
        print(f"     ZH: {zh_1to1[i]['text'][:70]}", flush=True)

    # 5) contrast: what the CURRENT index-merge would pair (en[i] vs clause-split zh[i])
    print("\n=== CURRENT index-merge would WRONGLY pair (en[i] vs clause-split zh[i]) ===", flush=True)
    for i in range(3, min(6, len(zh_single))):
        print(f"  row{i+1}: EN={en_base[i]['text'][:42] if i < len(en_base) else '(blank/exhausted)'!r}", flush=True)
        print(f"          ZH={zh_single[i]['text'][:42]!r}  <- clause-split fragment, NOT the translation of this EN", flush=True)

    # 6) write aligned bilingual SRT (O1)
    out = []
    for i, (e, z) in enumerate(zip(en_base, zh_1to1), 1):
        out.append(f"{i}\n{_srt_ts(e['start'])} --> {_srt_ts(e['end'])}\n{e['text']}\n{z['text']}\n")
    open("/tmp/o1_bilingual.srt", "w").write("\n".join(out))
    print(f"\n# wrote /tmp/o1_bilingual.srt ({len(en_base)} paired cues)", flush=True)
    json.dump({"en": en_base, "zh_1to1": zh_1to1, "zh_single_count": len(zh_single)},
              open("/tmp/o1_bilingual.json", "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
