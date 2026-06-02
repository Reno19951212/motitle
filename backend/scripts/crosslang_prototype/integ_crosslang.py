"""Live integration — cross-language routing, one clip per routing cell (2026-06-02).

Uploads real clips through the live HTTP API (worktree backend on :5002) and asserts
by_lang text + script per output language. Covers: whisper-direct (yue, cmn),
cross-language ASR+MT (yue→en), cross-DIALECT ASR+MT (cmn→yue — the key nuance),
and simplified script (en→zh simp). Run with the worktree backend live on :5002.
"""
import json
import sys
import time

import requests

BASE = "http://localhost:5002"
U, P = "admin_p3", "TestPass1!"
FOLDER = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音"

# (clip, source_language, [outputs], script, expect_substr_in_first_output_or_None)
CASES = [
    ("香港警察結業會操（中文語音）.mp4", "yue", ["yue", "en"], "trad", "嘅"),
    ("阿土 YouTube 爆旋陀螺（普通話語音）.mp4", "cmn", ["yue", "cmn"], "trad", "係"),
    ("Harry-Kane-Post-Match-Interview-Bayern（英文語音）.mp4", "en", ["zh"], "simp", None),
]
DEADLINE = 900


def main():
    s = requests.Session()
    r = s.post(f"{BASE}/login", json={"username": U, "password": P})
    print(f"[login] {r.status_code}", flush=True)
    ok_all = True
    for clip, src, outs, script, sub in CASES:
        with open(f"{FOLDER}/{clip}", "rb") as f:
            r = s.post(f"{BASE}/api/transcribe", files={"file": (clip, f, "video/mp4")},
                       data={"output_languages": json.dumps(outs),
                             "source_language": src, "script": script})
        if r.status_code != 202:
            print(f"[upload FAIL {r.status_code}] {r.text[:160]}", flush=True); ok_all = False; continue
        fid = r.json()["file_id"]
        print(f"\n[{clip[:18]}] src={src} outs={outs} script={script} fid={fid}", flush=True)
        t0 = time.time()
        while time.time() - t0 < DEADLINE:
            time.sleep(8)
            tr = s.get(f"{BASE}/api/files/{fid}/translations").json().get("translations", [])
            if tr and all(any((r0.get("by_lang", {}).get(o, {}) or {}).get("text") for r0 in tr) for o in outs):
                break
        tr = s.get(f"{BASE}/api/files/{fid}/translations").json().get("translations", [])
        elapsed = int(time.time() - t0)
        for o in outs:
            txt = next((r0["by_lang"][o]["text"] for r0 in tr
                        if (r0.get("by_lang", {}).get(o, {}) or {}).get("text")), "")
            print(f"   {o}: {txt[:64]}", flush=True)
        # descriptor + status
        files = s.get(f"{BASE}/api/files").json().get("files", [])
        entry = next((x for x in files if x["id"] == fid), {})
        print(f"   status={entry.get('status')} langs={[l['lang'] for l in entry.get('languages', [])]} "
              f"({elapsed}s, {len(tr)} rows)", flush=True)
        if sub:
            first_txt = " ".join((r0.get("by_lang", {}).get(outs[0], {}) or {}).get("text", "") for r0 in tr)
            if sub not in first_txt:
                print(f"   ✗ expected {sub!r} in {outs[0]} output", flush=True); ok_all = False
            else:
                print(f"   ✓ {sub!r} present in {outs[0]}", flush=True)
    print(f"\n>>> INTEGRATION {'OK' if ok_all else 'FAIL'} <<<", flush=True)
    sys.exit(0 if ok_all else 2)


if __name__ == "__main__":
    main()
