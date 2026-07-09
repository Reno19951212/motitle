"""實驗 B：regression — 兩片全 cue 用新 prompt，逐 cue judge「新 vs 舊」有冇引入新錯。"""
import json
import re
import refharness as rh
import mtrun

FIDS = ["f66d9705f78d", "28deab03a71c"]
JUDGE_SYS = (
    "你係英譯中字幕質量審核員。俾你一句英文原文、譯法A、譯法B。"
    "判斷 B 相對 A 有冇引入「A 冇而 B 有」的意思錯誤／漏譯／幻覺／語體漂移（粵語口語或公文腔）。"
    "淨係睇 B 有冇變差，唔使理風格長短差異。只回 JSON：{\"regression\": true/false, \"why\": \"…\"}")
_J = re.compile(r'"regression"\s*:\s*(true|false)')


def judge(en, a, b):
    u = f"英文：{en}\n譯法A（舊）：{a}\n譯法B（新）：{b}\nB 相對 A 有冇引入新錯誤？"
    raw = mtrun.ollama(JUDGE_SYS, u, temperature=0.2)
    m = _J.search(raw or "")
    return (m and m.group(1) == "true"), raw


def main():
    old_p = mtrun.read_prompt(mtrun.BASELINE_PATH)
    new_p = mtrun.read_prompt(mtrun.CANDIDATE_PATH)
    regressions = []
    total = 0
    for fid in FIDS:
        mot = rh.load_pair(fid)["mot"]
        cues = [{"start": c["start"], "end": c["end"], "text": c["en"]} for c in mot if c["en"].strip()]
        old_zh = mtrun.run_mt(cues, old_p)
        new_zh = mtrun.run_mt(cues, new_p)
        for i, c in enumerate(cues):
            total += 1
            reg, raw = judge(c["text"], old_zh[i], new_zh[i])
            print(f"  {fid} #{i} reg={reg}", flush=True)
            if reg:
                regressions.append({"fid": fid, "en": c["text"],
                                    "old": old_zh[i], "new": new_zh[i], "why": raw[:200]})
    json.dump(regressions, open("exp_b_results.json", "w"), ensure_ascii=False, indent=1)
    print(f"\nGATE B: {'PASS' if not regressions else 'FAIL'} — {len(regressions)}/{total} regressions", flush=True)
    for r in regressions:
        print(f"  {r['fid']}: {r['en'][:40]}\n    舊:{r['old'][:40]}\n    新:{r['new'][:40]}", flush=True)


if __name__ == "__main__":
    main()
