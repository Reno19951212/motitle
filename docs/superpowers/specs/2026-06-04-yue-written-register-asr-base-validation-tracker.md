# Validation Tracker — 粵語語音 → 中文書面語：ASR base 選擇（zh-direct vs yue+convert）

**日期：** 2026-06-04
**範圍（CLAUDE.md Validation-First 管制）：** output_lang 路由 `route_output('yue','zh')` 嘅 ASR base 選擇 — 屬 ASR/MT engine 行為，落代碼前必須先量化驗證。
**狀態：** ✅ **Validated（user 提出嘅假設成立）** — 待 user review evidence → brainstorm → spec → plan。

---

## 假設（user 提出）

對「粵語語音、中文書面語輸出」嘅情況，現行 production 用 **Whisper 直接 `language='zh'` 轉錄**（route_output('yue','zh')=='whisper'）會有質量問題；改成 **先用 `language='yue'` ASR（口語，最準）→ 再 LLM 轉書面語** 應該意思更準確。

## 兩條 path（其餘 post-processing 完全相同，只差 ASR base）

| | Path A（現行 production，baseline） | Path B（提案） |
|---|---|---|
| ASR | mlx-whisper large-v3 `language='zh'`（直出書面，`cond=False`） | mlx-whisper large-v3 `language='yue'`（準確口語，`cond=False`） |
| Refiner | `formal_refine`（qwen3.5:35b-a3b-mlx-bf16, temp 0.3, `zh_written_register_v6` prompt） | 同 A 完全一樣 |
| Script | OpenCC `s2hk`（apply_script trad） | 同 A 完全一樣 |

## 方法（production-aligned，零 mutation）

- 用同一條 毛記電視 clip 嘅 **兩個真實 production 輸出**（registry 已有）：
  - yue（file `039d53ee8d1c`，525 segs）＝準確口語 ASR → **B 嘅 base + 意思 ground-truth reference**
  - zh （file `824424f99efc`，496 segs）＝現行 production 書面語 → **Path A baseline（user 唔滿意嗰個）**
- B ＝ 對 yue base 行 **production `formal_refine` + `apply_script`**（同 A 完全相同嘅 post-proc，只係 ASR base 換成 yue）。
- 比較：① 書面語 register marker rate（客觀）② time-window 對 yue reference 嘅意思忠實度（LLM judge，A/B 位置對調去 bias）③ B 轉換完整性。
- Prototype：[`backend/scripts/crosslang_prototype/diag_yue_written_vs_direct.py`](../../../backend/scripts/crosslang_prototype/diag_yue_written_vs_direct.py)（NOT production code，只讀持久化輸出）。
- 樣本：首 200 yue segs（≈ 5.3 分鐘，39 個 8 秒 window）。

---

## 結果 — judge = qwen3.5:35b-a3b-mlx-bf16（200 segs / 39 windows）

| 指標 | A（zh-direct，現行） | B（yue+convert，提案） | 結論 |
|---|---|---|---|
| 書面語 marker /100 字（越低越乾淨） | **0.0** | **0.24** | ⚖️ 平手（兩者都乾淨；yue base 原本 25.17） |
| 意思 head-to-head 贏出 window | 9（23.1%） | **26（66.7%）**（tie 4） | ✅ B 大幅勝 |
| **對音頻有意思錯誤嘅 window** | **30（76.9%）** | **14（35.9%）** | ✅ B 將意思錯誤率 **減半** |
| 字數 median / max / >28 | 7 / 35 / **1** | 8 / 20 / **0** | ✅ B 略緊、無爆 cap |
| B 轉換完整性（noop / len-median / blowup>3.5×） | — | 0% / 1.0× / **0** | ✅ 無幻覺膨脹 |

## 結果 — 獨立 judge = qwen3.6:27b（de-bias，重用同一 B）

> 因為 B 由 qwen3.5 生成，用 qwen3.5 做 judge 有 self-bias 風險。用唔同 model（qwen3.6:27b）重判同一批 A/B/yue 以確認方向。

| 指標 | A（zh-direct） | B（yue+convert） | 對 qwen3.5 judge |
|---|---|---|---|
| 意思 head-to-head 贏出 | 8（20.5%） | **26（66.7%）**（tie 5） | ✅ 一致（B 同樣 66.7%） |
| 對音頻有意思錯誤嘅 window | 31（79.5%） | **13（33.3%）** | ✅ 一致（B 仍減半，甚至更低） |
| register 贏出 | 8 | **26**（tie 5） | ✅ B 更強 |

> **結論：兩個獨立 judge model 結果近乎一致（B 意思贏 66.7% / 意思錯誤率 A≈77-80% vs B≈33-36%）→ 唔係 self-judge artifact，方向 robust。**

---

## 代表性例子（A 漏失粵語特定意思，B 保留）

- `[72s]` 口語「你係咪識穿咗男朋友喺東南亞**叫雞**」
  - A：「你是否已察覺男友在東南亞」 ← **完全漏咗「召妓」**，句子變無意義
  - B：「你是否察覺男友在東南亞**召妓**？」 ← 保留核心意思 + 正確疑問句
- `[64s]` 口語「Subscribe 咗我哋**未**呢」（疑問）
  - A：「**未**訂閱我們」（變成陳述：未訂閱）
  - B：「**是否已訂閱？**」（正確疑問）
- `[104s]` 口語「你點樣自取佢**叫雞**呢」
  - A：「如何自行前往**找他**」（漏「叫雞」） / B：「如何自行**叫雞**？」（保留）

## 誠實 caveats（未可一刀切）

1. **B 唔係零錯**：B 仍有 36% window 有意思錯誤 —— 部分來自 yue ASR 本身喺好亂嘅對話音頻有錯（如「我好真啲叫雞嘅男人」本身已 garbled），部分來自轉換誤讀（「分唔哂」→「分配」、「好少事」→「小事」）。B 係**大幅改善**而唔係完全解決。
2. **樣本範圍**：單條 clip 首 5.3 分鐘、對話 talking-head 內容（正正係 user 呢類 YouTube 片）。新聞/廣播類內容未必同樣表現，建議擴樣再 confirm。
3. **Judge 主觀性**：意思忠實度由 LLM 判（已位置對調 + 獨立 model 交叉驗證）；最終以 human eyeball 為準（Validation-First：human 係 final arbiter）。

## 架構含意（若 confirm 落實）

- B ≈ 現有 **aligned_bilingual** 路徑嘅做法（`derive_mode(yue,zh)=='refine'`，refine yue base）。即係將**單語言** `粵→zh` 由「Whisper-zh 直出」改成「content ASR(yue) + formal_refine」。
- 改動點：`output_lang_router.route_output('yue','zh')` + `app.py::_produce_output_lang` 嘅 zh 分支。
- **附帶 efficiency win**：若同時要 口語(yue)+書面(zh)（user 正正咁做），yue ASR 只跑一次、書面由佢 derive，慳一個 Whisper pass（= O1 shared-base）。

## ✅ 整合驗證（live，real mlx + Ollama，90s 毛記 clip，2026-06-04）

落代碼後經 `backend/scripts/crosslang_prototype/integ_yue_base.py` 跑 3 個 flow（真 mlx-whisper large-v3 + 真 Ollama qwen3.5:35b-a3b-mlx-bf16，直接行新 dispatch `_run_output_lang`）：

| flow | ASR | 書面(zh) | 其他軌 | aligned |
|---|---|---|---|---|
| 1 書面單一 | **1× Whisper-yue** | clean（marker 0.0）「她發現男友前往東南亞**召妓**。」 | — | 52/52 |
| 2 書面+口語 | **1× shared yue** | marker 0.0 | yue = raw 口語 marker 25.1「嘩今日個case正呀」（== 持久化口語，逐句一致） | 52/52 |
| 3 書面+英文 | **1× shared yue** | clean 書面 | en = real MT「He still refuses to admit it.」 | 52/52 |

3/3 verdict ✅。確認：① source-driven（全部一次 Whisper-yue）② 書面由 yue base derive，**召妓 意思保留**（正正係 Whisper-zh 直出會漏嗰個）③ **口語軌 byte-match 持久化口語**（零 regression）④ 多輸出共用一次 yue ASR（efficiency win）⑤ aligned grid == segs（配對完美）。Backend unit + regression（output_lang/crosslang/bilingual/aligned/dispatch suite）全綠；auth API 檔各自隔離全綠（full-suite 401 = pre-existing session-pollution baseline）。

## 狀態：✅ Validated + Implemented + Integration-verified

Spec [2026-06-04-…-design.md](2026-06-04-yue-written-register-asr-base-design.md) / Plan [2026-06-04-…-plan.md](../plans/2026-06-04-yue-written-register-asr-base-plan.md)。Commits（branch feat/output-language-pipeline）：`ce487f8`(validation+spec) → `471f3eb`(plan) → `33fee2f`(實作+tests)。
