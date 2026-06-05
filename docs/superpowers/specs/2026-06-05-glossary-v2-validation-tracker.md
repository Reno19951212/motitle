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

## ✅ Follow-rate（demo 信號，formal 待 gold-label）

Demo（`diag_glossary_v2.py`，真 qwen3.5，Winning Factor en→zh 源側 + guard）：39 段被改，馬名 wins **全部正確 canonicalize**（火悟空/活力拍檔/榮駿大道/共享富裕/北斗福星/燈胆將軍/喜慶寶/錶之星河/翠紅），中文名 100% 由 glossary `target` 抽出（剝 `(H###)`）。LLM 只擺位 + 判斷適用性。

> ⚠️ **formal follow-rate（`correct / gold-applicable`）需 `gold_applicability.json`（人手標逐段 applicable term）** — 與 user 一齊標後補。Demo 定性顯示 follow-rate 高。

## ⏳ 待做（Phase 0 full gate）

- `gold_applicability.json`（Winning Factor + 一條粵→書面 clip）→ formal follow-rate ≥85% 驗證。
- Suffix-leak = 0 全 clip 確認（demo 剝 suffix logic 已驗 0）。
- Quality regression（over-cap/empty/meaning-drift）vs no-glossary baseline。
- 多表（broadcast + racing 同時）first-wins + 各自路由的 end-to-end。
- 1350 vs 19 scale robustness（follow-rate 跌 ≤5pp）。

## 已 commit 證據

`diag_glossary_v2.py`（demo + guard）；clones `wfglossary001`（無防守，3 false-inj）/`wfglossary002`（有防守，0）喺 registry 供校對頁人手檢測。

**判定：false-injection gate ✅ 綠（兩 guard → 0）；full Phase-0（follow-rate gold-label）pending → 完成先入 Phase 1 production code。**
