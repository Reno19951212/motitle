# Profile MT 鄰段意思重複 — 分析報告（EN→Cantonese 書面語）

**日期**：2026-05-31 ｜ **狀態**：Diagnosis + options（**未改任何嘢**；MT 改動受 Validation-First 管制）
**檔案**：`f422c01566ca`（YTDown FIFA Club World Cup Interview Haris Zeb），Profile `dev-default`（name「English to Cantonese 書面語」），106 段。
**方法**：4-angle workflow（quantify / MT 機制 / 解決方案 / ASR 分段）+ synthesis，我再獨立核對代碼路徑 + 翻譯引擎身份。

---

## 1. 症狀 + 量化
整體翻譯質素好，但**相鄰字幕意思重複**。量化（全 106 段）：
- **ASR 片段化**：84.9%（90/106）source 段係 mid-sentence fragment（無句尾標點 / 細階開頭），平均 ~7 字/段。e.g. #0「Okay, Haris, you have been in the」+ #1「US for a few days already.」係**一句被切兩段**。
- **鄰段意思重複**：14.3%（15/105 鄰對）共享關鍵詞 —— 美國(#0/#1)、世界冠軍球會盃(#2/#3)、奧克蘭(#5/#6)、賽事(#10/#11,#18/#19)、巴基斯坦(#19/#20)、榮耀(#22/#23)、支援(#39/#40)。
- **加字/潤飾**：21.7%（23/106）ZH 加咗 source 無嘅修飾（確實/令人振奮/充滿期待/數日之久/漫長旅程…）。

## 2. Root cause（已核實）
**Fragment 輸入 + 逐段「補成完整句」+ 長度目標 padding，而所有 sentence-coherence mode 全部 OFF。**
- dev-default config：`use_sentence_pipeline=False`、`translation_passes=1`、`alignment_mode=""` → `_select_translation_strategy()`（app.py）回 **`batched`**（已核實 config + 代碼路徑）。
- Batched 路徑（`translation/ollama_engine.py`，`batch_size=5`）：`_build_user_message` 用 `_detect_sentence_scopes` **將還原嘅完整句作 context 同時餵畀組成嗰句嘅每一段** + 滑動窗 previous-translation context；加 `SYSTEM_PROMPT_FORMAL` 規則「**完整保留主謂結構，避免省略主語**」+「**每行目標約 20–28 字**」→ 逼模型將每個 fragment **補成一句完整可朗讀句 + 加字湊夠長度**。結果：同一句嘅兩三個 fragment 各自被譯成完整意思 → 相鄰重複。
- `translation_passes=1` → 唔關 Pass-2 enrich 事；alignment / sentence-pipeline 都 OFF。
- ASR 安全網接唔到：en.json `merge_short_max_words=2`（只併 ≤2 字段），但 fragment 係 5–8 字；而 `max_words_per_segment=8` cap 令 7 字 fragment 同鄰段併會超 8 字 → 拒絕（50/60 併唔到）。

## 3. ⚠️ 附帶發現：profile 引擎身份
dev-default 嘅 `engine="qwen3.5-35b-a3b"` + `openrouter_model="anthropic/claude-sonnet-4.5"`。但 `create_translation_engine` 係**睇 `engine` field**：`"qwen3.5-35b-a3b"` → **OllamaTranslationEngine**（本地 `qwen3.5:35b-a3b-mlx-bf16`）。**`openrouter_model` 完全冇用**（只有 `engine="openrouter"` 先會行 Claude）。即係而家實際譯緊嘅係**本地 Ollama qwen3.5-35b**，唔係 Claude Sonnet 4.5。（你覺得「非常好」嘅質素 = qwen3.5-35b 嘅出品。）—— 呢個 stale/誤導 config 值得順手清。

## 4. 解決方案（ranked；未實施）
| # | 方案 | 機制 | 工夫 | 風險 | 評 |
|---|---|---|---|---|---|
| **1** | **`use_sentence_pipeline=true`** | pySBD 將鄰近 EN fragment 併成完整句 → **整句譯一次** → 按比例 redistribute 返各段。直接消滅「逐段補句」 | **Config-only** | 低（EN source pySBD 已驗證；time-gap guard 防跨人併）。殘留：比例 redistribute 可能令某段超 char cap（[LONG]） | **首選** —— 直擊 root cause、config-only、最低風險、EN source 適用 |
| 2 | `alignment_mode="llm-markers"` | 同上併句，但用 `[N]` marker 切返 | Config-only | 中（marker ~10% parse 失敗→fallback；mt-quality-research 記 13% boundary 微碎段 + prompt-example leak） | 次選 fallback（方案 1 出 over-cap 先用）|
| 3 | `batch_size=1`（single-segment）| 每段孤立譯、禁加外部資訊（v3.8 SINGLE_SEGMENT_PROMPT）| Config-only | 中（消重複但變**choppy** —— 對 incomplete EN fragment 會出 1-2 字斷句；該 mode 為 zh→zh 同源設計）| 不建議（重複換 choppy）|
| 4 | Prompt 收緊（反重複/反 padding）| 加負向約束入 SYSTEM_PROMPT | **Code change** | 高（band-aid，唔解 root cause；v3.18 先例：prompt example 會 leak）| 不建議 |
| 5 | ASR 階段 merge fragment | 譯前喺 segment_utils 併短段 | **Code change + 要 re-transcribe** | 中（失邊界、要升 8 字 cap、修唔到已譯嘅檔）| 不建議 |

## 5. 建議
**首選方案 1（`use_sentence_pipeline=true`）** —— config-only、直擊 root cause、EN source 適用、避開 llm-markers 嘅 13% boundary 失敗。方案 2 留作 fallback。

**Validation-First（MT 改動強制）**：唔可以直接 flip config ship。要先 ——
1. **Prototype 量化**（用 production stack = profile 實際引擎 **Ollama qwen3.5-35b**；若要對齊 CLAUDE.md 嘅 OpenRouter qwen3.5-35B 亦同模型家族）：對 `f422c01566ca` 用 `use_sentence_pipeline=true` re-translate，量度同 3 個 baseline 指標 vs 而家：鄰對重複（target « 14.3%，已知 #0/#1、#2/#3、#5/#6、#18-20、#22/#23、#39/#40 唔再重複）、padding（< 21.7%）、**新 guard：[LONG] over-cap 率唔可以 regress**；抽 20-30 段睇自然度 + off-by-one timing。
2. 記入 `docs/superpowers/specs/YYYY-MM-DD-validation-tracker.md`（✅/❌/⚠️）。
3. User review 證據後先 brainstorm → spec → plan → code。若出 over-cap regression → 升方案 2 再驗。

**本報告 = 診斷 + 選項，唔實施。**
