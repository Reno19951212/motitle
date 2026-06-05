# Design — 詞彙表 Review v2（output_lang 統一 post-derivation glossary stage）

**日期：** 2026-06-05
**範圍：** output_lang pipeline 嘅 glossary 應用。屬 MT/refiner prompt 行為 → 受 CLAUDE.md Validation-First 管制（落 code 前必須過 §8 stress test）。
**狀態：** 設計已 user-approved（方向）；待寫 spec review → writing-plans。

---

## Goal

令詞彙表（術語表 / Glossary）喺**而家嘅 output_lang 主流程**真正生效（目前完全未接駁）。用戶喺上傳彈窗揀一個或多個 glossary，系統喺 ASR→derive（refine/MT/pass）→OpenCC **之後**做一個統一嘅 glossary review stage，將輸出嘅專名（馬名、人名、術語）正規化成 glossary 嘅規範譯名，並守住「常用詞撞名」嘅 false-injection。

## 背景 / 證據

- **現狀（已核實）**：glossary 喺 output_lang derive 路徑零引用；proofread「套用」喺 output_lang 隱藏；只有舊 Profile-mode MT（`ollama_engine._filter_glossary_for_batch`，guard 死 en→zh）會注入。
- **研究**：[2026-06-05-glossary-v2-research.md](../research/2026-06-05-glossary-v2-research.md)（5-agent workflow，含真 Ollama probe）裁決：**獨立 post-derivation stage**（唔入 refiner，答用戶兩個 concern：refiner 零負擔 + glossary 睇乾淨最終中文）；**false-injection 係主導 ship/no-ship 風險**（唔係 follow-rate）；1350 條 full-inject latency 唔係 blocker（warm 0.6s/call）但對 refine 係 no-op（英文 key），filter 係正路。
- **Demo（真片）**：`diag_glossary_v2.py` 跑 The Winning Factor（en→zh MT，1350-term 賽馬 glossary，source-side）：
  - 無防守：42 段改，**3 段 false-injection**（`class→大文豪`、`dash→迅意` — glossary 真係有同名馬）。
  - **加源側防守**（多字放行、單字常用詞 deny）：39 段改，馬名 wins 全保留（火悟空/活力拍檔/榮駿大道/共享富裕/北斗福星…），**false-injection = 0**。
  - 證實:中文規範名 100% 由 glossary `target` 抽出（剝 `(H###)` suffix）；LLM 只做「擺位 + 判斷該唔該改」。

## User-approved 決定

1. **多表**：多表（ordered SET）+ 優先順序。
2. **語言支援**：全語對自動路由（按 glossary 嘅 source_lang/target_lang + derive mode）。
3. **套用時機**：處理時自動 + 校對頁可重套。

**Finalized parameters（2026-06-05）：**
- **衝突規則**：多表撞同一 match key → **排前嘅 glossary 贏**（揀選順序 = 優先；後表唔覆蓋）。
- **LLM 精修層 default**：**default ON**（toggle `#olGlossaryLlm` 預設開）。原因：alias-less glossary（如 racing 1350 條）淨確定性層只能剝 suffix + 確認，**改唔到英文留底/異寫嘅名**；要 demo 嗰種「Blazing Wukong → 火悟空」效果做 default,必須開 LLM。用戶可關閉做純確定性/快速模式。
- **CSV aliases backfill**：v1 **純文檔提示**（README 講「target 可含 (H###)、建議補常見錯寫做 alias」）；自動 helper 留 v2。

---

## A. 架構 — 統一 post-derivation glossary stage

新純模組 `backend/output_lang_glossary.py`（依 many-small-files）。喺 **任何 derive 結果 + `apply_script`（OpenCC）之後、persist 之前** 嘅同一個 slot 運行；refine / MT / pass **共用同一 stage**，只係內部 match 方向不同。

**兩層（確定性優先，LLM 升級）**：

1. **確定性層（無 LLM、microseconds）**
   - 剝 glossary target 嘅 `(H###)` 馬號 suffix（**必須永不漏入字幕**，suffix-leak = 0 係硬指標）。
   - Verbatim 命中：輸出已含 canonical target → 確認/保留。
   - 有 alias（將來 backfill）→ `{alias → target}` deterministic replace。
2. **LLM 精修層（per-segment filtered、opt-in by toggle）**
   - 只有被 candidate filter flag 嘅 segment 先送 LLM。
   - Prompt 重用 / 對齊 `app.py:GLOSSARY_APPLY_SYSTEM_PROMPT`（已 battle-tested「verbatim-wins / same-entity-only」），demo 嘅 `REVIEW_SYS`（馬名規範化 + 拒絕普通詞）係佢嘅 output_lang 版。
   - 中文規範名由 glossary `target` 提供，LLM 只擺位 + 判斷適用性。

> ⚠️ Demo 已證 1350 條冇 alias → 確定性層主力係 suffix-strip + verbatim 確認;**修 mis-rendered/英文留底嘅名要靠 LLM 層**。即係 LLM 唔係「罕有補漏」。v2 backfill 高頻 alias 可令確定性層接走更多。

## B. 多表（ordered SET + 優先順序）

- file entry 新欄 **`glossary_ids: List[str]`**（有序，popup 揀選順序 = 優先順序）。
- 合併規則：union 所有適用 glossary 嘅詞條 → build 一個 merged index；**同一 match key 撞到唔同 target，排前嘅 glossary 贏**（後面唔覆蓋）。
- 每個 glossary 獨立按自己 lang-pair 決定適用邊個輸出（§C）。一個 file 可同時有 en→zh + ja→zh 表，各自落各自輸出。

## C. 全語對自動路由

對「每個輸出語言 × 每個選定 glossary」決定 match 方向：

| 該輸出嘅 derive mode | 適用條件 | match 方向 |
|---|---|---|
| **MT**（跨家族，如 en→zh、ja→zh、en→ja） | `glossary.source_lang == 內容語言`（content_asr_lang(source)） | **源側** — glossary 英/日 source key 喺 segment 嘅 source text（en_text / 內容文字）出現 |
| **refine / pass**（中文輸出 zh/cmn/yue） | `glossary.target_lang == 輸出語言`（或同中文家族） | **目標側** — glossary 中文 target 喺已輸出中文出現 → canonicalize |
| 其餘（對唔上 source/target） | — | **skip 該 glossary 落該輸出** |

**Candidate guard（按 match 語言）**：
- **源側（en / ja）**：多字 source 一律放行（distinctive）；單字 source 必須**唔係常用詞**（per-language deny-list；en demo 已驗）。可加「源 occurrence 大寫」做加分但唔做硬條件（ASR 會 lowercase）。
- **目標側（中文）**：≤2 字 target 保守（容易 substring 撞中）；用中文字界（重用 `_make_glossary_term_pattern` 嘅 boundary class）。
- Filter 後預期每段 candidate 數 0–3 → 注入 block 細、prompt 安全。

## D. UX 改動（user 第 3 點）

| 位置 | 改動 |
|---|---|
| **上傳 popup**（`index.html` olOverlay） | 加「詞彙表 Review」**多選** selector（`#olGlossary`，可多選，順序 = 優先）+「LLM 精修」toggle（`#olGlossaryLlm`，對應 §A LLM 層 opt-in） |
| **POST /api/transcribe**（app.py） | 讀 `glossary_ids`（JSON array）+ 驗證每個存在 → 存 `entry["glossary_ids"]` + `entry["glossary_llm"]` |
| **校對頁**（proofread.html） | output_lang 重開「套用」→ **「重新套用詞彙表」**（改完手動 re-run glossary stage on 現有輸出）；header 顯示用咗邊幾個 glossary |
| **校對頁 — 詞彙對照 before/after**（右邊 detail panel） | 接通現有 stub「詞彙對照」欄（line ~2255）：渲染當前段嘅 `glossary_changes`，逐個 `before → after`（before 淡色/刪除線、after 高亮）+ glossary 名；**該段無詞條時顯示「此段無詞彙表詞條（未涉及）」** → 令用戶知道某些名冇變係因為 glossary 冇對應，唔係 bug。rail 行 `.rv-b-rail-flags` 加 📖 badge 標示有改動嘅段 |
| **Glossary.html**（CRUD + CSV import/export） | **不變**（已支援 `{source,target,target_aliases}` + source_lang/target_lang + 語言對 badge）。文檔提示「target 可含 `(H###)`，stage 自動剝」 |
| **檔案卡 / 校對頂** | 加「📖 已套詞彙表」indicator（由 `entry["glossary_ids"]` 派生） |
| **CSV 格式** | 3 欄不變;README 建議**補 aliases**（racing 1350 條冇 alias → 確定性層先接到更多） |

## E. Data model（最小改動）

- file entry 新欄：`glossary_ids: List[str]`（有序）、`glossary_llm: bool`。
- translation row 新欄：**`glossary_changes: List[{source, before, after, glossary}]`**（glossary stage 改字時記低，per-segment；空 list = 該段無詞條改動）→ 校對頁 before/after 顯示用。
- 重用：`GlossaryManager`（get / list / CSV）、`/api/glossaries*` CRUD、`GLOSSARY_APPLY_SYSTEM_PROMPT`、`_make_glossary_term_pattern`（字界）、`_make_ollama_llm_call`（LLM binding）。
- `by_lang` / `{lang}_text` / `aligned_bilingual` shape **不變**（glossary stage 只改 text 值）。

## F. Integration points（file:function）

1. `frontend/index.html` — `olOverlay` 加 selector；confirm handler 收集 `glossary_ids` + `glossary_llm`；`startTranscription` 將佢哋 append 入 `/api/transcribe` FormData。
2. `backend/app.py` — transcribe handler（讀 `source_language`/`script` 嗰度）驗證 + 存 `entry["glossary_ids"]`；`_run_output_lang` / `_run_output_lang_bound_base` / `_run_output_lang_cross` / `_run_output_lang_second*` load glossaries（`_glossary_manager.get`）+ thread。
3. `backend/output_lang_aligned.derive_aligned_output`（+ `build_aligned_bilingual`）/ `backend/output_lang_postprocess` — `apply_script` 之後 call `output_lang_glossary.glossary_stage(...)`；signature 加 `glossaries`（向後兼容 default None = 行為不變）。
4. **新** `backend/output_lang_glossary.py` — `build_merged_index(glossaries)`（剝 suffix + 優先序合併）、`route_for_output(glossary, output_lang, content_lang) -> 'source'|'target'|None`、`filter_candidates(text, index, side)`（含 guard）、`deterministic_apply(...)`、`llm_review(...)`（注入 llm_call）、`glossary_stage(segments, glossaries, output_lang, content_lang, llm_call, *, use_llm)`。
5. `frontend/proofread.html` — output_lang 重開套用掣 → 「重新套用詞彙表」→ 新 endpoint（或重用）re-run stage on 現有 translations；`renderDetail`（~L2159）嘅「詞彙對照」stub（~L2255）渲染當前段 `glossary_changes`（before→after + glossary 名 / 無詞條提示）；`_renderSegListBase` rail 行加 📖 badge（有 `glossary_changes` 時）。`loadSegments` output_lang 分支將 `t.glossary_changes` 帶入 `segs[i]`。
6. `backend/app.py` — 新（或擴）endpoint `POST /api/files/<id>/glossary-reapply`（output_lang re-run glossary stage on 現有輸出，回更新後 translations）。

## G. 範圍外（v2）

aliases 自動 backfill、per-glossary 用量統計、glossary 衝突預覽 UI、glossary 直接編入 refine/MT prompt（vs post-pass）、>2 語系混合表、glossary 影響 ASR。

## H. Validation-First gate（落 code 前必過）

擴 `diag_glossary_v2.py` 成完整 stress test（tracker `docs/superpowers/specs/2026-06-05-glossary-v2-validation-tracker.md`）：

- **Matrix**：{19-term broadcast, 1350-term racing} × {源側(en→zh), 目標側(refine)} × {確定性-only, +LLM} × {full, filtered}，cheap→expensive fail-fast。
- **Metrics + 門檻**：
  - **FALSE-INJECTION ≤ 1.0%**（>2% auto-reject）← 單一最 gating 數字
  - **FOLLOW-RATE ≥ 85%**（gold-applicable terms 正確 canonicalize）
  - **SUFFIX-LEAK = 0%**（`(H###)` 漏入字幕）
  - QUALITY：over-cap ≤+1pp、empty ≤+0.5pp、0 新 meaning-drift（30-seg 人手 audit）
  - LATENCY：post-pass 只計 flag 段；19→1350 follow-rate 跌 ≤5pp
- **Prototype**：食 registry 已轉錄段（mlx-whisper large-v3 輸出，唔重跑 ASR）+ production Ollama qwen3.5:35b。需 `gold_applicability.json`（逐 clip 人手標 applicable term）；false-injection floor 可用「講騎師唔講馬名」嘅片**免人手**先量。
- **已有第一信號**：demo guard → false-injection 3→0、wins 全保留。

## Testing strategy（實施階段）

- **Unit**：`output_lang_glossary` 純函數（build_merged_index 優先序 / route_for_output 各語對 / filter guard 拒常用詞 + 放多字 / deterministic suffix-strip / llm_review mock）。
- **Regression**：無 `glossary_ids` 時 derive 逐 byte 不變（default None）；refine/MT/pass 不受影響；既有 output_lang/crosslang/bilingual suite 全綠。
- **Integration**：live re-run（真 mlx + Ollama）對 Winning Factor（en→zh 源側）+ 一條粵→書面（目標側）+ 多表（broadcast+racing）；對齊 stress tracker。

## 下一步

User review 呢份 spec → writing-plans（逐 task TDD）→ **先完成 §H stress test（gate）** → subagent-driven 實施。
