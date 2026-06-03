"""Regenerate the zh track of given output_lang file entries with a given MT prompt
(reuses each entry's cached en content_asr_segments — no re-ASR). Used to apply the
de-raced 'sportsnews' generic prompt to the football clips while the racing clip keeps
the racing-winner prompt (demonstrating the per-style design).

Usage: PYTHONPATH=. python regen_clips_with_prompt.py <prompt_file> <fid1> [fid2 ...]
Run with :5001 STOPPED; restart after.
"""
import json
import re
import sys
import urllib.request

import output_lang_postprocess as olp

OLLAMA = "http://localhost:11434"
MT = "qwen3.5:35b-a3b-mlx-bf16"
REG = "data/registry.json"
TH = re.compile(r"<think>.*?</think>", re.S)
LB = re.compile(r"^(譯文|翻譯|Translation|出力)[:：]\s*")
LEAK = re.compile(r"[係嘅喺咗唔嗰哋睇佢嚟畀]")
RACE = re.compile(r"騎師|賽駒|馬匹|練馬師|頭馬|檔位|出閘|馬房|讓賽|策騎|跑馬")


def ollama(prompt, user):
    body = {"model": MT, "stream": False, "think": False,
            "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": user}],
            "options": {"temperature": 0.3}}
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode()).get("message", {}).get("content", "") or ""


def clean(raw):
    o = TH.sub("", raw or "").strip(); o = LB.sub("", o).strip()
    return o.splitlines()[0].strip() if o else ""


def main():
    prompt = open(sys.argv[1]).read()
    fids = sys.argv[2:]
    data = json.load(open(REG))
    files = data.get("files", data)
    for fid in fids:
        e = files.get(fid)
        if not e:
            print(f"SKIP {fid}: missing"); continue
        en_base = e.get("content_asr_segments") or []
        zh_raw = [{"start": s["start"], "end": s["end"],
                   "text": clean(ollama(prompt, s["text"])) if s["text"].strip() else ""} for s in en_base]
        zh = [z["text"] for z in olp.apply_script(zh_raw, "trad")]
        leak = sum(1 for z in zh if LEAK.search(z))
        race = sum(1 for z in zh if RACE.search(z))
        tr = e.get("translations") or []
        e["translations"] = [{**row, "by_lang": {**(row.get("by_lang") or {}),
                                                  "zh": {"text": (zh[i] if i < len(zh) else ""), "status": "pending", "flags": []}},
                              "zh_text": (zh[i] if i < len(zh) else "")} for i, row in enumerate(tr)]
        al = e.get("aligned_bilingual") or []
        e["aligned_bilingual"] = [{"start": c["start"], "end": c["end"],
                                   "by_lang": {**c.get("by_lang", {}), "zh": (zh[i] if i < len(zh) else "")}}
                                  for i, c in enumerate(al)]
        print(f"{fid} ({str(e.get('original_name'))[:24]}): {len(zh)} cues | leak={leak} racing_terms={race}", flush=True)
    json.dump(data, open(REG, "w"), ensure_ascii=False, indent=1)
    print("registry written", flush=True)


if __name__ == "__main__":
    main()
