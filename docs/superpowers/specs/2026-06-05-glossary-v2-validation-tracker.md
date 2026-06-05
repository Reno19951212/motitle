# Validation Tracker — 詞彙表 Review v2（output_lang）

**日期：** 2026-06-05
**範圍（CLAUDE.md Validation-First）：** glossary 應用到 output_lang refine/MT prompt 行為。落 production code 前嘅 gate。
**狀態：** ⏳ **進行中** — false-injection floor（主導風險）✅ 綠；formal follow-rate（需 gold-label）待做。

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

## ⏳ 待做（Phase 0 full gate）

- `gold_applicability.json`（Winning Factor + 一條粵→書面 clip）→ formal follow-rate ≥85% 驗證。
- Suffix-leak = 0 全 clip 確認（demo 剝 suffix logic 已驗 0）。
- Quality regression（over-cap/empty/meaning-drift）vs no-glossary baseline。
- 多表（broadcast + racing 同時）first-wins + 各自路由的 end-to-end。
- 1350 vs 19 scale robustness（follow-rate 跌 ≤5pp）。

## 已 commit 證據

`diag_glossary_v2.py`（demo + guard）；clones `wfglossary001`（無防守，3 false-inj）/`wfglossary002`（有防守，0）喺 registry 供校對頁人手檢測。

**判定（2026-06-05）：源側 Phase-0 gate ✅ 綠 — false-injection（兩 guard → 0）+ follow-rate（gold-confirmed 100%）。User 批准開始 Phase 1（branch `feat/glossary-v2`）。目標側 follow-rate 留 Phase 4 integration 補（floor 已 0）。**
