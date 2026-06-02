"""Validation-First (B direction) — single shared-base 1:1 derivation across CONTENT
languages, using the EXACT production function B would adopt: output_lang_aligned.
derive_aligned_output (the O1 aligned derivation), now as the SINGLE source for ALL
outputs (display + export).

Closes the gaps the adversarial review flagged before reversing routing globally:
  gap ④  generalise beyond Cantonese — 普通話 (cmn) + 日文 (ja) content cells, incl.
         the known-asymmetric 普→yue (must yield REAL Cantonese, not Mandarin).
  gap ①  structural 1:1 — every derived output count == base count.
  gap ③  duplicate / sub-min-duration cue artifact at the base.
  (gap ② fidelity/register judged separately by LLM-judge on the saved full text.)

Per content clip: ONE base ASR (content_asr_lang) -> derive each realistic output via
derive_aligned_output(base, source, out, "trad", llm). Saves /tmp/drift_B_<tag>.json
(base + every output's full segments) for the fidelity judges.

Production stack: mlx large-v3 + Ollama qwen3.5:35b-a3b-mlx-bf16.
Run: cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/drift_fix_validation_B.py
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
import output_lang_aligned as ola              # noqa: E402  (the function B adopts)
from output_lang_router import content_asr_lang  # noqa: E402

REPO = "mlx-community/whisper-large-v3-mlx"
OLLAMA = "http://localhost:11434"
MT_MODEL = "qwen3.5:35b-a3b-mlx-bf16"
F = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音"
CLIP_SEC = int(os.environ.get("CLIP_SEC", "120"))
HALLU = re.compile(r"Amara|字幕|社羣|社群|訂閱|請按|like and sub", re.IGNORECASE)
YUE_MARK = re.compile(r"[係嘅咗喺唔嗰睇佢哋畀嘢冇]")   # Cantonese-specific markers
MIN_DUR = 0.3

# tag, file, source_language, [output langs to derive]
CLIPS = [
    ("yue", f"{F}/賽後兩點晚（中文語音）.mp4", "yue", ["yue", "zh", "en"]),
    ("cmn", f"{F}/阿土 YouTube 爆旋陀螺（普通話語音）.mp4", "cmn", ["cmn", "yue", "zh", "en"]),
    ("ja",  f"{F}/日本語音訪問片段馬會(日文語音）.mp4", "ja", ["ja", "en", "zh"]),
]


def _ollama(system, user):
    body = {"model": MT_MODEL, "stream": False, "think": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0.3}}
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode()).get("message", {}).get("content", "") or ""


def _short_cues(segs):
    return [(i, round(s["end"] - s["start"], 2), s["text"][:18])
            for i, s in enumerate(segs) if (s["end"] - s["start"]) < MIN_DUR]


def main():
    summary = []
    allout = {}
    for tag, clip, src, outs in CLIPS:
        wav = f"/tmp/drift_B_{tag}.wav"
        subprocess.run(["ffmpeg", "-y", "-i", clip, "-t", str(CLIP_SEC), "-ar", "16000", "-ac", "1", wav],
                       capture_output=True)
        print(f"\n{'='*72}\n## {tag}  source={src}  outputs={outs}  ({CLIP_SEC}s)\n{'='*72}", flush=True)
        t = time.time()
        wlang = content_asr_lang(src)
        r = mlx_whisper.transcribe(wav, path_or_hf_repo=REPO, language=wlang, task="transcribe",
                                   condition_on_previous_text=False)
        base = [{"start": s["start"], "end": s["end"], "text": (s["text"] or "").strip()}
                for s in r.get("segments", [])]
        bHall = [(i, s["text"][:26]) for i, s in enumerate(base[:5]) if HALLU.search(s["text"])]
        bShort = _short_cues(base)
        print(f"[base {wlang}] {len(base)} cues ({round(time.time()-t,1)}s) | head-hallu={bHall} | short(<{MIN_DUR}s)={len(bShort)}", flush=True)

        derived = {}
        for o in outs:
            t1 = time.time()
            mode = ola.derive_mode(src, o)
            d = ola.derive_aligned_output(base, src, o, "trad", _ollama)
            derived[o] = d
            note = ""
            if o == "yue":  # 普→yue must be REAL Cantonese
                hits = sum(1 for s in d if YUE_MARK.search(s["text"]))
                note = f" | cantonese-marker cues={hits}/{len(d)}"
            print(f"  -> {o} (mode={mode}): {len(d)} cues, 1:1={len(d)==len(base)} ({round(time.time()-t1,1)}s){note}", flush=True)

        ok = all(len(derived[o]) == len(base) for o in outs)
        print(f"  STRUCTURAL 1:1 (all outputs == base {len(base)}): {ok}", flush=True)
        print("  --- first 4 cues (base + each output) ---", flush=True)
        for i in range(min(4, len(base))):
            print(f"    [{round(base[i]['start'],1)}-{round(base[i]['end'],1)}] base={base[i]['text'][:24]!r}", flush=True)
            for o in outs:
                print(f"        {o}: {derived[o][i]['text'][:40]!r}", flush=True)

        allout[tag] = {"source": src, "base": base, "outputs": derived,
                       "base_hallu": bHall, "base_short": bShort, "structural_1to1": ok}
        json.dump(allout[tag], open(f"/tmp/drift_B_{tag}.json", "w"), ensure_ascii=False, indent=1)
        summary.append((tag, len(base), {o: len(derived[o]) for o in outs}, ok, bool(bHall), len(bShort)))

    print(f"\n{'='*72}\n## SUMMARY\n{'='*72}", flush=True)
    for tag, n, counts, ok, hall, nshort in summary:
        print(f"  {tag}: base={n} outs={counts} 1:1={ok} base_hallu={hall} short_cues={nshort}", flush=True)
    print("\n# wrote /tmp/drift_B_{yue,cmn,ja}.json", flush=True)


if __name__ == "__main__":
    main()
