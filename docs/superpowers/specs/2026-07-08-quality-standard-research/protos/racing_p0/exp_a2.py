"""實驗 A2：術語規則乾淨隔離測試（單句 probe，避開多句 run-on 觸發嘅 model 退化）。

用乾淨單句直接測「術語規則有冇效」，而唔係「model 處唔處理到 run-on 真 cue」（後者
無論新舊 prompt 都會退化，唔係公平 test bed）。舊 vs 新 racing.txt 各 3 次。
"""
import json
import refharness as rh
import mtrun

RUNS = 3
# (乾淨單句 probe, term 名, 硬/軟)
PROBES = [
    ("His track work has been excellent this week.", "track_work", "HARD"),
    ("He is a very talented sprinter.", "sprinter", "HARD"),
    ("He steps up to 2000 metres today.", "unit", "HARD"),
    ("He is out of a Reset mare.", "reset", "HARD"),
    ("He settled at the back of the field early.", "closer", "SOFT"),
    ("He is a newcomer this season.", "newcomer", "SOFT"),
]


def term_ok(name, zh):
    if name == "sprinter":
        return "短途" in (zh or "")
    return rh.term_accept(name, zh)


def main():
    old = mtrun.read_prompt(mtrun.BASELINE_PATH)
    new = mtrun.read_prompt(mtrun.CANDIDATE_PATH)
    rows = []
    for en, term, tier in PROBES:
        seg = [{"start": 0, "end": 1, "text": en}]
        rec = {"term": term, "tier": tier, "en": en, "old": [], "new": []}
        for _ in range(RUNS):
            rec["old"].append(mtrun.run_mt(seg, old)[0])
            rec["new"].append(mtrun.run_mt(seg, new)[0])
        rec["old_hit"] = sum(term_ok(term, z) for z in rec["old"])
        rec["new_hit"] = sum(term_ok(term, z) for z in rec["new"])
        rows.append(rec)
        print(f"[{tier} {term}] old {rec['old_hit']}/{RUNS} -> new {rec['new_hit']}/{RUNS}", flush=True)
        for z in rec["new"]:
            print("    new:", z[:60], flush=True)
    json.dump(rows, open("exp_a2_results.json", "w"), ensure_ascii=False, indent=1)
    hard = [r for r in rows if r["tier"] == "HARD"]
    hard_pass = all(r["new_hit"] >= 2 for r in hard)
    print("\nGATE A (HARD ≥2/3):", "PASS" if hard_pass else "FAIL", flush=True)
    for r in rows:
        print(f"  {r['tier']} {r['term']}: {r['old_hit']}→{r['new_hit']}", flush=True)


if __name__ == "__main__":
    main()
