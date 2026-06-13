# 書面語 Refiner 質量提升（P0+P1）— Design

日期：2026-06-13 ｜ 狀態：✅ 用戶已批准方向（P0+P1+多 clip gating）｜ Branch: `worktree-lang-quality`
研究基礎：[2026-06-13-written-quality-research/](2026-06-13-written-quality-research/)（7-agent 實驗；W6 組合 理想達成 68.8%→91.7-93.8%、位置術語 0→100%、名詞 87.5→100%、意思忠實 0/9→6/9）

## 目標

提升 yue→zh **書面語** refine 質量。現狀 `formal_refine` **逐段獨立、零上下文** → 兩大系統性錯：①位置術語「尾二/尾三/尾四」（＝倒數第N匹）100% 解錯（0/5）②馬名被當普通詞改走（好友心得→獲好評、幸運有您→拆散）。研究實證最佳組合（W6）對住 W1 catalog 達成上述數字，1 call/段、warm 0.39s/段、production 可行。

## 架構（W6 贏家組合，全部 byte-identical port 自驗證 proto）

`formal_refine` 由「逐段裸文字」改成「**逐段 + 鐵則 prompt + 逐句正名注入 + ±2 上下文窗口 + 名詞遺失 flag**」：

```
for 每段 base：
  ① system prompt = 鐵則 prompt（名詞保護/位置術語/反幻覺前置）
       + 本句命中嘅 glossary 馬名逐字注入（SYSTEM，唔係 USER — gotcha 見下）
       + 本句出現嘅位置術語 gloss（racing 先有）
  ② user turn = 【前文 ±2】【本句】【後文 ±2】（前後文只讀唔輸出，語義錨點）
  ③ LLM → parse keep JSON
  ④ name-set diff：注入咗嘅名喺輸出消失 → 記 flag（唔自動還原 — flag only）
```

**致命 gotcha（W2 實證）**：roster 注入**必須喺 SYSTEM prompt**。放 USER turn → 48/48 段將提示 echo 入字幕、JSON contract 爆。

**明確 REJECT**（研究實證）：C2 全文一次過（register 崩 54%、8 段照抄口語）；phonetic 後處理還原馬名（recall 0.40、auto-restore 吞句誤傷）。

## Prompt（racing 換新、generic 保守）

- **racing** `config/prompt_templates_v5/refiner/zh_written_register_v6.json` 嘅 `system_prompt` → 換成 **W5 V2 鐵則前置 prompt + EMBED_GLOSS（埋邊/放頭/透出/做P 術語）**（= research `protos/W5-final-prompt.txt` + W6 `EMBED_GLOSS`，已驗證）
- **generic** `zh_written_register_generic.json` → **prompt 唔改**（研究只驗證 racing；generic prompt 重寫未驗證，風險）。只套用**域中性機制**（roster 注入 + 上下文窗口 + name-diff flag）
- **GARBLED_GUARD + WIN_INSTR**（亂碼保護 + 窗口格式說明）由 code 加（域中性，所有 style；WIN_INSTR 只喺 `context_window>0` 時加）— 拼接順序 = file 內容 → GARBLED_GUARD → WIN_INSTR，令 racing 嘅最終 prompt byte-identical 對齊 W6_BASE_SYSP

## 後端

**`backend/output_lang_postprocess.py` `formal_refine` 改簽名 + 邏輯**：

```python
def formal_refine(segments, llm_call, style="generic", glossaries=None,
                  context_window=2, cancel_check=None) -> List[dict]:
```
- 新 helper（同檔，port 自 W6 proto）：`_refine_window_user(texts, i, ctx)`、`_inject_roster(base_sysp, names, pos_terms)`、`_glossary_name_set(glossaries)`（lazy `import phonetic_correction; build_index([...],[])` 攞 glossary 正名集，**ImportError fail-open → 空 set**）
- 逐段：抽本句命中嘅 glossary 名（`name in txt`）+ 位置術語（racing 先計 `尾二/尾三/尾四`）→ 注入 system → 窗口 user → call → parse → name-diff flag（`seg["refine_name_dropped"]=[…]`，純記錄）
- `cancel_check` 行為不變（每段前 call）
- **`context_window=0` → 退回逐段無窗口**（測試/將來 generic toggle 用）；`glossaries=None` → 無 roster 注入（行為接近舊版但 prompt 已換）

**`backend/output_lang_aligned.py` `derive_aligned_output`**：refine 分支 `olp.formal_refine(base, llm_call, style=style, cancel_check=cancel_check)` → 加 `glossaries=glossaries`

**`backend/app.py`**：
- `_produce_output_lang` 嘅 `output_lang == "zh"` refine call → 加 `style=mt_style, glossaries=glossaries`
- bound_base 路徑經 `derive_aligned_output` 已 thread glossaries，無需另改

## 名詞遺失 flag（P2 輕量版，純記錄）

`seg["refine_name_dropped"]` 只係 deterministic 記錄（base 有名→refine 丟咗），**唔自動還原、唔郁文字**。今次 scope 唔接 proofread UI（P2 follow-up）— 只確保資料存在 + log，將來可 surface。

## P1.5 多 clip gating（GATING — ship 前必過）

離線跑 baseline（舊 refine）vs 新 refine，≥3 領域：
- **racing 回歸**：研究 clip（48c1657e7ec1/09e0e3679f35）— 對 W1 catalog 重現 ~44/48 理想達成、位置術語 5/5、名詞 40/40，**唔可以低過研究數字**
- **racing #2**：de5bd2b803bf（袁幸堯）— 確認泛化
- **generic 回歸**：≥1 條 generic yue clip（570fde92b502 / 798853512b6d）— **確認 generic prompt 不變 + 加機制後冇 regression**（名詞保留升或平、register 唔崩、格式 48 進 48 出）
- 結果寫 `docs/superpowers/specs/2026-06-13-written-refine-validation-tracker.md`（✅/⚠️/❌ + 數字）。**generic 出現 register 崩或名詞 regression → 該 clip 嘅機制收窄再驗**

## 唔做（P2 follow-ups）

generic prompt 重寫（未驗證）、name-diff flag 接 proofread UI、garbled cue 上游 ASR 糾錯（refiner 階段結構性無解 — seg46 類）、體育新聞 style gloss、cmn 書面語驗證、AI Rerun 重做 cue 過新 refine。

## 測試

1. pytest pure（`tests/test_written_refine.py`）：窗口 user 格式（前/本/後、邊界 i=0/i=N-1）、roster 注入（本句命中名先注入、SYSTEM 唔係 USER）、位置術語只 racing 計、`_glossary_name_set` ImportError fail-open、name-diff flag 記錄、`context_window=0` 退回逐段、空段 passthrough、cancel_check raise；fake llm 驗 prompt 內容 + parse
2. pytest 整合：`derive_aligned_output` refine 分支 thread glossaries → formal_refine 收到
3. P1.5 多 clip gating（上述，真 local Ollama）
4. E2E：重新處理一條有 zh 輸出嘅 yue 賽馬檔，核對書面語軌位置術語/馬名修正
