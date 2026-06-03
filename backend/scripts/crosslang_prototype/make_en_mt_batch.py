"""Batch: process a few English clips with the validated MT method + WINNER prompt
(en ASR base + qwen3.5 1:1 MT(en->zh書面語), no refiner) and add them to the project
as new file entries, so the user can see the effect across diverse English content.

mlx large-v3 loaded once (reused across clips). Winner prompt: /tmp/mtopt_prompts/winner.txt.
Run with :5001 STOPPED; restart after.
Run: cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/make_en_mt_batch.py
"""
import json
import os
import re
import shutil
import time
import urllib.request
import uuid

import mlx_whisper
import output_lang_postprocess as olp

OLLAMA = "http://localhost:11434"
MT = "qwen3.5:35b-a3b-mlx-bf16"
REPO = "mlx-community/whisper-large-v3-mlx"
REG = "data/registry.json"
TEMPLATE_FID = "39fea6251836"
PROMPT = open("/tmp/mtopt_prompts/winner.txt").read()
F = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音"
CLIPS = [
    ("馬會騎師訪問（英文語音）", "賽馬騎師訪問[EN→中文書面語]"),
    ("Harry-Kane-Post-Match-Interview-Bayern（英文語音）", "哈利簡尼賽後訪問[EN→中文書面語]"),
    ("FIFA-Club-World-Cup-Interview （英文語音）", "FIFA世冠盃訪問[EN→中文書面語]"),
]
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
    template = files[TEMPLATE_FID]
    uploads = os.path.dirname(template["file_path"])
    summary = []
    for srcname, dispname in CLIPS:
        src_mp4 = f"{F}/{srcname}.mp4"
        if not os.path.exists(src_mp4):
            print(f"SKIP {srcname}: missing", flush=True); continue
        wav = f"/tmp/batch_{abs(hash(srcname)) % 99999}.wav"
        os.system(f'ffmpeg -y -i "{src_mp4}" -ar 16000 -ac 1 "{wav}" >/dev/null 2>&1')
        t0 = time.time()
        r = mlx_whisper.transcribe(wav, path_or_hf_repo=REPO, language="en", task="transcribe",
                                   condition_on_previous_text=False)
        en_base = [{"start": s["start"], "end": s["end"], "text": (s["text"] or "").strip()}
                   for s in r.get("segments", [])]
        print(f"[{dispname}] en ASR {len(en_base)} cues ({round(time.time()-t0,1)}s)", flush=True)
        t1 = time.time()
        zh_raw = [{"start": s["start"], "end": s["end"],
                   "text": clean(ollama(s["text"])) if s["text"].strip() else ""} for s in en_base]
        zh_segs = olp.apply_script(zh_raw, "trad")
        zh = [z["text"] for z in zh_segs]
        leak = sum(1 for z in zh if LEAK.search(z))
        print(f"   zh MT(winner) {len(zh)} cues ({round(time.time()-t1,1)}s) | leak={leak}/{len(zh)}", flush=True)

        newid = uuid.uuid4().hex[:12]
        new_media = os.path.join(uploads, f"{newid}.mp4")
        shutil.copy2(src_mp4, new_media)
        outs = ["en", "zh"]
        translations, segments, aligned = [], [], []
        for i, (eb, zt) in enumerate(zip(en_base, zh)):
            st, ed = eb["start"], eb["end"]
            translations.append({"idx": i, "start": st, "end": ed, "status": "pending",
                                 "by_lang": {"en": {"text": eb["text"], "status": "pending", "flags": []},
                                             "zh": {"text": zt, "status": "pending", "flags": []}},
                                 "en_text": eb["text"], "zh_text": zt})
            segments.append({"id": i, "start": st, "end": ed, "text": eb["text"], "words": []})
            aligned.append({"start": st, "end": ed, "by_lang": {"en": eb["text"], "zh": zt}})
        entry = {**template, "id": newid, "stored_name": f"{newid}.mp4", "file_path": new_media,
                 "original_name": f"{dispname}.mp4", "size": os.path.getsize(new_media),
                 "uploaded_at": time.time(), "source_language": "en", "output_languages": outs,
                 "script": "trad", "status": "done", "translation_status": "done",
                 "translation_kind": "output_lang", "active_kind": "output_lang",
                 "segments": segments, "translations": translations, "aligned_bilingual": aligned,
                 "content_asr_segments": en_base, "text": " ".join(s["text"] for s in segments),
                 "waveform_peaks": None}
        for stale in ("_pre_B_translations", "_pre_B_segments"):
            entry.pop(stale, None)
        files[newid] = entry
        summary.append((dispname, newid, len(en_base), leak))
        print(f"   NEW {newid}", flush=True)

    json.dump(data, open(REG, "w"), ensure_ascii=False, indent=1)
    print("\n=== SUMMARY ===", flush=True)
    for name, fid, n, leak in summary:
        print(f"  {fid}  {name}  {n} cues  leak={leak}/{n}", flush=True)


if __name__ == "__main__":
    main()
