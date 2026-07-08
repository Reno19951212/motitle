"""B0 mechanical baseline — read-only scan of registry racing files.

Computes today's per-track mechanical quality numbers (no LLM):
  cue count / over-cap(>28) / marker-rate per 100 chars / empty / dup-runs /
  timing sanity (overlap, <0.4s) / glossary_changes count.
Marker set = union used by diag_yue_written_vs_direct.py + diag_refiner_deraced.py.
"""
import json

REG = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/data/registry.json"
MARKERS = set("嘅係咗喺唔冇嗰呢㗎喎囉啦咩喇佢哋嘢乜嚟畀俾睇咁攞嘥諗啲嘞冚揾邊")
FILES = {
    "f66d9705f78d": "馬會 Test Footage 1 (en→en,zh racing)",
    "28deab03a71c": "馬會 Test Footage 2 (en→en,zh racing)",
    "97b66062bfee": "Sha Tin race previews (en→en,zh racing, 851)",
    "09e0e3679f35": "研究 clip 沙田銀瓶 (yue→yue racing)",
    "48c1657e7ec1": "研究 clip 沙田銀瓶 (yue→zh racing)",
    "de5bd2b803bf": "袁幸堯新聞 (yue→zh racing)",
    "fb76532ed5bc": "賽後兩點晚 (yue→yue racing)",
    "ea49ef1969a9": "3K5k4QXhzVA (yue→zh racing, 1809)",
}

def marker_rate(t):
    if not t: return 0.0
    return round(sum(1 for c in t if c in MARKERS) / len(t) * 100, 2)

with open(REG) as f:
    reg = json.load(f)

out = {}
for fid, label in FILES.items():
    e = reg.get(fid)
    if not e: continue
    tr = e.get("translations") or []
    langs = sorted({l for r in tr for l in (r.get("by_lang") or {})})
    res = {"label": label, "n_cues": len(tr), "langs": langs, "tracks": {}}
    # timing sanity
    overlaps = sum(1 for a, b in zip(tr, tr[1:]) if b["start"] < a["end"] - 1e-6)
    short = sum(1 for r in tr if r["end"] - r["start"] < 0.4)
    res["timing"] = {"overlaps": overlaps, "cues_under_0.4s": short}
    n_glc = sum(len(r.get("glossary_changes") or []) for r in tr)
    res["glossary_changes_total"] = n_glc
    for lang in langs:
        texts = [ (r.get("by_lang") or {}).get(lang, {}).get("text", "") for r in tr ]
        empty = sum(1 for t in texts if not (t or "").strip())
        over28 = sum(1 for t in texts if len(t) > 28)
        over40 = sum(1 for t in texts if len(t) > 40)
        allchars = "".join(texts)
        mrate = marker_rate(allchars)
        # dup runs >=3 consecutive identical
        dup = 0; run = 1
        for a, b in zip(texts, texts[1:]):
            if a == b and a.strip(): run += 1
            else:
                if run >= 3: dup += run
                run = 1
        if run >= 3: dup += run
        res["tracks"][lang] = {"empty": empty, "over28": over28, "over40": over40,
                               "marker_per_100": mrate, "dup_run_cues": dup,
                               "total_chars": len(allchars)}
    out[fid] = res

print(json.dumps(out, ensure_ascii=False, indent=1))
with open("/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/.claude/worktrees/quality-standard/docs/superpowers/specs/2026-07-08-quality-standard-research/protos/baseline_mechanical_out.json", "w") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
