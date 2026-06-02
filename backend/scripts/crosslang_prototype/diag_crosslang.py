"""Validation-First — cross-language routing: Whisper-direct vs ASR+MT (2026-06-02).

For one CONTENT language (zh/en/ja audio), runs every CROSS output language two ways
on the SAME clip slice, and emits quantified quality metrics + an LLM-judge verdict:

  Method A (Whisper-direct):  output==en -> Whisper `translate` (→EN);
                              else        -> Whisper force `language=<output>` (transcribe).
  Method B (ASR+MT):          Whisper transcribe in the CONTENT language (the source),
                              then per-segment 1:1 MT to the output language
                              (Ollama qwen3.5:35b — production MT; 1:1 = lower bound,
                               production ProFlow uses sentence-pipeline so ≥ this).

Same-family outputs (e.g. zh-content→yue/zh) are run Whisper-direct as a quality ceiling.

Production stack: ASR = mlx-whisper large-v3; MT = Ollama qwen3.5:35b-a3b-mlx-bf16.
Run:  cd backend && PYTHONPATH=. python scripts/crosslang_prototype/diag_crosslang.py <zh|en|ja>
Writes /tmp/crosslang_<content>.json + prints a readable summary.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

import mlx_whisper

try:
    from opencc import OpenCC
    _CC = OpenCC("s2hk")
    def s2hk(t):
        return _CC.convert(t or "")
except Exception:
    def s2hk(t):
        return t or ""

REPO = "mlx-community/whisper-large-v3-mlx"
OLLAMA = "http://localhost:11434"
MT_MODEL = "qwen3.5:35b-a3b-mlx-bf16"
FOLDER = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音"
CLIP_SEC = int(os.environ.get("CLIP_SEC", "80"))

LANG = {
    "yue": {"wl": "yue", "s2hk": True,  "label": "口語廣東話", "cjk": True,
            "name": "香港口語廣東話（用口語字眼如 嘅/係/喺/咗/唔/睇，繁體字）"},
    "zh":  {"wl": "zh",  "s2hk": True,  "label": "中文書面語", "cjk": True,
            "name": "現代正式繁體中文書面語（阿拉伯數字，禁文言/公文腔）"},
    "en":  {"wl": "en",  "s2hk": False, "label": "英文",       "cjk": False, "name": "English"},
    "ja":  {"wl": "ja",  "s2hk": False, "label": "日文",       "cjk": True,
            "name": "自然書面日本語（日文）"},
}

CONTENT = {
    "zh": {"clip": "香港警察結業會操（中文語音）.mp4", "asr_wl": "yue", "s2hk": True,
           "name": "粵語/中文", "same": ["yue", "zh"], "cross": ["en", "ja"]},
    "en": {"clip": "Harry-Kane-Post-Match-Interview-Bayern（英文語音）.mp4", "asr_wl": "en", "s2hk": False,
           "name": "English", "same": ["en"], "cross": ["zh", "yue", "ja"]},
    "ja": {"clip": "日本語音訪問片段馬會(日文語音）.mp4", "asr_wl": "ja", "s2hk": False,
           "name": "日本語", "same": ["ja"], "cross": ["zh", "yue", "en"]},
}


def clip_wav(src, out):
    subprocess.run(["ffmpeg", "-y", "-i", src, "-t", str(CLIP_SEC),
                    "-ar", "16000", "-ac", "1", out], capture_output=True)


def whisper_pass(wav, language, task, do_s2hk):
    """Return (segments[{start,end,text}], wall_seconds). cond_prev=False (anti-loop)."""
    t0 = time.time()
    kwargs = {"path_or_hf_repo": REPO, "task": task,
              "condition_on_previous_text": False}
    if language is not None:
        kwargs["language"] = language
    r = mlx_whisper.transcribe(wav, **kwargs)
    segs = []
    for s in r.get("segments", []):
        txt = (s.get("text", "") or "").strip()
        if do_s2hk:
            txt = s2hk(txt)
        segs.append({"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": txt})
    return segs, round(time.time() - t0, 1)


def _ollama(system, user, temperature=0.3):
    body = {"model": MT_MODEL, "stream": False, "think": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "options": {"temperature": temperature}}
    req = urllib.request.Request(f"{OLLAMA}/api/chat",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out = data.get("message", {}).get("content", "") or ""
    # strip any stray <think> blocks + label prefixes
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()
    out = re.sub(r"^(譯文|翻譯|Translation|出力)[:：]\s*", "", out).strip()
    return out.splitlines()[0].strip() if out else ""


_MT_SYS = ("你係專業廣播字幕翻譯員。將用戶提供嘅單句{src}字幕，翻譯成{tgt}。"
           "規則：貼近廣播口播、自然流暢；唔好加原文冇嘅資訊；保留專有名詞；"
           "輸出一行、只輸出譯文本身，唔好任何解釋或標籤。")


def asr_mt(asr_segs, src_name, tgt_code):
    """Per-segment 1:1 MT of the content-language ASR segments → tgt language."""
    tgt = LANG[tgt_code]
    sysp = _MT_SYS.format(src=src_name, tgt=tgt["name"])
    out = []
    t0 = time.time()
    for s in asr_segs:
        src_txt = s["text"]
        tr = _ollama(sysp, src_txt) if src_txt.strip() else ""
        if tgt["s2hk"]:
            tr = s2hk(tr)
        out.append({"start": s["start"], "end": s["end"], "text": tr})
    return out, round(time.time() - t0, 1)


def metrics(segs, cjk):
    txts = [s["text"] for s in segs]
    lens = [len(t) for t in txts]
    n = len(segs)
    cap = 18 if cjk else 45
    nonempty = [l for l in lens if l > 0]
    med = sorted(nonempty)[len(nonempty)//2] if nonempty else 0
    over = sum(1 for l in lens if l > cap)
    short = sum(1 for l in lens if 0 < l <= (2 if cjk else 4))
    empty = sum(1 for l in lens if l == 0)
    # adjacent duplicate (near-identical neighbour) — a hallucination/loop tell
    dup = sum(1 for i in range(1, n) if txts[i] and txts[i] == txts[i-1])
    # repeated 4-gram ratio across the whole text (loop detector)
    joined = "".join(txts) if cjk else " ".join(txts)
    grams = [joined[i:i+8] for i in range(0, max(0, len(joined)-8), 4)] if cjk else \
            [" ".join(joined.split()[i:i+4]) for i in range(0, max(0, len(joined.split())-4))]
    rep = round(1 - len(set(grams))/len(grams), 3) if grams else 0.0
    return {"n_seg": n, "median_chars": med, "max_chars": max(lens) if lens else 0,
            "over_cap": over, "over_cap_pct": round(100*over/n, 1) if n else 0,
            "short_frag": short, "empty": empty, "adj_dup": dup, "rep4gram": rep,
            "total_chars": sum(lens)}


_JUDGE_SYS = ("你係雙語字幕質檢專家。畀你 SOURCE（原文逐句）同 CANDIDATE（某語言字幕輸出），"
              "評估 CANDIDATE 作為 SOURCE 嘅{tgt}字幕質量。"
              "只輸出 JSON：{{\"adequacy\":1-5,\"fluency\":1-5,\"segmentation\":1-5,\"note\":\"≤30字\"}}。"
              "adequacy=有冇忠實傳達原意（5=完全準確,1=亂噏/幻覺）；fluency=讀落自然程度；"
              "segmentation=分句是否自然合理。")


def judge(src_segs, cand_segs, tgt_code):
    tgt = LANG[tgt_code]
    src_join = "\n".join(s["text"] for s in src_segs[:40])
    cand_join = "\n".join(s["text"] for s in cand_segs[:40])
    user = f"SOURCE:\n{src_join}\n\nCANDIDATE（{tgt['label']}）:\n{cand_join}"
    raw = _ollama(_JUDGE_SYS.format(tgt=tgt["label"]), user, temperature=0.0)
    try:
        m = re.search(r"\{.*\}", raw, flags=re.S)
        return json.loads(m.group(0)) if m else {"raw": raw[:120]}
    except Exception:
        return {"raw": raw[:120]}


def main():
    content = sys.argv[1] if len(sys.argv) > 1 else "zh"
    cfg = CONTENT[content]
    wav = f"/tmp/clx_{content}.wav"
    clip_wav(f"{FOLDER}/{cfg['clip']}", wav)
    print(f"\n{'='*72}\n## CONTENT={content} ({cfg['name']})  clip={cfg['clip'][:30]} {CLIP_SEC}s\n{'='*72}", flush=True)

    # Shared content-language ASR (the MT source + the judge reference)
    asr_segs, asr_t = whisper_pass(wav, cfg["asr_wl"], "transcribe", cfg["s2hk"])
    print(f"[ASR {cfg['asr_wl']}] {len(asr_segs)} segs, {asr_t}s — source for ASR+MT + judge ref", flush=True)
    print(f"   e.g. {asr_segs[0]['text'][:60] if asr_segs else '(empty)'}", flush=True)

    result = {"content": content, "clip": cfg["clip"], "clip_sec": CLIP_SEC,
              "asr_seconds": asr_t, "asr_n": len(asr_segs), "cells": {}}

    # Same-family baselines (Whisper-direct quality ceiling)
    for out_code in cfg["same"]:
        L = LANG[out_code]
        segs, t = whisper_pass(wav, L["wl"], "transcribe", L["s2hk"])
        m = metrics(segs, L["cjk"])
        j = judge(asr_segs, segs, out_code)
        result["cells"][f"{out_code}__baseline"] = {"method": "whisper-direct(same)",
                                                     "secs": t, "metrics": m, "judge": j,
                                                     "sample": [s["text"] for s in segs[:3]]}
        print(f"\n-- {out_code} (same-family baseline, whisper-direct) {t}s --\n   {m}\n   judge={j}", flush=True)

    # Cross cells: Method A (whisper-direct) vs Method B (ASR+MT)
    for out_code in cfg["cross"]:
        L = LANG[out_code]
        # A: whisper-direct
        if out_code == "en":
            a_segs, a_t = whisper_pass(wav, None, "translate", False)
        else:
            a_segs, a_t = whisper_pass(wav, L["wl"], "transcribe", L["s2hk"])
        a_m = metrics(a_segs, L["cjk"]); a_j = judge(asr_segs, a_segs, out_code)
        # B: ASR + MT
        b_segs, b_t = asr_mt(asr_segs, cfg["name"], out_code)
        b_m = metrics(b_segs, L["cjk"]); b_j = judge(asr_segs, b_segs, out_code)
        result["cells"][f"{out_code}__cross"] = {
            "A_whisper_direct": {"secs": a_t, "metrics": a_m, "judge": a_j,
                                 "sample": [s["text"] for s in a_segs[:3]]},
            "B_asr_mt":         {"secs": b_t, "metrics": b_m, "judge": b_j,
                                 "sample": [s["text"] for s in b_segs[:3]]},
        }
        print(f"\n== CROSS {content}→{out_code} ({L['label']}) ==", flush=True)
        print(f"  A whisper-direct {a_t}s: {a_m}\n     judge={a_j}\n     e.g. {a_segs[0]['text'][:60] if a_segs else ''}", flush=True)
        print(f"  B ASR+MT        {b_t}s: {b_m}\n     judge={b_j}\n     e.g. {b_segs[0]['text'][:60] if b_segs else ''}", flush=True)

    path = f"/tmp/crosslang_{content}.json"
    json.dump(result, open(path, "w"), ensure_ascii=False, indent=2)
    print(f"\n# wrote {path}", flush=True)


if __name__ == "__main__":
    main()
