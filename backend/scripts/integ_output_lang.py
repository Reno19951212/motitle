"""T11 integration — real dual-Whisper-pass output_lang via the live HTTP API.

Uploads a real Cantonese broadcast clip with output_languages=["yue","en"],
waits for BOTH Whisper passes (first=yue口語+s2hk, second=en translate),
then verifies by_lang persistence + descriptor + export. Run with the backend
live on :5001.
"""
import json
import sys
import time

import requests

BASE = "http://localhost:5001"
CLIP = "/Users/renocheung/Downloads/香港警察結業會操（中文語音）.mp4"
USER, PW = "admin_p3", "TestPass1!"
DEADLINE = 600  # seconds for both passes


def main():
    s = requests.Session()
    r = s.post(f"{BASE}/login", json={"username": USER, "password": PW})
    print(f"[login] {r.status_code}", flush=True)
    if r.status_code != 200:
        print("LOGIN FAILED", r.text[:200]); sys.exit(1)

    with open(CLIP, "rb") as f:
        r = s.post(f"{BASE}/api/transcribe",
                   files={"file": ("police.mp4", f, "video/mp4")},
                   data={"output_languages": json.dumps(["yue", "en"])})
    print(f"[upload] {r.status_code} {r.text[:200]}", flush=True)
    if r.status_code != 202:
        print("UPLOAD FAILED"); sys.exit(1)
    fid = r.json()["file_id"]
    print(f"[file_id] {fid}", flush=True)

    t0 = time.time()
    yue_ok = en_ok = False
    last = None
    while time.time() - t0 < DEADLINE:
        time.sleep(8)
        tr = s.get(f"{BASE}/api/files/{fid}/translations")
        if tr.status_code != 200:
            continue
        rows = tr.json().get("translations", [])
        if not rows:
            fr = s.get(f"{BASE}/api/files/{fid}").json() if False else None
            continue
        by0 = rows[0].get("by_lang", {})
        yue_ok = any((r.get("by_lang", {}).get("yue", {}) or {}).get("text") for r in rows)
        en_ok = any((r.get("by_lang", {}).get("en", {}) or {}).get("text") for r in rows)
        st = f"rows={len(rows)} yue={yue_ok} en={en_ok} keys={list(by0)}"
        if st != last:
            print(f"[{int(time.time()-t0)}s] {st}", flush=True)
            last = st
        if yue_ok and en_ok:
            break

    print("\n===== RESULT =====", flush=True)
    files = s.get(f"{BASE}/api/files").json().get("files", [])
    entry = next((f for f in files if f["id"] == fid), {})
    print(f"status={entry.get('status')} active_kind={entry.get('active_kind')} "
          f"output_languages={entry.get('output_languages')}", flush=True)
    desc = s.get(f"{BASE}/api/files/{fid}/languages").json()
    print(f"descriptor={json.dumps(desc.get('languages', desc), ensure_ascii=False)}", flush=True)

    tr = s.get(f"{BASE}/api/files/{fid}/translations").json().get("translations", [])
    print(f"rows={len(tr)}  yue_ok={yue_ok}  en_ok={en_ok}", flush=True)
    if tr:
        r0 = tr[0]
        print(f"  row0.by_lang.yue.text = {((r0.get('by_lang',{}).get('yue',{}) or {}).get('text',''))[:60]!r}", flush=True)
        print(f"  row0.yue_text mirror  = {(r0.get('yue_text','') or '')[:60]!r}", flush=True)
        print(f"  row0.by_lang.en.text  = {((r0.get('by_lang',{}).get('en',{}) or {}).get('text',''))[:60]!r}", flush=True)
        print(f"  row0.en_text mirror   = {(r0.get('en_text','') or '')[:60]!r}", flush=True)

    # Export both sources
    for src in ("first", "second"):
        ex = s.get(f"{BASE}/api/files/{fid}/subtitle.srt?source={src}")
        body = ex.text if ex.status_code == 200 else f"ERR {ex.status_code}"
        head = body.split("\n\n")[0].replace("\n", " | ") if ex.status_code == 200 else body
        print(f"export[{src}] {ex.status_code}: {head[:90]}", flush=True)

    ok = yue_ok and en_ok and entry.get("status") == "done" and len(desc.get("languages", [])) == 2
    print(f"\n>>> INTEGRATION {'PASS' if ok else 'INCOMPLETE'} <<<", flush=True)
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
