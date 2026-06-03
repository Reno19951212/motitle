"""Live integration (Phase 2): upload an English FOOTBALL clip (FIFA) with
mt_style=generic vs racing; assert generic → 0 racing-term contamination in the zh
output, racing → racing terms allowed; both 0 Cantonese leak. Demonstrates the style
picker end-to-end through the wired pipeline.

Run against a LIVE :5001 carrying Phase 2 code (restart first).
Run: cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/integ_style_phase2.py
"""
import json
import re
import sys
import time

import requests

BASE = "http://localhost:5001"
U, P = "admin_p3", "TestPass1!"
F = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音"
CLIP = "FIFA-Club-World-Cup-Interview （英文語音）.mp4"
RACE = re.compile(r"騎師|賽駒|馬匹|策騎|檔位|頭馬|練馬師")
LEAK = re.compile(r"[係嘅喺咗唔嗰哋睇佢嚟畀]")


def run(s, style):
    with open(f"{F}/{CLIP}", "rb") as fh:
        r = s.post(f"{BASE}/api/transcribe", files={"file": ("fifa.mp4", fh, "video/mp4")},
                   data={"output_languages": json.dumps(["en", "zh"]), "source_language": "en",
                         "script": "trad", "mt_style": style})
    fid = r.json()["file_id"]
    tr = []
    for _ in range(120):
        time.sleep(8)
        jr = s.get(f"{BASE}/api/files/{fid}/translations").json()
        tr = jr.get("translations", []) if isinstance(jr, dict) else []
        if tr and all((t.get("by_lang", {}).get("zh", {}) or {}).get("text") for t in tr):
            break
    race = sum(1 for t in tr if RACE.search((t.get("by_lang", {}).get("zh", {}) or {}).get("text", "")))
    leak = sum(1 for t in tr if LEAK.search((t.get("by_lang", {}).get("zh", {}) or {}).get("text", "")))
    # find the "the boys" cue if present
    sample = next((t for t in tr if "boys" in (t.get("by_lang", {}).get("en", {}) or {}).get("text", "").lower()), None)
    boys = (sample.get("by_lang", {}).get("zh", {}) or {}).get("text", "") if sample else "(no 'boys' cue)"
    print(f"  mt_style={style}: fid={fid} cues={len(tr)} racing_terms_in_zh={race} cantonese_leak={leak}", flush=True)
    print(f"     'the boys' -> {boys[:30]!r}", flush=True)
    return race, leak


def main():
    s = requests.Session()
    s.post(f"{BASE}/login", json={"username": U, "password": P})
    print("## generic (通用) — expect 0 racing terms on football", flush=True)
    g_race, g_leak = run(s, "generic")
    print("## racing (馬會賽馬) — racing terms allowed (style does not block them)", flush=True)
    r_race, r_leak = run(s, "racing")
    ok = (g_race == 0 and g_leak == 0 and r_leak == 0)
    print(f"\nVERDICT: {'PASS' if ok else 'FAIL'} — generic racing_terms={g_race}(expect 0), "
          f"leaks generic={g_leak}/racing={r_leak}(expect 0); racing racing_terms={r_race}(allowed)", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
