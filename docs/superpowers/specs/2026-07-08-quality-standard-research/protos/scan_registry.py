import json, sys
REG = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/data/registry.json"
with open(REG) as f:
    reg = json.load(f)
print(f"total entries: {len(reg)}")
rows = []
for fid, e in reg.items():
    name = e.get("original_name", "")
    kind = e.get("active_kind") or e.get("pipeline_kind") or ""
    langs = e.get("languages") or e.get("output_languages") or []
    src = e.get("source_language", "")
    style = e.get("mt_style", "")
    gl = e.get("glossary_ids", [])
    n_tr = len(e.get("translations") or [])
    status = e.get("status", "")
    rows.append((fid, name[:52], kind, src, ",".join(langs) if isinstance(langs, list) else str(langs), style, len(gl), n_tr, status))
# filter interesting: racing / 馬會 / Test Footage
import re
for r in rows:
    if re.search(r"(?i)test.?footage|馬會|racing|winning|賽馬|賽後|騎師", r[1]) or r[5] == "racing":
        print("|".join(str(x) for x in r))
