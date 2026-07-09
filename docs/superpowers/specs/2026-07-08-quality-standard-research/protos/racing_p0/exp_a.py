"""實驗 A：目標術語命中率（舊 racing.txt vs 候選，各 cue 重跑 3 次）。"""
import json
import refharness as rh
import mtrun

RUNS = 3
# (fid, en 子串定位 cue, term 名)
TARGETS = [
    ("f66d9705f78d", "in his work", "track_work"),
    ("28deab03a71c", "track works", "track_work"),
    ("f66d9705f78d", "back in the field", "closer"),
    ("28deab03a71c", "newcomers", "newcomer"),
    ("f66d9705f78d", "another step", "unit"),
    ("f66d9705f78d", "reset mare", "reset"),
]


def main():
    old = mtrun.read_prompt(mtrun.BASELINE_PATH)
    new = mtrun.read_prompt(mtrun.CANDIDATE_PATH)
    pairs = {fid: rh.load_pair(fid) for fid in {t[0] for t in TARGETS}}
    rows = []
    for fid, sub, term in TARGETS:
        cue = rh.find_cue(pairs[fid]["mot"], sub)
        assert cue, f"cue not found: {fid} / {sub}"
        seg = [{"start": cue["start"], "end": cue["end"], "text": cue["en"]}]
        rec = {"fid": fid, "term": term, "en": cue["en"], "old": [], "new": []}
        for _ in range(RUNS):
            rec["old"].append(mtrun.run_mt(seg, old)[0])
            rec["new"].append(mtrun.run_mt(seg, new)[0])
        rec["old_hit"] = sum(rh.term_accept(term, z) for z in rec["old"])
        rec["new_hit"] = sum(rh.term_accept(term, z) for z in rec["new"])
        rows.append(rec)
        print(f"[{term}] {fid} old {rec['old_hit']}/{RUNS} -> new {rec['new_hit']}/{RUNS}", flush=True)
        for z in rec["new"]:
            print("    new:", z[:60], flush=True)
    json.dump(rows, open("exp_a_results.json", "w"), ensure_ascii=False, indent=1)
    passed = all(r["new_hit"] >= 2 for r in rows)
    print("\nGATE A:", "PASS" if passed else "FAIL", "(每 term new_hit >= 2/3)", flush=True)


if __name__ == "__main__":
    main()
