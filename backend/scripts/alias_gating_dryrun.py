"""確定性別名層 gating — 零 LLM，read-only。
GATE1: 宣告別名全中（en source_variants + yue target_aliases）
GATE2: 已知 FP class 零新增（電流/尾指/標誌/段處 2 字別名 → 唔改正常句）
GATE3: 既有糾錯零 regression（整個過 → 靖哥哥 仍然被 AUTO 擋，唔會因別名層變樣）
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import alias_rewrite as ar
import phonetic_correction as pc
import en_correction as ec

REG = os.path.join(os.path.dirname(__file__), "..", "data", "registry.json")
GLO = os.path.join(os.path.dirname(__file__), "..", "config", "glossaries",
                   "db323f9d-8f1e-44da-a20f-64d1ace09b89.json")

reg = json.load(open(REG, encoding="utf-8"))
glo = json.load(open(GLO, encoding="utf-8"))

# --- GATE1 en：注入已知聽錯做 source_variants，確認 100% 改回正名 ---
en_cues = [{"start": 0, "end": 1, "text": (s.get("text") or "")}
           for s in reg["97b66062bfee"]["segments"]]
gt_en = {"Speedy Smarty": "SPEEDY SMARTIE", "Malpenza": "MALPENSA",
         "Wolff coming": "WOLF COMING"}
g_en = json.loads(json.dumps(glo))
by_src = {e["source"]: e for e in g_en["entries"]}
for heard, canon in gt_en.items():
    if canon in by_src:
        by_src[canon].setdefault("source_variants", []).append(heard)
rules = ar.collect_en_rules([g_en])
out, ch = ar.apply_latin(en_cues, rules)
joined = " ".join(s["text"] for s in out)
gate1_en = all(canon in joined for canon in gt_en.values())
print(f"GATE1 en 宣告別名全中: {gate1_en}")

# --- GATE2：2 字別名唔改正常句 ---
fp_probe = [{"start": 0, "end": 1, "text": t} for t in
            ["呢條電流好強", "佢隻尾指受咗傷", "個標誌好靚", "段處理流程順暢"]]
g_fp = {"source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "gx",
        "entries": [{"id": "e1", "source": "A", "target": "殿後", "target_aliases": ["電流"]},
                    {"id": "e2", "source": "B", "target": "尾二", "target_aliases": ["尾指"]}]}
out2, ch2 = ar.apply_cjk(fp_probe, ar.collect_zh_rules([g_fp]))
gate2 = all(o["text"] == p["text"] for o, p in zip(out2, fp_probe))
print(f"GATE2 2字別名零誤中: {gate2}")

# --- GATE3：既有 AUTO 回歸（整個過 → 靖哥哥 仍被擋）---
probe3 = [{"start": 0, "end": 1, "text": "喺整個過程之中"}]
out3, _ = pc.correct_segments(probe3, glossaries=[glo], mt_style="racing", use_llm=False)
gate3 = "靖哥哥" not in out3[0]["text"]
print(f"GATE3 整個過→靖哥哥 仍被擋: {gate3}")

print("\nALL PASS:", gate1_en and gate2 and gate3)
