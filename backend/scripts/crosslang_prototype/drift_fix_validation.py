"""Validation-First: output_lang bilingual DRIFT root-cause + 2 fix directions (2026-06-02).

Reproducer: 賽後兩點晚（中文語音）— Cantonese content, outputs [zh 書面語, en].
Production showed: by_lang display drifts (en[i] not the translation of zh[i]) + a
Whisper head hallucination「字幕由 Amara.org 社羣提供」in the zh track.

Two fix directions to validate empirically (production stack: mlx large-v3 + Ollama qwen3.5):
  H2 — zh head hallucination: 粵→zh currently uses Whisper-DIRECT language=zh, which
       mis-fires on Cantonese intro. Does the CONTENT base (language=yue, cond=False)
       avoid it? Does yue-ASR + 書面語 refiner give clean zh of comparable quality?
  H1 — display drift: by_lang is two INDEPENDENT transcriptions index-merged. Does a
       SINGLE shared content base -> 1:1 derive (zh refine / en MT) give equal cue
       counts (structural zero-drift)? What is the single-language trade-off (cue length,
       over-cap) of base-grid refine vs whisper-direct, and does clause-split recover it?

Convergence hypothesis: routing 粵→zh through the shared yue base + refiner fixes BOTH
(no hallucination + same grid as en -> zero drift), at the cost of coarser cues unless
clause-split is applied to the single-language copy.

Run: cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/drift_fix_validation.py
Writes /tmp/drift_fix_validation.json + prints a quantified report.
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
from output_lang_router import whisper_direct_params, content_asr_lang  # noqa: E402

REPO = "mlx-community/whisper-large-v3-mlx"
OLLAMA = "http://localhost:11434"
MT_MODEL = "qwen3.5:35b-a3b-mlx-bf16"
FOLDER = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音"
CLIP = os.environ.get("CLIP_PATH") or f"{FOLDER}/賽後兩點晚（中文語音）.mp4"
CLIP_SEC = int(os.environ.get("CLIP_SEC", "120"))
CAP = 24  # single-language char cap reference (zh 書面語)
HALLU = re.compile(r"Amara|字幕|社羣|社群|提供|訂閱|請按|by\s", re.IGNORECASE)


def _ollama(system, user):
    body = {"model": MT_MODEL, "stream": False, "think": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0.3}}
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode()).get("message", {}).get("content", "") or ""


def _mlx(wav, lang):
    r = mlx_whisper.transcribe(wav, path_or_hf_repo=REPO, language=lang, task="transcribe",
                               condition_on_previous_text=False)
    return [{"start": s["start"], "end": s["end"], "text": (s["text"] or "").strip()}
            for s in r.get("segments", [])]


def _chars(segs):
    L = [len(s["text"]) for s in segs if s["text"].strip()]
    L.sort()
    if not L:
        return {"n": 0}
    med = L[len(L) // 2]
    over = sum(1 for x in L if x > CAP)
    return {"n": len(L), "median_chars": med, "max_chars": L[-1],
            "over_cap_pct": round(100 * over / len(L), 1)}


def _hallu_head(segs, n=4):
    hits = []
    for i, s in enumerate(segs[:n]):
        if HALLU.search(s["text"]):
            hits.append((i, round(s["start"], 1), round(s["end"], 1), s["text"][:30]))
    return hits


def _head_durs(segs, n=3):
    return [round(s["end"] - s["start"], 1) for s in segs[:n]]


def main():
    wav = "/tmp/drift_fix.wav"
    subprocess.run(["ffmpeg", "-y", "-i", CLIP, "-t", str(CLIP_SEC), "-ar", "16000", "-ac", "1", wav],
                   capture_output=True)
    print(f"## DRIFT-FIX VALIDATION — 賽後兩點晚 first {CLIP_SEC}s (Cantonese; outputs zh書面語 + en)\n", flush=True)
    out = {}

    # --- A: CURRENT 粵→zh route = Whisper-DIRECT language=zh ---
    t = time.time()
    A = _mlx(wav, whisper_direct_params("zh")["lang_override"])  # 'zh'
    out["A_whisper_direct_zh"] = A
    print(f"[A] whisper-DIRECT zh (current 粵→zh): {len(A)} cues ({round(time.time()-t,1)}s)", flush=True)

    # --- B: CONTENT base = language=yue (cantonese), cond=False ---
    t = time.time()
    B = _mlx(wav, content_asr_lang("yue"))  # 'yue'
    out["B_yue_base"] = B
    print(f"[B] yue content base: {len(B)} cues ({round(time.time()-t,1)}s)", flush=True)

    # --- C: zh via aligned approach = B -> 書面語 refine (1:1) ---
    t = time.time()
    C = olp.formal_refine(B, _ollama)
    C = olp.apply_script(C, "trad")
    out["C_zh_refine_from_base"] = C
    print(f"[C] zh = refine(yue base) [aligned, no clause-split]: {len(C)} cues ({round(time.time()-t,1)}s)", flush=True)

    # --- C': single-language zh from aligned base WITH clause-split ---
    Cs = olp.clause_split_all(C, char_cap=18)
    out["Cp_zh_refine_clausesplit"] = Cs
    print(f"[C'] zh single-lang = refine + clause_split(18): {len(Cs)} cues", flush=True)

    # --- D: en via aligned approach = B -> MT(yue->en) (1:1) ---
    t = time.time()
    D = crosslang_mt.translate_segments(B, "yue", "en", _ollama)
    out["D_en_mt_from_base"] = D
    print(f"[D] en = MT(yue base -> en) [aligned]: {len(D)} cues ({round(time.time()-t,1)}s)\n", flush=True)

    # ===== METRICS =====
    print("=" * 70)
    print("## H2 — zh head hallucination")
    print("=" * 70)
    aH = _hallu_head(A); bH = _hallu_head(B); cH = _hallu_head(C)
    print(f"  A whisper-direct-zh  head hallucination hits: {aH}")
    print(f"  A head cue durations (s): {_head_durs(A)}   <- coarse blocks = hallucination")
    print(f"  B yue base           head hallucination hits: {bH}")
    print(f"  B head cue durations (s): {_head_durs(B)}")
    print(f"  C refine(yue base)   head hallucination hits: {cH}")
    print(f"  VERDICT H2: whisper-direct-zh hallucinates={bool(aH)} ; yue-base clean={not bH} ; refine clean={not cH}")

    print("\n" + "=" * 70)
    print("## H1 — display drift (counts must MATCH for zero-drift)")
    print("=" * 70)
    print(f"  CURRENT by_lang (independent): zh=A({len(A)}) vs en(independent yue-ASR+MT, ~{len(D)} from base)")
    print(f"    -> count divergence A vs base = {len(A)-len(B)} cues (index-merge offset source)")
    print(f"  ALIGNED (shared base): zh=C({len(C)}) en=D({len(D)}) base=B({len(B)})")
    print(f"    -> aligned counts equal? C==D==B : {len(C)==len(D)==len(B)}  (structural zero-drift)")

    print("\n" + "=" * 70)
    print("## Single-language zh quality trade-off (whisper-direct A vs aligned-base C / C')")
    print("=" * 70)
    print(f"  A whisper-direct-zh : {_chars(A)}")
    print(f"  C refine (no split) : {_chars(C)}")
    print(f"  C' refine + split   : {_chars(Cs)}")

    print("\n--- sample: A (whisper-direct zh, current) head ---")
    for s in A[:5]:
        print(f"    [{round(s['start'],1)}-{round(s['end'],1)}] {s['text'][:42]!r}")
    print("--- sample: C (refine from yue base) head ---")
    for s in C[:5]:
        print(f"    [{round(s['start'],1)}-{round(s['end'],1)}] {s['text'][:42]!r}")
    print("--- sample: aligned bilingual (C zh / D en) paired head ---")
    for i in range(min(5, len(C), len(D))):
        print(f"    [{round(C[i]['start'],1)}-{round(C[i]['end'],1)}] zh={C[i]['text'][:26]!r} en={D[i]['text'][:34]!r}")

    json.dump(out, open("/tmp/drift_fix_validation.json", "w"), ensure_ascii=False, indent=1)
    print("\n# wrote /tmp/drift_fix_validation.json", flush=True)


if __name__ == "__main__":
    main()
