import json
REG = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/data/registry.json"
with open(REG) as f:
    reg = json.load(f)
e = reg["f66d9705f78d"]
print("f66d9705f78d keys:", sorted(e.keys()))
print("stored_name:", e.get("stored_name"), "| path:", e.get("path") or e.get("file_path"))
for fid in ["28deab03a71c", "97b66062bfee"]:
    ee = reg[fid]
    print(fid, "stored:", ee.get("stored_name"), "path:", ee.get("path") or ee.get("file_path"))
# any render job info anywhere?
import re
txt = json.dumps(reg)
print("renders mentioned:", len(re.findall(r'render', txt)))
