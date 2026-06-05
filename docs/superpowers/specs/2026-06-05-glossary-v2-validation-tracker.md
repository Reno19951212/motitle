# Validation Tracker — 詞彙表 Review v2（output_lang）

**日期：** 2026-06-05
**範圍（CLAUDE.md Validation-First）：** glossary 應用到 output_lang refine/MT prompt 行為。落 production code 前嘅 gate。
**狀態：** ✅ **源側完成（已上線整合驗證）** — false-injection floor ✅ 0；源側 follow-rate gold-confirmed 100% + SHIPPED-code 整合重現（43 occ / 9 名 / 0 false-inj）。目標側 follow-rate 留 v2（floor 已 0）。

Spec：[2026-06-05-glossary-v2-design.md](2026-06-05-glossary-v2-design.md)｜Plan：[../plans/2026-06-05-glossary-v2-plan.md](../plans/2026-06-05-glossary-v2-plan.md)｜Research：[../research/2026-06-05-glossary-v2-research.md](../research/2026-06-05-glossary-v2-research.md)

---

## ✅ False-injection floor（主導 ship/no-ship 風險，candidate-filter 層，免 Ollama/gold-label）

研究裁決 false-injection >> follow-rate 係 gating。呢個 floor 量「唔應該套嘅段被套」嘅基線。

| Floor cell | 無防守 | 加防守 | 防守規則 |
|---|---|---|---|
| **源側 en**：Winning Factor（`17b6d55ef43b`）× 賽馬 glossary（1350） | **3**（`class→大文豪`、`dash→迅意` — glossary 真有同名馬） | **0** | 多字 source 放行；單字 source 若係常用英文詞 → reject（`output_lang_glossary.is_name_candidate`） |
| **目標側**：賽馬 glossary（1289 獨特中文名）× 非賽馬 clip（`2c7b503ee5df`） | 0 | 0 | 賽馬中文馬名夠獨特，零 coincidental |
| **目標側**：broadcast glossary（19，含 `字幕`/`和`/`球會`）× 中文 clip（`2c7b503ee5df`） | **2**（`字幕`、`和` coincidental） | **0** | ≤2 字 target 保守 skip（中文字界） |

**結論**：源側（常用詞 deny）+ 目標側（≤2 字 skip）兩個 guard 各自將 false-injection 壓到 **0**。Gate 嘅最關鍵數字綠燈。

## ✅ Follow-rate（gold-confirmed，源側）

**Gold-label（user-confirmed 2026-06-05）**：[gold_applicability_winningfactor.json](../validation/glossary-v2/gold_applicability_winningfactor.json) — Winning Factor（en→zh 源側）× 賽馬 glossary。User 確認：`CLASS`/`DASH` 喺片中係「班次/衝刺」唔係嗰兩隻馬（**not applicable**）；其餘 9 個馬名真係指嗰隻馬（applicable）；無漏咗馬名。Gold = **39 段、43 個 applicable occurrence**。

**Formal FOLLOW-RATE = 43/43 = 100%**（對 guarded clone `wfglossary002` 計：所有 gold-applicable 馬名 occurrence 正確 canonicalize 成 glossary `target`；`CLASS`/`DASH` 正確冇套 → false-injection 同步 = 0）。≥85% 門檻 **遠超**。

> ⚠️ 目標側（粵→書面）follow-rate 未做（floor 已 0）— 需一條真係講馬名嘅粵語片;user 暫接受「源側 100% + 兩側 floor 0」做 Phase-1 起步 gate。

## ✅ Phase 4 — 整合驗證（SHIPPED code，真 Ollama，2026-06-05）

落 production code（commits `246a771`/`045868a`/`2246828`/`55c2a6c`）後，用**已整合嘅 `output_lang_glossary.glossary_stage`**（即真實上線 path，唔再係 prototype）+ 真 Ollama `qwen3.5:35b-a3b-mlx-bf16` 重驗源側：

| 整合測試 | 檔 | 結果 |
|---|---|---|
| **源側 follow-rate（gold 重現）** | Winning Factor `17b6d55ef43b`（en→zh, mt mode, 賽馬 1350 表） | **39/282 段有 candidate → 入 LLM；43 個 change occurrence、9 隻 gold 馬名全部 canonicalize**（火悟空/活力拍檔/燈胆將軍/喜慶寶/錶之星河/榮駿大道/共享富裕/北斗福星/翠紅），29s。對齊 gold（43 applicable occurrence / 9 names）。 |
| **False-injection（整合層重驗）** | 同上 | **CLASS→大文豪 / DASH→迅意 = NONE ✅**；`\bACE\b` word-boundary 正確唔中 "race/place" substring。 |
| **Endpoint end-to-end** | `POST /api/files/<id>/glossary-reapply` on 騎師訪問 `591daafc9f4b`（en→zh, racing, 52 段） | **HTTP 200、47s、`changed_count:0`** —— 正確：該 clip 無真實 glossary 馬名（唯一 'ACE' 係 "race" 內 substring，word-boundary 正確排除）。證明 endpoint 由 cached base 1:1 re-derive（無 re-ASR）跑通。 |

**整合期捉到（非 production bug，diagnostic 自身）**：`glossary_stage(...)` 嘅 `derive_mode` 參數係 **string**（`"mt"`/`"refine"`/`"pass"`），非 function；`derive_aligned_output` 內部 `mode = derive_mode(content,output)` 計好先傳，整合 path 正確。
**已知 v1 minor（非 blocker）**：個別 source-side `before` label 可能係跨名 fragment（e.g. `Blazing Wukong」與「Amazing Partners`），但 `after`（canonical 名）永遠正確 —— 校對頁 before/after 顯示輕微 cosmetic，留 v2 prompt 調。
**Side effect（dev registry）**：591 reapply 重 derive 咗其 zh translations（同等質量重生），無備份；dev 資料可接受。

## ⏳ 待做（Phase 0 full gate — 部分留 v2）

- 目標側（粵→書面）formal follow-rate：需一條真係講馬名嘅粵語片（floor 已 0，user 接受留後）。
- Suffix-leak = 0 全 clip 確認（demo 剝 suffix logic 已驗 0；整合 9 隻名無 suffix 殘留）。
- Quality regression（over-cap/empty/meaning-drift）vs no-glossary baseline。
- 多表（broadcast + racing 同時）first-wins + 各自路由的 end-to-end。
- 1350 vs 19 scale robustness（follow-rate 跌 ≤5pp）。

## 已 commit 證據

`diag_glossary_v2.py`（demo + guard）；clones `wfglossary001`（無防守，3 false-inj）/`wfglossary002`（有防守，0）喺 registry 供校對頁人手檢測。

**判定（2026-06-05）：源側 Phase-0 gate ✅ 綠 — false-injection（兩 guard → 0）+ follow-rate（gold-confirmed 100%）。User 批准開始 Phase 1（branch `feat/glossary-v2`）。目標側 follow-rate 留 Phase 4 integration 補（floor 已 0）。**

## ✅ Final 對抗式 code review（2026-06-05，7 維度 × adversarial verify）

Workflow（7 reviewer → 逐 finding 由 skeptic 反駁/確認）：**10 findings、10 全部 confirmed、0 refuted**（1 HIGH / 3 MEDIUM / 6 LOW）。三大不可動 invariant（immutability / glossaries=None backward-compat / lock discipline）全部 verifier 確認 intact。

**已修（commit `eeaca3c`）：**
- **HIGH — `cmn`（普通話）來源 content-language 分歧**：dispatch 傳原始 `source_language`（`cmn`），但中文 glossary `source_lang` 只可 `zh`，`route_for_output` exact-equality `'zh'!='cmn'` → glossary 靜默唔套用；reapply 用 `content_asr_lang`（→`zh`）就套 → 非 idempotent。修：dispatch 全 5 site 改用 `content_asr_lang(source_language)`（同 ASR base + reapply 一致）。`derive_mode(cmn,o)==derive_mode(zh,o)` 全輸出相同；yue/en/ja 係 identity → 主力驗證流程 byte-identical。**收窄結論**：真 bug 只係 `cmn→[zh-family 輸出]`（yue/zh/cmn，e.g.「普通話→口語廣東話」呢個官方支援流程）；`cmn→en/ja` 仍正確回 `None`（zh→zh glossary 本質上唔套用到英/日輸出，要 zh→en glossary 先得）—— 原 finding 略 over-scope。
- **MEDIUM #2**（同根因：reapply MT prompt source label `cmn`→bare `zh`）：補 `crosslang_mt._SRC_NAME['zh']='中文'` → label 唔再退化，dispatch/reapply 一致。
- **MEDIUM #3**（glossary selector 用 DOM 順序非點擊順序）：label 改「清單上方者優先」，貼合 `selectedOptions` 嘅 DOM 順序 + first-wins。
- **MEDIUM #4**（`filter_candidates` 85 行 dead code）：刪除（`glossary_stage` 用 `_filter_source_side`/`_filter_target_side`）+ 7 條專屬 test（guard 覆蓋由 `glossary_stage` 整合 test 保留）。

**Known-minor（6 LOW，已記、留 v2）：**
- #5 target-side guard 用 length-only（≤2 char skip + substring）而非 spec §C/§I5 提嘅中文 boundary-class pattern（doc-only；floor 已驗 0）。
- #6 `route_for_output`/`glossary_stage` 簽名加 `derive_mode`/`src_texts` 超 spec §F.4（internally consistent；只需 update spec doc）。
- #7 `build_output_translations` + 二次合併永遠寫 `glossary_changes` key（no-glossary 時 = `[]`，inert；downstream 全 null-safe；row-level always-present 係刻意設計）。
- #8 `glossary-reapply` Phase 3 鎖外覆寫 translations，理論上同 in-flight `asr_output`（加第二語言）job 有 TOCTOU（user-initiated、窄窗；reapply 由 base 全重 derive 故大致 self-consistent；可日後加 409 guard）。
- #9 `_load_glossaries` 回 `[]` vs reapply 正規化做 `None`（downstream 全 truthiness gate → 行為相同；latent inconsistency）。
- #10 個別 function >50 行（`glossary_stage`/`llm_review`/`build_merged_index`，多數係 docstring/comment 撐大；純風格）。

**整體判定**：實作 sound，唯一真 correctness bug（cmn）已修並驗證；其餘 MEDIUM 兩個（label/dead-code）已收，6 LOW 全 doc/style/edge 無 correctness 影響，記低留 v2。可 merge。
