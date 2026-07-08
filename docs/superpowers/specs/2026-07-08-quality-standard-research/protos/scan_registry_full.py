import json
REG = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/data/registry.json"
with open(REG) as f:
    reg = json.load(f)
for fid, e in reg.items():
    name = e.get("original_name","")
    kind = e.get("active_kind","")
    langs = e.get("languages") or []
    src = e.get("source_language","")
    style = e.get("mt_style","")
    gl = e.get("glossary_ids") or []
    tr = e.get("translations") or []
    n_ab = len(e.get("aligned_bilingual") or [])
    dur = tr[-1]["end"] if tr else 0
    keys = sorted(e.keys())
    print(f"{fid} | {name[:48]} | kind={kind} src={src} langs={langs} style={style} gl={gl} n_tr={len(tr)} n_aligned={n_ab} last_end={dur:.1f}s")
    # check render-related keys
    rk = [k for k in keys if "render" in k.lower()]
    if rk:
        for k in rk:
            v = e[k]
            print(f"    {k}: {json.dumps(v, ensure_ascii=False)[:300]}")
# show one translations row schema
sample = reg.get("f66d9705f78d", {})
tr = sample.get("translations") or []
if tr:
    print("\nSample translations row keys (f66d9705f78d):", sorted(tr[0].keys()))
    print(json.dumps(tr[0], ensure_ascii=False)[:600])
ab = sample.get("aligned_bilingual") or []
if ab:
    print("\nSample aligned_bilingual row:", json.dumps(ab[0], ensure_ascii=False)[:400])
