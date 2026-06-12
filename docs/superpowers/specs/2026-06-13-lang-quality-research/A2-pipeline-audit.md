# A2 — 現有 pipeline 審計：點解 glossary stage 救唔到譯音錯誤 + 可掛鈎位

日期：2026-06-12 ｜ 目標檔：09e0e3679f35（yue 源，48 段）｜ Stack：production（output_lang_glossary.py 原裝代碼 + Ollama qwen3.5:35b-a3b-mlx-bf16 @0.3）

## TL;DR

現有 glossary stage 對呢 48 段嘅實質修復數 = **0**。對住 A1 error catalog（36 個 high-confidence 錯誤）：deterministic variant **recovered 0 / missed 36**；LLM variant（production qwen3.5:35b-a3b-mlx-bf16）**recovered 0 / missed 36 / false-positive 1**（idx4 半形逗號→全形，純標點誤改 + 誤記一條 glossary_change）。36 個錯入面有 **24 個 glossary 明明有正典名**（in_glossary=true）— 即係話唔係 coverage 問題咁簡單，係**候選過濾層（candidate gate）令 LLM 根本見唔到錯字嗰啲段**：同音字錯誤喺字面 string match 下產生零候選 → LLM 一次都冇被叫去處理佢哋。結構性缺陷，唔係 prompt 問題。

## 1. 結構分析：四重 gate，每重都擋住譯音錯誤

對本檔（glossary: en→zh，content=yue，outputs=yue[pass]/zh[refine]）：

1. **路由 gate** — `route_for_output`（output_lang_glossary.py:184-217）：pass/refine mode 一律行 **target-side**（:212-215）。即係要靠「規範中文名」字面出現喺輸出文字先有得玩。Source-side（英文名 regex match）只限 `derive_mode=='mt'` 而且要 `gl_src == content_lang`（:207-210）— en→zh glossary 對 yue 源完全冇 source-side 可言（就算第二語言出 en 都 route None，因為 gl_src 'en' ≠ content 'yue'）。
2. **Target verbatim gate** — `_filter_target_side`（:598-658）：候選條件係 `t in text`（:631）或 alias `in text`（:644-646）。**同音字錯誤 = 字面唔同 = 零候選。** 升制快車 ≠ 星際快車，永遠唔 match。本 glossary 1352 條全部冇 `target_aliases`，所以 alias 路完全冇用。
3. **LLM gate** — `glossary_stage`（:523）`if use_llm and all_cands:`：**冇候選嘅段 LLM 一次都唔會叫**。錯字段（seg 1/2/3…）正正係零候選段。就算有候選嘅段（seg 44 有「精算暴雪」verbatim），LLM 對照表（llm_review :340）都只包含嗰段嘅候選 — seg 44 入面嘅「升制快車」錯字，table 冇 STELLAR EXPRESS 條目，LLM 想救都冇權救。
4. **≤2 字 guard** — `_filter_target_side`（:625-626）：target ≤2 字直接跳過 — 「翠紅」明明 verbatim 出現喺段 17 都唔會成為候選（亦即永遠唔會送 LLM confirm）。

Deterministic 層（`deterministic_apply` :269-315）只做 alias→canonical 替換；冇 alias 嘅 glossary = 純 no-op。

## 2. 實跑 baseline（48 段原裝餵入 production `glossary_stage`）

跑法：`/tmp/lq-research/protos/A2_glossary_stage_baseline.py`，`sys.path` 直 import worktree 嘅 `output_lang_glossary`，mode=(yue,yue,'pass')，glossary = 賽馬 1352 條。

| 量度 | use_llm=False | use_llm=True（Ollama qwen3.5:35b-a3b-mlx-bf16 @0.3） |
|---|---|---|
| 有候選嘅段 | 12 / 48 | 12 / 48 |
| LLM 實際被叫次數 | 0 | 10（2 次超時 @300s：idx 6、44） |
| 文字真係改咗嘅段 | 0 | 1（idx4 — 純標點 `,`→`，`） |
| glossary_changes 記錄 | 0 | 1（誤記：標點 diff 被 fallback 歸因落 BEAUTY WAVES） |
| **A1 catalog（36 high-conf）recovered / missed** | **0 / 36** | **0 / 36** |
| false-positive 改動 | 0 | 1（標點） |
| 耗時 | 0.03s | 1508.8s（LLM 時間 ~909s，平均 91s/call，加 2×300s 超時） |

12 段候選**全部係「已經啱」嘅 verbatim 確認**（信心星×3、笑傲江湖×3、精算暴雪×3、美麗第一×2、友愛心得×1、星際快車×1 — seg 43 嗰個係 ASR 自己出啱咗）。**冇一個候選對應錯字 span。** 10 次 LLM call 全部原文返回（除咗 idx4 改標點）— LLM 行為正確，佢眼前根本冇嘢可改：對照表只包含「已經啱」嘅名。

A1 catalog 對照逐類睇：
- 36 個 high-conf 錯誤入面 **24 個 in_glossary=true**（升制快車→星際快車、精算部說→精算暴雪、幸運有利→幸運有您、好有心得→好友心得、標之星河→錶之星河 等）— glossary 有正典名都救唔到，證明 gate 係主因。
- 12 個 in_glossary=false（內藍米字→內欄位置 等 racing_term/賽馬術語）— gate 之外仲有 coverage 缺口，glossary 本身只有馬名冇術語。
- seg 44 雙重示範：段內有 verbatim「精算暴雪」→ 有候選 → 會叫 LLM，但對照表只有 RAGING BLIZZARD 一條 — 同段嘅「升制快車」「標之星我」「好有心得」錯字，LLM 想救都冇權救（table 冇對應條目）。
- 「翠紅」（2 字名）就算 verbatim 啱都被 ≤2 字 guard 排除，永遠唔成候選。

**成本觀察**：pass track 行 use_llm=True，10 次 call 共 ~909s LLM 時間，換嚟 0 個實質修復 + 1 個標點誤改 — 而家嘅 LLM review 喺 yue passthrough track 上係純開銷。另外 prototype 300s cap 下 2/12 超時；production OllamaTranslationEngine timeout 180s，同樣 failure shape（段落原文返回，唔會 crash）。

## 3. 可掛鈎位（hook points）完整清單

### H1 — ASR `initial_prompt`（decoder bias，上游醫）
- **讀入點**：`asr/mlx_whisper_engine.py:55`（`self._config.get("initial_prompt")`）→ :68-69 傳入 `mlx_whisper.transcribe`。Schema 已支援（:150-156）。
- **output_lang 路徑而家冇傳**：override dict 由 `platform_backend.resolve_asr_override`（platform_backend.py:44-60）產生 — **冇 initial_prompt key**。包裝喺 `app._output_lang_asr_override()`（app.py:369-377），喺 `transcribe_with_segments` 內 `asr_cfg = profile["asr"]`（app.py:1772-1776，task_override 已示範點樣 immutably merge）流入 engine。
- **掛法**：(a) per-job 加 `initial_prompt_override` 參數落 `transcribe_with_segments`，喺 app.py:1773-1775 同 task_override 一齊 merge；call sites：bound-base app.py:615-619、_produce_output_lang app.py:458-470、second-pass app.py:735-739、rerun `_rerun_asr_engine` app.py:261-263。(b) 或直接喺 `_output_lang_asr_override()` 度按檔案 glossary 砌 prompt。
- **改動範圍**：細（~20 行 + tests）。
- **⚠️ 實證限制**：production override 用 `condition_on_previous_text=False`；mlx_whisper 源碼（同 openai-whisper 一致）每個 window 之後 `prompt_reset_since = len(all_tokens)` → **initial_prompt 只影響第一個 ~30s window**。108.6s 音訊有 ~4 個 window，後 3 個完全唔受 prompt 影響。再加 prompt 上限 ~224 tokens，1352 條馬名塞唔晒（要預選出賽馬匹）。呢個 hook 對全片糾錯**作用有限**，除非反轉 cond=True（CLAUDE.md 已知會放大錯誤）。

### H2 — ASR 後 / derive 前（base 糾正 stage）⭐ 最高槓桿位
- **位置**：`_run_output_lang_bound_base`（app.py:593）— base 砌好（app.py:620-621）之後、clause_split（:624-625）/`derive_aligned_output`（:628-631）之前。
- **點解最正**：yue 源全家行呢條路（app.py:570-575，do_clause_split=False）。base 係**所有**輸出語言嘅 1:1 derive 源頭 — 喺度修一次，口語 passthrough、書面語 refine、en/ja MT 全部自動受惠。仲會 persist 做 `content_asr_segments`（app.py:636-639），所以 glossary-reapply（app.py:5010-5080，由 cached base re-derive）、加第二語言（app.py:658+，用 cached base）都自動繼承修正。
- **要兼顧嘅旁路**：`_produce_output_lang`（app.py:429；whisper-direct base :458-463 + asr_mt cache :465-471 — cmn/en/ja 源用）同 AI Rerun 單 cue 路（app.py:5908-5921）— 同一個糾正函數插三個位就齊。
- **改動範圍**：中（新 pure module，例如 jyutping 索引 match + LLM 確認；三個 call site；唔使掂 glossary_stage 本身）。**口語 yue track 而家全程零 LLM**（pass mode 純 copy，output_lang_aligned.py:52-54）— 呢個 hook 係唯一可以醫到口語 track 嘅位（除咗 H3）。

### H3 — glossary_stage 內加 phonetic 候選層
- **位置**：`output_lang_glossary.py` — 喺 `_filter_source_side`/`_filter_target_side`（:552-658）旁邊加 `_filter_phonetic_side`：用 jyutping（yue）/pinyin（zh）索引 glossary targets，對段文字 n-gram 同音/近音 match 產生 `side:"phonetic"` 候選；候選自然流入現有 LLM gate（:523）同 llm_review 對照表（:340）。
- **連帶要改**：`scan_track`（:665-743，校對頁 review scan 用同一套 filter — 唔同步會 UI/pipeline 不一致）；`glossary_changes` 記錄格式不變（add-only side 值）。
- **改動範圍**：中。好處：留喺現有 stage 內，routing/persist/審計鏈全部現成；壞處：對 zh refine track 嚟講 stage 行喺 refine+OpenCC **之後**，refine 可能已經將錯字改寫到 jyutping 都唔似；而 glossary 冇收嘅賽馬術語（內欄位置 等 12 個 in_glossary=false 項）任何 glossary hook 都救唔到。
- **同音證據**：升制快車 vs 星際快車 jyutping 完全相同（sing1 zai3 faai3 ce1，CONTEXT 已驗證）— phonetic index 一定 match 到呢類。

### H4 — refine prompt（書面語 track only）
- **位置**：`output_lang_postprocess.formal_refine`（output_lang_postprocess.py:58-81）— system prompt 喺 :64 由 `_refiner_prompt(style)` 揀（generic/racing JSON，:30-31 載入 `config/prompt_templates_v5/refiner/`）；per-cue `llm_call(sysp, txt)` :73。
- **掛法**：threading glossary 名單入 sysp（或 per-cue user message 加候選馬名 hint）。caller 係 `derive_aligned_output`（output_lang_aligned.py:51），signature 已經有 glossaries 參數可借。
- **改動範圍**：細。**致命限制**：只影響 zh/cmn refine track — yue 口語 track（用戶主要投訴對象）係 pass mode，完全唔經呢度。refiner 每 cue 只見一句，冇音訊、冇上下文，要佢憑字面估「升制」應該係「星際」屬於賭博（同 H3 嘅 LLM 確認比，佢冇對照表錨點）。

### H5 — MT prompt（en/ja 輸出 track）
- **位置**：`translation/crosslang_mt.build_mt_system_prompt`（crosslang_mt.py:57-63）+ `_MT_SYS`「保留專有名詞」規則（:28-31）。
- 補充 routing 缺陷：en→zh glossary 喺 yue 源 + en 輸出嘅 mt mode route None（`gl_src 'en' != content 'yue'`，output_lang_glossary.py:207-210）— 想中→英反向用 glossary 要另一張表或反向索引。改動範圍細，但對本案（中文輸出）唔係主菜。

### H6 — 校對頁人手鏈（已存在，非自動）
- `scan_track`（output_lang_glossary.py:665-743）+ `/api/files/<id>/glossary-apply-item`（app.py:5194，glossary_review.py pure 模組）+ legacy `/api/files/<id>/glossary-apply`（app.py:3308）。全部同樣受 verbatim gate 限制 — 掃描層都係字面 match，錯字段照樣零 item。如果 H3 落地，scan_track 同步擴展可令校對頁都見到 phonetic 建議。

## 4. 結論

- **Baseline 證實**：現有 glossary stage 對 A1 catalog 36 個 high-conf 錯誤嘅修復率 = 0%（0 recovered / 36 missed / 1 false-positive），且結構上不可能 >0（候選 gate 係字面 match，同音錯字零候選 → LLM 冇得叫）。
- **Coverage 修正（推翻 CONTEXT.md 假設）**：「幸運有你/標之星河 MISSING」唔成立 — glossary 正典寫法係 `幸運有您 (E356)`／`錶之星河 (J343)`／`好友心得 (H303)`。對照 A1 roster，本場 **10 匹馬 100% 喺 glossary** — 馬名錯誤（25 個，high-conf 24 個 in_glossary=true）純粹係 gate 問題。Coverage 缺口只係賽馬術語（內欄位置/沙田銀瓶 等 12 個 in_glossary=false，glossary 只收馬名）。
- **最值得投資**：H2（base 糾正 stage，全 track 受惠 + persist 繼承）配 H3 嘅 phonetic 索引做候選產生器（升制快車↔星際快車 jyutping 完全相同，phonetic index 必中）；H1 受 cond=False first-window 限制只可做輔助；H4/H5 只係 prompt 加固，醫唔到口語 track。
- **附帶觀察**：pass track 嘅 use_llm=True 而家係純開銷（~909s LLM 時間換 0 修復 + 1 標點誤改）— 任何新方案落地時可以考慮對 pass track 改寫候選邏輯而唔係照搬 LLM confirm。

## 檔案
- 量化結果：`/tmp/lq-research/results/A2-baseline-run.json`
- Prototype：`/tmp/lq-research/protos/A2_glossary_stage_baseline.py`
