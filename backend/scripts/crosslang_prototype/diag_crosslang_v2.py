"""Re-validation v2 — Mandarin (普通話) source + new output variables (2026-06-02).

Adds the dimensions raised after v1:
  - NEW source language 普通話 (Mandarin audio) → Whisper ASR `language=zh`.
  - The within-Chinese cross-DIALECT nuance: 普通話內容 → 口語廣東話 output —
    Whisper-direct (force `language=yue` on Mandarin audio) vs ASR(zh)+MT(zh→yue).
  - Mandarin cross outputs 普→en / 普→ja (ASR+MT).
  - 普通話 output (Whisper zh raw) vs 中文書面語 (zh + V6 formal-register refiner).
  - 簡體 script (OpenCC: Whisper zh native = Simplified; s2hk = 繁HK).

Reuses v1 helpers. Production stack: mlx-whisper large-v3 + Ollama qwen3.5:35b.
Run:  cd backend && PYTHONPATH=. python scripts/crosslang_prototype/diag_crosslang_v2.py
Writes /tmp/crosslang_mando.json.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from diag_crosslang import (  # noqa: E402
    whisper_pass, asr_mt, _ollama, metrics, judge, s2hk, clip_wav, FOLDER, CLIP_SEC,
)

MANDO_CLIP = "阿土 YouTube 爆旋陀螺（普通話語音）.mp4"

# V6 written-register refiner (粵/中口語 → 正式繁體書面語) — already validated in V6 work.
_REFINER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "config", "prompt_templates_v5", "refiner", "zh_written_register_v6.json",
)
_REFINER_SYS = json.load(open(_REFINER_PATH))["system_prompt"]


def refine_written(segs):
    """Apply the V6 formal-register refiner per segment (中文書面語 output)."""
    out = []
    t0 = time.time()
    for s in segs:
        raw = _ollama(_REFINER_SYS, s["text"]) if s["text"].strip() else ""
        # refiner may emit {"action":..,"text":..} JSON — extract text if so
        txt = raw
        if raw.startswith("{"):
            try:
                txt = json.loads(raw).get("text", raw)
            except Exception:
                txt = raw
        out.append({"start": s["start"], "end": s["end"], "text": s2hk(txt)})
    return out, round(time.time() - t0, 1)


def main():
    wav = "/tmp/clx_mando.wav"
    clip_wav(f"{FOLDER}/{MANDO_CLIP}", wav)
    print(f"\n{'='*72}\n## CONTENT=普通話 (Mandarin) clip={MANDO_CLIP[:24]} {CLIP_SEC}s\n{'='*72}", flush=True)

    # Source ASR: Mandarin audio → Whisper language=zh (native). Keep繁 for readability.
    asr_zh, t = whisper_pass(wav, "zh", "transcribe", do_s2hk=True)
    print(f"[ASR zh on Mandarin audio] {len(asr_zh)} segs {t}s (MT source + judge ref)\n   e.g. {asr_zh[0]['text'][:60] if asr_zh else '(empty)'}", flush=True)

    R = {"content": "cmn", "clip": MANDO_CLIP, "clip_sec": CLIP_SEC, "asr_n": len(asr_zh), "cells": {}}

    # 普→普通話 : Whisper zh raw (same-dialect, native) — expected excellent baseline.
    j = judge(asr_zh, asr_zh, "zh")
    R["cells"]["普通話_raw"] = {"method": "whisper-zh raw (=ASR)", "metrics": metrics(asr_zh, True),
                               "judge": j, "sample": [s["text"] for s in asr_zh[:3]]}
    print(f"\n-- 普→普通話 (Whisper zh raw) judge={j}\n   {[s['text'][:40] for s in asr_zh[:2]]}", flush=True)

    # 普→中文書面語 : zh base + V6 formal-register refiner.
    refined, rt = refine_written(asr_zh)
    jr = judge(asr_zh, refined, "zh")
    R["cells"]["中文書面語_refined"] = {"method": "whisper-zh + V6 formal refiner", "secs": rt,
                                       "metrics": metrics(refined, True), "judge": jr,
                                       "sample": [s["text"] for s in refined[:3]]}
    print(f"\n-- 普→中文書面語 (+formal refiner {rt}s) judge={jr}\n   {[s['text'][:40] for s in refined[:2]]}", flush=True)

    # ★ NUANCE 普→口語廣東話 : A whisper-direct (force yue on Mandarin) vs B ASR(zh)+MT(zh→yue)
    a_segs, at = whisper_pass(wav, "yue", "transcribe", do_s2hk=True)
    am, aj = metrics(a_segs, True), judge(asr_zh, a_segs, "yue")
    b_segs, bt = asr_mt(asr_zh, "普通話/中文", "yue")
    bm, bj = metrics(b_segs, True), judge(asr_zh, b_segs, "yue")
    R["cells"]["口語廣東話_cross"] = {
        "A_whisper_direct": {"secs": at, "metrics": am, "judge": aj, "sample": [s["text"] for s in a_segs[:3]]},
        "B_asr_mt":         {"secs": bt, "metrics": bm, "judge": bj, "sample": [s["text"] for s in b_segs[:3]]},
    }
    print(f"\n== ★ 普→口語廣東話 (cross-dialect nuance) ==", flush=True)
    print(f"  A whisper-direct(force yue) judge={aj}\n     {[s['text'][:45] for s in a_segs[:3]]}", flush=True)
    print(f"  B ASR(zh)+MT(zh→yue)        judge={bj}\n     {[s['text'][:45] for s in b_segs[:3]]}", flush=True)

    # 普→英文 / 普→日文 : cross → ASR+MT (judge unreliable for en/ja → rely on samples)
    for code in ("en", "ja"):
        seg, tt = asr_mt(asr_zh, "普通話/中文", code)
        R["cells"][f"{code}_cross"] = {"method": "ASR(zh)+MT", "secs": tt,
                                       "metrics": metrics(seg, code == "ja"),
                                       "judge": judge(asr_zh, seg, code),
                                       "sample": [s["text"] for s in seg[:3]]}
        print(f"\n== 普→{code} (ASR+MT) ==\n   {[s['text'][:55] for s in seg[:3]]}", flush=True)

    # 簡體 script check: Whisper zh native (no s2hk) should be Simplified.
    simp, _ = whisper_pass(wav, "zh", "transcribe", do_s2hk=False)
    R["cells"]["簡體_check"] = {"method": "whisper-zh no-s2hk (native Simplified)",
                               "sample": [s["text"] for s in simp[:3]]}
    print(f"\n-- 簡體 (Whisper zh native, no s2hk)\n   {[s['text'][:40] for s in simp[:2]]}", flush=True)

    json.dump(R, open("/tmp/crosslang_mando.json", "w"), ensure_ascii=False, indent=2)
    print("\n# wrote /tmp/crosslang_mando.json", flush=True)


if __name__ == "__main__":
    main()
