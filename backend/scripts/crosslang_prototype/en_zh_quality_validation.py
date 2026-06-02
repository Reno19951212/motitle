"""Validation-First — EN-content → ZH-output MT QUALITY (user's bound-ASR + 1:1 MT plan).

User decision: cross-language videos bind the CONTENT-language ASR as the base (accurate
timing) + 1:1 MT the rest with qwen3.5:35b. Open quality question for English videos:
the zh output via raw MT leans colloquial ('我係艾倫·艾特肯'), but the output is LABELLED
中文書面語. Does it need a 書面語 refine pass on top of MT to reach proper written register
— and does refine preserve fidelity (FORMAL broadcast content, unlike the casual cmn vlog
where refine distorted meaning)?

Compares, on Winning Factor (English formal broadcast):
  base   = en ASR (the bound base, authoritative timing)
  zh_mt        = MT(en->zh) + s2hk            [raw MT, 1:1]
  zh_mt_refine = MT(en->zh) + 書面語 refine + s2hk  [1:1]
Reconfirms drift (all == base count). Saves /tmp/en_zh_quality.json for quality judging.

Production stack: mlx large-v3 + Ollama qwen3.5:35b-a3b-mlx-bf16 (kept per user).
Run: cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/en_zh_quality_validation.py
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
F = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音"
CLIP = os.environ.get("CLIP_PATH") or f"{F}/The-Winning-Factor-Season 1 - （英文語音）.mp4"
CLIP_SEC = int(os.environ.get("CLIP_SEC", "150"))
CAP = 24


def _ollama(system, user):
    body = {"model": MT_MODEL, "stream": False, "think": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0.3}}
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode()).get("message", {}).get("content", "") or ""


def _chars(segs):
    L = sorted(len(s["text"]) for s in segs if s["text"].strip())
    if not L:
        return {"n": 0}
    return {"n": len(L), "median": L[len(L)//2], "max": L[-1],
            "over_cap_pct": round(100*sum(1 for x in L if x > CAP)/len(L), 1)}


def main():
    wav = "/tmp/en_zh_q.wav"
    subprocess.run(["ffmpeg", "-y", "-i", CLIP, "-t", str(CLIP_SEC), "-ar", "16000", "-ac", "1", wav],
                   capture_output=True)
    print(f"## EN->ZH quality — Winning Factor first {CLIP_SEC}s (English formal broadcast)\n", flush=True)

    t = time.time()
    r = mlx_whisper.transcribe(wav, path_or_hf_repo=REPO, language="en", task="transcribe",
                               condition_on_previous_text=False)
    base = [{"start": s["start"], "end": s["end"], "text": (s["text"] or "").strip()}
            for s in r.get("segments", [])]
    print(f"[base en ASR] {len(base)} cues ({round(time.time()-t,1)}s) — bound base, authoritative timing", flush=True)

    t = time.time()
    zh_mt = crosslang_mt.translate_segments(base, "en", "zh", _ollama)
    zh_mt = olp.apply_script(zh_mt, "trad")
    print(f"[zh_mt] MT(en->zh)+s2hk: {len(zh_mt)} cues ({round(time.time()-t,1)}s)", flush=True)

    t = time.time()
    zh_ref = crosslang_mt.translate_segments(base, "en", "zh", _ollama)
    zh_ref = olp.formal_refine(zh_ref, _ollama)
    zh_ref = olp.apply_script(zh_ref, "trad")
    print(f"[zh_mt_refine] MT+書面語 refine+s2hk: {len(zh_ref)} cues ({round(time.time()-t,1)}s)\n", flush=True)

    print("=" * 68)
    print(f"DRIFT: base={len(base)} zh_mt={len(zh_mt)} zh_refine={len(zh_ref)} -> 1:1 all equal? "
          f"{len(base)==len(zh_mt)==len(zh_ref)}")
    print(f"CHARS zh_mt    : {_chars(zh_mt)}")
    print(f"CHARS zh_refine: {_chars(zh_ref)}")
    print("=" * 68)
    print("\n--- paired sample (en base / zh_mt / zh_mt_refine) ---")
    for i in range(min(8, len(base))):
        print(f"  [{round(base[i]['start'],1)}] EN : {base[i]['text'][:50]}")
        print(f"        MT : {zh_mt[i]['text'][:40]}")
        print(f"        REF: {zh_ref[i]['text'][:40]}")

    json.dump({"clip": "WinningFactor", "content": "en", "sec": CLIP_SEC,
               "base_en": base, "zh_mt": zh_mt, "zh_mt_refine": zh_ref},
              open("/tmp/en_zh_quality.json", "w"), ensure_ascii=False, indent=1)
    print("\n# wrote /tmp/en_zh_quality.json", flush=True)


if __name__ == "__main__":
    main()
