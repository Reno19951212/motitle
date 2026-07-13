# 確定性後處理正規化層 驗證 tracker（GATING）

日期：2026-07-13 ｜ 實施：`backend/output_lang_normalize.py`（Task 1-5，commit `517d9550`→`f6d106be`）
設計：[2026-07-09-deterministic-mt-normalize-design.md](2026-07-09-deterministic-mt-normalize-design.md)
計劃：[../plans/2026-07-09-deterministic-mt-normalize-plan.md](../plans/2026-07-09-deterministic-mt-normalize-plan.md)

**理念**：確定映射（公尺→米、騎師英文/音譯錯→HKJC 正名）移出概率 MT prompt，落零 LLM 確定層 → 100% 一致，唔再靠 model 記性。

## A. Unit test gate（主 gate，Task 1-4/5 覆蓋）

單獨跑（避 order 污染，見 memory test-suite-isolation-baseline）：

```
pytest tests/test_output_lang_normalize.py -q   → 19 passed
```

覆蓋：
- **單位 pass**（Task 1）：公尺→米、1600公尺→1600米、公裏→公里 異體、已正確公里 no-op、無單位 no-op、多段、immutable。
- **roster / load_jockeys**（Task 2）：Luke 變體齊、缺檔 fail-open `[]`。
- **騎師 pass**（Task 3）：英文變體替換、音譯錯（盧克）替換、longest-first（Luke Ferraris 整體）、word-boundary 防 `lukewarm` 誤中、already-正名 no-op、immutable、空 roster no-op。
- **orchestrator**（Task 4）：zh+racing 單位+騎師都做、zh+generic 只做單位（騎師唔郁）、en+racing no-op、唔加 lang（由 caller 蓋）。

hook merge（Task 5）：`test_normalize_hook.py` 驗 `derive_aligned_output` 掛 normalize_stage 後，`glossary_changes` 保留單位/騎師記錄 + caller 蓋 `lang`（fast path / glossary path 都 merge，同 phonetic `_pc2` pattern，冇被 glossary_stage 冲走）。

## B. 真檔 dry-run（B — 生產 registry READ-ONLY）

Script：[2026-07-09-normalize-validation.py](2026-07-09-normalize-validation.py)
資料：`$MAIN/backend/data/registry.json`（只讀，冇寫回）｜模組：worktree `output_lang_normalize.py`（Task 1-5，未 merge 入 main）

跑：`python3 2026-07-09-normalize-validation.py` → `2 cues normalized.`

| 檔 | 掃描 cues | 修正 | before → after | 記錄 |
|---|---|---|---|---|
| `f66d9705f78d` | 29 | 2 | `他衝上領放，Luke 已策騎他` → `…霍宏聲 已策騎他` | 騎師正名 `Luke→霍宏聲` |
| | | | `二千公尺又是另一程。` → `二千米又是另一程。` | 單位正規化 `公尺→米` |
| `28deab03a71c` | 21 | 0 | （無 Luke / 無公尺）零改動 | — |

**觀察**：
- 預期修正兩樣都出現：`公尺→米`（單位）+ `Luke→霍宏聲`（騎師英文名保留 → 正名）。
- 50 cues 掃描只動 2 cue，其餘 48 cue 零改動 → **零誤傷**（word-boundary + ≥2 字 substring + longest-first 生效，冇撞普通句/普通英文）。
- 檔2 完全 no-op → 確定映射只喺真命中時觸發，安全對照。

## Gate 結論

**PASS** — unit test 19/19（單位/騎師/orchestrator/hook merge 全覆蓋）；真檔 dry-run 兩檔 50 cue 命中 2、零誤傷；確定映射一致、fail-open 到位（缺 jockeys.json → `[]`，唔炒 job）。

E2E（Task 7 Step 4，用戶自行）：重啟後端 + 重新處理真賽馬片，校對頁應見「二千米」「霍宏聲」+ 詞彙對照記錄（tag 單位正規化 / 騎師正名）。

## 已知限制（落 production 接受）

- roster 策展（寧缺莫濫）：只收診斷確認 + racing.txt G 段已驗證名單 + 常見音譯；未收名字 → 唔郁（保留 MT 原輸出，唔會誤改）。
- 中文音譯變體用 ≥2 字 substring：極短同名碰撞理論存在，故 roster 只收辨識度高變體（2 字名如「潘頓」為 canonical，變體側重英文名/3+ 字音譯）。
- 單位只做距離（公尺/公裏 → 米/公里）；其他單位（如速度）未納入，按需擴 `_UNIT_RULES`。
