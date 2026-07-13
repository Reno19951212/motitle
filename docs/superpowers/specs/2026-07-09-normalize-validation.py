#!/usr/bin/env python3
"""真檔 dry-run：兩馬會檔 registry 譯文 → apply normalize_stage → print before/after。READ-ONLY。"""
import json
import os
import sys
MAIN = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
# 模組取自 worktree（Task 1-5 未 merge 入 main），registry 讀 $MAIN 生產資料（READ-ONLY）。
_WT_BACKEND = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "..", "..", "..", "backend"))
sys.path.insert(0, _WT_BACKEND)   # worktree module（正在驗證嘅版本）優先
import output_lang_normalize as oln  # noqa: E402

reg = json.load(open(MAIN + "/backend/data/registry.json"))
changed = 0
for fid in ["f66d9705f78d", "28deab03a71c"]:
    rows = reg[fid]["translations"]
    segs = [{"start": r.get("start"), "end": r.get("end"),
             "text": ((r.get("by_lang") or {}).get("zh") or {}).get("text")
                      or r.get("zh_text") or ""} for r in rows]
    out, ch = oln.normalize_stage(segs, "zh", "racing")
    for i, c in enumerate(ch):
        if c:
            changed += 1
            print(f"{fid} #{i}: {segs[i]['text'][:45]}")
            print(f"        → {out[i]['text'][:45]}  {[x['before']+'→'+x['after'] for x in c]}")
print(f"\n{changed} cues normalized. 檢查：公尺→米、Luke→霍宏聲 應出現；其他句零改動。")
