"""Regenerate the MT-method WF entry (39fea6251836) zh track using the WINNING
MT prompt (checklist) from the prompt-optimisation workflow, so the user can compare
old-prompt (b70ce) vs new-prompt (39fea) in the project. en base reused (no re-ASR).

Winner prompt: /tmp/mtopt_prompts/winner.txt (also docs/superpowers/specs/2026-06-02-mt-prompt-winner-checklist.txt).
Run with :5001 STOPPED; restart after.
Run: cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/regen_wf_winner_prompt.py
"""
import json
import re
import urllib.request

import output_lang_postprocess as olp

OLLAMA = "http://localhost:11434"
MT = "qwen3.5:35b-a3b-mlx-bf16"
REG = "data/registry.json"
FID = "39fea6251836"
PROMPT = open("/tmp/mtopt_prompts/winner.txt").read()
TH = re.compile(r"<think>.*?</think>", re.S)
LB = re.compile(r"^(譯文|翻譯|Translation|出力)[:：]\s*")
LEAK = re.compile(r"[係嘅喺咗唔嗰哋睇佢嚟畀]")


def ollama(user):
    body = {"model": MT, "stream": False, "think": False,
            "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}],
            "options": {"temperature": 0.3}}
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode()).get("message", {}).get("content", "") or ""


def clean(raw):
    o = TH.sub("", raw or "").strip(); o = LB.sub("", o).strip()
    return o.splitlines()[0].strip() if o else ""


def main():
    data = json.load(open(REG))
    files = data.get("files", data)
    e = files[[k for k in files if k.startswith(FID)][0]]
    en_base = e.get("content_asr_segments") or []
    assert en_base, "no en base"
    print(f"regen zh for {FID} with WINNER prompt: {len(en_base)} cues", flush=True)

    zh_txt = []
    for s in en_base:
        en = (s.get("text") or "").strip()
        zh_txt.append(clean(ollama(en)) if en else "")
    zh_segs = olp.apply_script([{"start": s["start"], "end": s["end"], "text": t}
                                for s, t in zip(en_base, zh_txt)], "trad")
    zh = [z["text"] for z in zh_segs]
    leak = sum(1 for z in zh if LEAK.search(z))
    print(f"done | cantonese-leak cues={leak}/{len(zh)}", flush=True)

    tr = e.get("translations") or []
    new_tr = []
    for i, row in enumerate(tr):
        zt = zh[i] if i < len(zh) else ""
        nbl = {**(row.get("by_lang") or {}), "zh": {"text": zt, "status": "pending", "flags": []}}
        new_tr.append({**row, "by_lang": nbl, "zh_text": zt})
    e["translations"] = new_tr
    al = e.get("aligned_bilingual") or []
    e["aligned_bilingual"] = [{"start": c["start"], "end": c["end"],
                               "by_lang": {**c.get("by_lang", {}), "zh": (zh[i] if i < len(zh) else "")}}
                              for i, c in enumerate(al)]
    e["original_name"] = "The-Winning-Factor（新prompt書面語）.mp4"
    json.dump(data, open(REG, "w"), ensure_ascii=False, indent=1)
    print(f"updated {FID} zh with winner prompt", flush=True)
    print("--- sample (compare vs old 我係艾倫/喺呢個) ---", flush=True)
    for i in range(min(4, len(en_base))):
        print(f"  EN: {en_base[i]['text'][:46]}", flush=True)
        print(f"  ZH: {zh[i][:40]}", flush=True)


if __name__ == "__main__":
    main()
