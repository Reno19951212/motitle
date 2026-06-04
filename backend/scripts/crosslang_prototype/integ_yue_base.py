#!/usr/bin/env python3
"""Integration — yue-source unified ASR-base, real mlx + real Ollama (2026-06-04).

Drives the NEW dispatch (_run_output_lang) directly with the production models on a
short real 毛記 clip, for the 3 confirmed flows:
  flow1  yue -> [zh]        書面單一
  flow2  yue -> [zh, yue]   書面 + 口語
  flow3  yue -> [zh, en]    書面 + 英文 (cross-language)

Asserts: ONE Whisper-yue ASR per file; 書面(zh) derived from the yue base (refined,
clean register); 口語(yue) track is the raw colloquial transcription (unchanged);
英文(en) is real MT; aligned_bilingual present for multi-output.

Side-effect-free: _save_registry is no-op'd; throwaway fids popped at the end.
Run: cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python scripts/crosslang_prototype/integ_yue_base.py
"""
import os, time, json
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as A

A._save_registry = lambda: None  # do not touch the on-disk registry

AUDIO = "/tmp/mokji_90s.wav"
_MARKERS = set("嘅係咗喺唔冇嗰呢㗎喎囉啦咩喇佢哋嘢乜嚟畀俾睇咁啲")
def mrate(t):
    t = t or ""
    return round(sum(1 for c in t if c in _MARKERS) / max(1, len(t)) * 100, 1)

def txt(row, lang):
    bl = row.get("by_lang") or {}
    v = bl.get(lang)
    return (v.get("text", "") if isinstance(v, dict) else (v or "")) or row.get(f"{lang}_text", "")

FLOWS = [("flow1_zh", ["zh"]), ("flow2_zh_yue", ["zh", "yue"]), ("flow3_zh_en", ["zh", "en"])]
results = {}

_orig_tx = A.transcribe_with_segments
for fid, outs in FLOWS:
    cnt = {"n": 0, "langs": []}
    def counting_tx(*a, **k):
        cnt["n"] += 1; cnt["langs"].append(k.get("lang_override"))
        return _orig_tx(*a, **k)
    A.transcribe_with_segments = counting_tx
    with A._registry_lock:
        A._file_registry[fid] = {"id": fid, "active_kind": "output_lang", "source_language": "yue",
                                 "script": "trad", "output_languages": outs, "mt_style": "generic"}
    t0 = time.time()
    try:
        A._run_output_lang(fid, {"user_id": 1, "id": "ij-" + fid}, AUDIO, None)
        e = A._file_registry[fid]
        tr = e.get("translations") or []
        al = e.get("aligned_bilingual") or []
        full = {o: "".join(txt(r, o) for r in tr) for o in outs}
        results[fid] = {
            "outs": outs, "status": e.get("status"), "segs": len(tr),
            "asr_calls": cnt["n"], "asr_langs": cnt["langs"], "secs": round(time.time() - t0, 1),
            "aligned": len(al),
            "marker_rate": {o: mrate(full[o]) for o in outs},
            "samples": [{o: txt(r, o) for o in outs} for r in tr[:6]],
        }
    except Exception as ex:
        results[fid] = {"error": repr(ex), "asr_calls": cnt["n"]}
    finally:
        A.transcribe_with_segments = _orig_tx
        with A._registry_lock:
            A._file_registry.pop(fid, None)

json.dump(results, open("/tmp/integ_yue_base.json", "w"), ensure_ascii=False, indent=2)

print("\n" + "=" * 72)
print("INTEGRATION — yue-source unified ASR-base (real mlx + Ollama, 90s 毛記 clip)")
print("=" * 72)
for fid, outs in FLOWS:
    r = results[fid]
    if "error" in r:
        print(f"\n{fid} {outs}: ERROR {r['error']}"); continue
    print(f"\n{fid}  outs={outs}  status={r['status']}  segs={r['segs']}  "
          f"ASR_calls={r['asr_calls']} (langs={r['asr_langs']})  aligned={r['aligned']}  {r['secs']}s")
    print(f"   marker/100 (口語高、書面低): {r['marker_rate']}")
    for s in r["samples"][:5]:
        print("   ", {o: (s[o][:34]) for o in outs})

# verdicts
print("\n── VERDICTS ──")
def ok(b): return "✅" if b else "❌"
f1, f2, f3 = results["flow1_zh"], results["flow2_zh_yue"], results["flow3_zh_en"]
print(ok(f1.get("status") == "done" and f1.get("asr_calls") == 1 and all(l == "yue" for l in f1.get("asr_langs", []))),
      "flow1: 書面單一 — done, ONE Whisper-yue ASR")
print(ok(f2.get("asr_calls") == 1 and f2.get("marker_rate", {}).get("yue", 0) > f2.get("marker_rate", {}).get("zh", 99)),
      "flow2: 書面+口語 — ONE shared yue ASR; 口語 marker-rate > 書面 marker-rate")
print(ok(f3.get("asr_calls") == 1 and f3.get("aligned", 0) == f3.get("segs", -1) and f3.get("segs", 0) > 0),
      "flow3: 書面+英文 — ONE yue ASR; aligned grid == segs")
print("\nfull JSON → /tmp/integ_yue_base.json")
