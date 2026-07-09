"""實驗 C：母系/Reset 規則獨立 — 有 vs 冇該規則，量 reset cue 命中 + 抽查唔 regress。"""
import json
import re
import refharness as rh
import mtrun

RUNS = 3


def strip_mare_rule(prompt: str) -> str:
    # 移除【母系規則】起，到該句句號止（含）。
    return re.sub(r"【母系規則】[^。]*。", "", prompt)


def main():
    full = mtrun.read_prompt(mtrun.CANDIDATE_PATH)
    noreset = strip_mare_rule(full)
    assert "母系規則" not in noreset and "母系規則" in full
    cue = rh.find_cue(rh.load_pair("f66d9705f78d")["mot"], "reset mare")
    seg = [{"start": cue["start"], "end": cue["end"], "text": cue["en"]}]
    with_hit = sum(rh.term_accept("reset", mtrun.run_mt(seg, full)[0]) for _ in range(RUNS))
    without_hit = sum(rh.term_accept("reset", mtrun.run_mt(seg, noreset)[0]) for _ in range(RUNS))
    print(f"reset cue: with-rule {with_hit}/{RUNS}  vs  without-rule {without_hit}/{RUNS}", flush=True)
    json.dump({"with": with_hit, "without": without_hit}, open("exp_c_results.json", "w"))
    keep = with_hit >= 2 and with_hit > without_hit
    print("GATE C:", "KEEP 母系規則" if keep else "DROP 母系規則（無明顯增益）", flush=True)


if __name__ == "__main__":
    main()
