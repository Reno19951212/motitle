"""scan_track perf 基準 — 真 851-cue 檔 × 真 1353 條術語表。
用法: scan_bench.py <snapshot_out.json>
Snapshot 內容: 兩條軌嘅 scan_track 完整輸出 + 逐軌時間。用嚟證明 perf 修改前後結果 byte-identical。"""
import json, sys, time, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__ if '__file__' in dir() else '.')), ''))
BACKEND = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
sys.path.insert(0, BACKEND)
from output_lang_glossary import scan_track
from output_lang_router import content_asr_lang
from output_lang_aligned import derive_mode

reg = json.load(open(os.path.join(BACKEND, "data/registry.json")))
e = reg["97b66062bfee"]
rows = e.get("translations") or []
content_segs = e.get("content_asr_segments") or []
glo = [json.load(open(os.path.join(BACKEND, "config/glossaries/db323f9d-8f1e-44da-a20f-64d1ace09b89.json")))]
content_lang = content_asr_lang(e.get("source_language") or "en")
src_texts = [s.get("text", "") for s in content_segs]
approved = [(r.get("status") == "approved") for r in rows]

out = {"tracks": {}, "timing": {}}
for lang in e.get("output_languages"):
    texts = [((r.get("by_lang") or {}).get(lang) or {}).get("text") or r.get(f"{lang}_text") or "" for r in rows]
    mode = derive_mode(content_lang, lang)
    t0 = time.time()
    trk = scan_track(texts=texts, src_texts=src_texts if mode == "mt" else None,
                     glossaries=glo, output_lang=lang, content_lang=content_lang,
                     derive_mode=mode, approved=approved)
    dt = time.time() - t0
    out["tracks"][lang] = trk
    out["timing"][lang] = round(dt, 2)
    print(f"track {lang} (mode={mode}): {dt:.1f}s, {len(trk['items'])} items", flush=True)

json.dump(out["tracks"], open(sys.argv[1], "w"), ensure_ascii=False, sort_keys=True)
print("TOTAL:", round(sum(out["timing"].values()), 1), "s | snapshot →", sys.argv[1])
