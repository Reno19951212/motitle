"""Live integration: re-process yue->[zh,en] (賽後) + en->[en,zh] (WF) through the NEW
cross-language single-pass path; assert display by_lang grid is the SAME grid as
aligned_bilingual (paired, 0 drift) + 0 Cantonese leak + no Amara hallucination.

Run against a LIVE :5001 backend carrying the Phase 1 code (restart it first).
Run: cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/integ_crosslang_phase1.py
"""
import json
import re
import sys
import time

import requests

BASE = "http://localhost:5001"
U, P = "admin_p3", "TestPass1!"
F = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音"
LEAK = re.compile(r"[係嘅喺咗唔嗰哋睇佢嚟畀]")
AMARA = re.compile(r"Amara|字幕由|社羣|社群")
CLIPS = [("賽後兩點晚（中文語音）.mp4", "yue", ["zh", "en"]),
         ("The-Winning-Factor-Season 1 - （英文語音）.mp4", "en", ["en", "zh"])]


def main():
    s = requests.Session()
    s.post(f"{BASE}/login", json={"username": U, "password": P})
    ok_all = True
    for clip, src, outs in CLIPS:
        with open(f"{F}/{clip}", "rb") as fh:
            r = s.post(f"{BASE}/api/transcribe", files={"file": (clip, fh, "video/mp4")},
                       data={"output_languages": json.dumps(outs), "source_language": src, "script": "trad"})
        if r.status_code not in (200, 202):
            print(f"FAIL upload {clip}: {r.status_code} {r.text[:200]}", flush=True)
            ok_all = False
            continue
        fid = r.json()["file_id"]
        print(f"\n## {clip} src={src} outs={outs} -> {fid}", flush=True)
        tr = []
        for _ in range(160):
            time.sleep(8)
            jr = s.get(f"{BASE}/api/files/{fid}/translations").json()
            tr = jr.get("translations", []) if isinstance(jr, dict) else []
            if tr and all(any((t.get("by_lang", {}).get(o, {}) or {}).get("text") for t in tr) for o in outs):
                break
        if not tr:
            print("  FAIL: no translations", flush=True); ok_all = False; continue
        n = len(tr)
        leak = sum(1 for t in tr for o in outs if LEAK.search((t.get("by_lang", {}).get(o, {}) or {}).get("text", "")))
        amara = sum(1 for t in tr for o in outs if AMARA.search((t.get("by_lang", {}).get(o, {}) or {}).get("text", "")))
        paired = all(all((t.get("by_lang", {}).get(o, {}) or {}).get("text") for o in outs) for t in tr)
        # display(by_lang) grid == aligned grid?  fetch aligned via bilingual export cue count
        body = s.get(f"{BASE}/api/files/{fid}/subtitle.srt?source=bilingual").text
        cues = len([c for c in body.split("\n\n") if c.strip()])
        print(f"  cues(by_lang)={n} bilingual_export_cues={cues} paired={paired} "
              f"cantonese_leak={leak} amara_hallucination={amara}", flush=True)
        print("  first 2 paired rows:", flush=True)
        for t in tr[:2]:
            print(f"    {outs[0]}={(t.get('by_lang',{}).get(outs[0],{}) or {}).get('text','')[:30]!r}  "
                  f"{outs[1]}={(t.get('by_lang',{}).get(outs[1],{}) or {}).get('text','')[:34]!r}", flush=True)
        if not paired or leak or amara or cues != n:
            ok_all = False
    print(f"\n{'='*60}\nVERDICT: {'PASS ✅' if ok_all else 'FAIL ❌'} "
          f"(expect: paired=True, leak=0, amara=0, by_lang cues == bilingual export cues)", flush=True)
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
