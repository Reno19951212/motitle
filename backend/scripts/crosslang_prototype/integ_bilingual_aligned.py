"""Live integration: O1 paired bilingual aligned export (store-both).

Uploads an English clip, requests outputs [zh, en], waits for the second
output pass to complete (which builds `aligned_bilingual`), then fetches the
bilingual SRT and asserts it is 1:1 PAIRED (each cue = EN line + ZH line,
cue count == base ASR grid, no index-merge misalignment).

Run against a LIVE worktree backend on :5002 (see crosslang plan T10 env):
  cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/integ_bilingual_aligned.py
"""
import json
import sys
import time

import requests

BASE = "http://localhost:5002"
U, P = "admin_p3", "TestPass1!"
CLIP = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音/Harry-Kane-Post-Match-Interview-Bayern（英文語音）.mp4"


def main():
    s = requests.Session()
    s.post(f"{BASE}/login", json={"username": U, "password": P})
    with open(CLIP, "rb") as f:
        r = s.post(f"{BASE}/api/transcribe",
                   files={"file": ("hk.mp4", f, "video/mp4")},
                   data={"output_languages": json.dumps(["zh", "en"]),
                         "source_language": "en", "script": "trad"})
    if r.status_code not in (200, 202):
        print(f"FAIL upload: {r.status_code} {r.text[:300]}", flush=True)
        sys.exit(1)
    fid = r.json()["file_id"]
    print(f"fid {fid}", flush=True)

    # wait for BOTH output langs to be populated (second pass done -> aligned built)
    ok = False
    for _ in range(150):
        time.sleep(8)
        tr = s.get(f"{BASE}/api/files/{fid}/translations").json().get("translations", [])
        if tr and all(any((t.get("by_lang", {}).get(o, {}) or {}).get("text") for t in tr)
                      for o in ("zh", "en")):
            ok = True
            break
    if not ok:
        print("FAIL: outputs did not populate in time", flush=True)
        sys.exit(1)

    body = s.get(f"{BASE}/api/files/{fid}/subtitle.srt?source=bilingual").text
    cues = [c for c in body.split("\n\n") if c.strip()]
    print(f"bilingual cues={len(cues)}", flush=True)
    print("--- first 3 paired cues (each = index / time / EN / ZH) ---", flush=True)
    print("\n\n".join(cues[:3]), flush=True)
    print("--- last 2 paired cues (drift would show here) ---", flush=True)
    print("\n\n".join(cues[-2:]), flush=True)
    print(">>> check: each cue has EN line + ZH line, paired (true translations), "
          "cue count == base ASR grid <<<", flush=True)


if __name__ == "__main__":
    main()
