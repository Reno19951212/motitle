"""實驗 B（精簡）：舊 vs 新 prompt 產出 side-by-side，供人手（Opus）判 regression。

唔用本地 judge（退化不可靠）；只攞譯文對照，由 reviewer 直接判。
選 cue：中性（無觸發詞）+ 含觸發詞（work/metres/back/mare）於不同語境，
偵測 append 術語有冇 mis-fire 到無關句。
"""
import json
import mtrun

# 揀自兩片：代表性 cue（單句／短，避 run-on 退化）
CUES = [
    "Brave. He's very brave.",                                  # 中性
    "So that would be the best description of him.",            # 中性
    "I wouldn't swap him for any other horse.",                 # 中性（him/swap）
    "he's probably ideal at 1,600.",                            # 距離單位
    "2,000's another step again.",                              # 距離單位（曾 baseline 出「公尺」）
    "he'll give himself every chance.",                         # 中性片段
    "That may be a benefit to newcomers.",                      # newcomer 觸發
    "He will race along the rail.",                             # rail（內欄）
]


def main():
    old = mtrun.read_prompt(mtrun.BASELINE_PATH)
    new = mtrun.read_prompt(mtrun.CANDIDATE_PATH)
    rows = []
    for en in CUES:
        seg = [{"start": 0, "end": 1, "text": en}]
        o = mtrun.run_mt(seg, old)[0]
        n = mtrun.run_mt(seg, new)[0]
        rows.append({"en": en, "old": o, "new": n})
        print(f"EN : {en}", flush=True)
        print(f"OLD: {o}", flush=True)
        print(f"NEW: {n}", flush=True)
        print("", flush=True)
    json.dump(rows, open("exp_b_lean_results.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
