"""實驗 D：最終 prompt 全片重跑，對齊專業參考，睇目標術語 ❌→✓ + 打印對照。"""
import json
import sys
import refharness as rh
import mtrun
from exp_c import strip_mare_rule

TARGETS = [
    ("f66d9705f78d", "in his work", "track_work"),
    ("28deab03a71c", "track works", "track_work"),
    ("f66d9705f78d", "back in the field", "closer"),
    ("28deab03a71c", "newcomers", "newcomer"),
    ("f66d9705f78d", "another step", "unit"),
    ("f66d9705f78d", "reset mare", "reset"),
]


def main():
    keep_mare = "--drop-mare" not in sys.argv
    prompt = mtrun.read_prompt(mtrun.CANDIDATE_PATH)
    if not keep_mare:
        prompt = strip_mare_rule(prompt)
    out = {}
    for fid in ["f66d9705f78d", "28deab03a71c"]:
        pair = rh.load_pair(fid)
        cues = [{"start": c["start"], "end": c["end"], "text": c["en"]} for c in pair["mot"]]
        zh = mtrun.run_mt(cues, prompt)
        out[fid] = [{"start": cues[i]["start"], "en": cues[i]["text"], "new_zh": zh[i],
                     "pro": rh.overlap_pro(pair["pro"], cues[i]["start"], cues[i]["end"])}
                    for i in range(len(cues))]
        print(f"{fid}: {len(cues)} cues done", flush=True)
    json.dump(out, open("exp_d_results.json", "w"), ensure_ascii=False, indent=1)
    # 目標術語 ❌→✓
    for fid, sub, term in TARGETS:
        row = next((r for r in out[fid] if sub.lower() in r["en"].lower()), None)
        ok = row and rh.term_accept(term, row["new_zh"])
        print(f"[{term}] {fid}: {'OK' if ok else 'MISS'}  {row['new_zh'][:50] if row else '-'}", flush=True)


if __name__ == "__main__":
    main()
