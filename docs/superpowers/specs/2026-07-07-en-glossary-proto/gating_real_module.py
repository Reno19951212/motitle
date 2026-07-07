#!/usr/bin/env python3
"""實施後 gating：真 module 重跑 dry-run 對照（tracker「實施後 gating」三條件）。
READ-ONLY。用 worktree backend 代碼 + main repo 真數據。"""
import json
import sys
import urllib.request

MAIN = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
WT_BACKEND = (MAIN + "/.claude/worktrees/glossary-en-tag/backend")
sys.path.insert(0, WT_BACKEND)

import en_correction as ec                    # noqa: E402
import output_lang_glossary as olg            # noqa: E402
import translation.crosslang_mt as cmt        # noqa: E402

REG = json.load(open(MAIN + "/backend/data/registry.json"))
GLO = json.load(open(MAIN + "/backend/config/glossaries/db323f9d-8f1e-44da-a20f-64d1ace09b89.json"))
OLD, NEW = "97b66062bfee", "f66d9705f78d"

# V1 實證嘅 10 個機械 FP 位（idx, 詞條）— gating 條件 1：全部唔可以再被 AUTO 改寫
KNOWN_FPS = [(47, "ONE MORE"), (325, "ONE MORE"), (428, "ONE MORE"), (620, "ONE MORE"),
             (825, "ONE MORE"), (314, "ON THE WAY"), (418, "I CAN"),
             (422, "NUMBERS"), (708, "NUMBERS"), (630, "WELL ENOUGH")]


def ollama(sysp, usr, temp=0.3, timeout=420):
    body = json.dumps({"model": "qwen3.5:35b-a3b-mlx-bf16", "stream": False,
                       "options": {"temperature": temp},
                       "messages": [{"role": "system", "content": sysp},
                                    {"role": "user", "content": usr}]}).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


def gate1_auto_zero_fp():
    segs = [{"start": 0, "end": 1, "text": (s.get("text") or "").strip()}
            for s in REG[OLD]["segments"]]
    out, ch = ec.correct_segments_en(segs, glossaries=[GLO], use_llm=False)
    n_rw = sum(len(c) for c in ch)
    fails = []
    for idx, term in KNOWN_FPS:
        if any(c["after"] == term for c in ch[idx]):
            fails.append((idx, term))
    print(f"GATE1 AUTO：{n_rw} rewrites；已知 FP 再現 {len(fails)}/10 → "
          f"{'PASS' if not fails else 'FAIL ' + str(fails)}")
    # 真名保留檢查（降級唔等於全失 — 呢啲必須仍然 AUTO 改寫）
    keep = {153: "SUPREME AGILITY", 2: "SUPERB GUY", 157: "BULL ATTITUDE"}
    misses = [(i, t) for i, t in keep.items() if not any(c["after"] == t for c in ch[i])]
    print(f"GATE1b 真名 AUTO 保留：{'PASS' if not misses else 'FAIL ' + str(misses)}")
    return out


def gate3_brackets():
    g_on = {**GLO, "name_brackets": "zh"}
    rows = REG[NEW]["translations"]
    segs_src = [(r.get("en_text") or "") for r in rows]
    zh = [{"start": 0, "end": 1, "text": ((r.get("by_lang") or {}).get("zh") or {}).get("text")
           or r.get("zh_text") or ""} for r in rows]
    out = olg.glossary_stage(zh, [g_on], "zh", "en", "mt",
                             llm_call=lambda s, u: "", use_llm=False, src_texts=segs_src)
    wrapped = [(i, o["text"]) for i, o in enumerate(out) if o["text"] != zh[i]["text"]]
    two_char_ok = any(("「祝願」" in t) or ("「球星」" in t) or ("「玩笑」" in t)
                      for _, t in wrapped)
    for i, t in wrapped:
        print(f"   wrap #{i}: {t[:70]}")
    # 舊片巧合位：idx627 關鍵所在（該段無命中）必須唔括
    rows_o = REG[OLD]["translations"]
    z627 = ((rows_o[627].get("by_lang") or {}).get("zh") or {}).get("text") or rows_o[627].get("zh_text") or ""
    e627 = (REG[OLD]["segments"][627].get("text") or "")
    o627 = olg.glossary_stage([{"start": 0, "end": 1, "text": z627}], [g_on], "zh", "en", "mt",
                              llm_call=lambda s, u: "", use_llm=False, src_texts=[e627])
    no_coincidence = "「關鍵所在」" not in o627[0]["text"]
    print(f"GATE3 括號：新片 wrap 段數={len(wrapped)}；2字名命中={'PASS' if two_char_ok else 'FAIL'}；"
          f"巧合唔括={'PASS' if no_coincidence else 'FAIL'}")


def gate4_generic_no_glossary():
    segs = [{"start": 0, "end": 1, "text": (s.get("text") or "").strip()}
            for s in REG[NEW]["segments"]]
    out, ch = ec.correct_segments_en(segs, glossaries=None)
    same = all(o["text"] == s["text"] for o, s in zip(out, segs))
    empty = all(not c for c in ch)
    print(f"GATE4 無詞彙表零改動：texts identical={'PASS' if same else 'FAIL'}；"
          f"changes 全空={'PASS' if empty else 'FAIL'}")


def gate2_rederive(out_segs):
    for idx, want in [(221, "奮鬥心"), (552, "疾風財子")]:
        src = out_segs[idx]["text"]
        for run in (1, 2):
            mt = cmt.translate_segments([{"start": 0, "end": 1, "text": src}],
                                        "en", "zh", ollama, style="racing")
            fin = olg.glossary_stage(mt, [GLO], "zh", "en", "mt", ollama,
                                     use_llm=True, src_texts=[src])
            ok = want in fin[0]["text"]
            print(f"GATE2 #{idx} run{run}: {'PASS' if ok else 'FAIL'} — {fin[0]['text'][:60]}")


if __name__ == "__main__":
    corrected = gate1_auto_zero_fp()
    gate3_brackets()
    gate4_generic_no_glossary()
    if "--llm" in sys.argv:
        gate2_rederive(corrected)
