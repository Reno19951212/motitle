"""Produce a NEW Winning Factor file entry using the validated MT method, for the
user to compare IN THE PROJECT:
  first language  = English (the bound content ASR base — authoritative timing)
  second language = 中文書面語 (zh) via qwen3.5 1:1 MT(en->zh) + s2hk, NO refiner.

Reuses the existing WF (b70ce) en content-ASR base (content_asr_segments) so no
re-transcribe — only the MT step runs. Copies the media to a new id, writes a new
registry entry (status=done). Run with the :5001 backend STOPPED; restart after.

Run: cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/make_wf_mt_entry.py
"""
import json
import os
import shutil
import urllib.request
import uuid

from translation import crosslang_mt
import output_lang_postprocess as olp

OLLAMA = "http://localhost:11434"
MT_MODEL = "qwen3.5:35b-a3b-mlx-bf16"
REG = "data/registry.json"
SRC_PREFIX = "b70ce2687ed5"


def _ollama(system, user):
    body = {"model": MT_MODEL, "stream": False, "think": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0.3}}
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode()).get("message", {}).get("content", "") or ""


def main():
    data = json.load(open(REG))
    files = data.get("files", data)
    src = files[[k for k in files if k.startswith(SRC_PREFIX)][0]]
    en_base = src.get("content_asr_segments") or []
    if not en_base:
        raise SystemExit("no en content_asr_segments to reuse")
    print(f"reusing en base: {len(en_base)} cues", flush=True)

    # MT method: zh = 1:1 MT(en->zh) + s2hk, NO refine (validated best for English source)
    zh = crosslang_mt.translate_segments(en_base, "en", "zh", _ollama)
    zh = olp.apply_script(zh, "trad")
    print(f"zh MT (書面語, no refine): {len(zh)} cues", flush=True)
    assert len(zh) == len(en_base), "MT broke 1:1"

    newid = uuid.uuid4().hex[:12]
    src_media = src["file_path"]
    new_media = os.path.join(os.path.dirname(src_media), f"{newid}.mp4")
    shutil.copy2(src_media, new_media)

    outs = ["en", "zh"]   # first = English (base), second = 中文書面語
    translations, segments, aligned = [], [], []
    for i, (eb, zb) in enumerate(zip(en_base, zh)):
        st, ed = eb.get("start", 0.0), eb.get("end", 0.0)
        translations.append({"idx": i, "start": st, "end": ed, "status": "pending",
                             "by_lang": {"en": {"text": eb["text"], "status": "pending", "flags": []},
                                         "zh": {"text": zb["text"], "status": "pending", "flags": []}},
                             "en_text": eb["text"], "zh_text": zb["text"]})
        segments.append({"id": i, "start": st, "end": ed, "text": eb["text"], "words": []})
        aligned.append({"start": st, "end": ed, "by_lang": {"en": eb["text"], "zh": zb["text"]}})

    new_entry = {**src, "id": newid, "stored_name": f"{newid}.mp4", "file_path": new_media,
                 "original_name": "The-Winning-Factor（MT書面語對比）.mp4",
                 "source_language": "en", "output_languages": outs, "script": "trad",
                 "status": "done", "translation_status": "done", "translation_kind": "output_lang",
                 "active_kind": "output_lang", "segments": segments, "translations": translations,
                 "aligned_bilingual": aligned, "content_asr_segments": en_base,
                 "text": " ".join(s["text"] for s in segments)}
    for stale in ("_pre_B_translations", "_pre_B_segments"):
        new_entry.pop(stale, None)
    files[newid] = new_entry
    json.dump(data, open(REG, "w"), ensure_ascii=False, indent=1)
    print(f"NEW file {newid}: {len(translations)} cues | en first / zh 書面語 second | MT method, no refine", flush=True)
    print("--- sample (EN base / ZH 書面語 MT) ---", flush=True)
    for i in range(min(4, len(en_base))):
        print(f"  EN: {en_base[i]['text'][:48]}", flush=True)
        print(f"  ZH: {zh[i]['text'][:40]}", flush=True)
    print(f"\nCOMPARE: new={newid} (en+zh書面語, MT) vs existing {SRC_PREFIX} (zh+en)", flush=True)


if __name__ == "__main__":
    main()
