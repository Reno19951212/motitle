# glossary-apply-item prompt — Validation-First tracker

日期：2026-06-12
範圍：`backend/glossary_review.py` 嘅 `build_apply_system_prompt`/`build_apply_user_prompt`（POST /glossary-apply-item 用）
Production 對齊：經 `app._make_ollama_llm_call()` 行 **qwen3.5:35b-a3b-mlx-bf16 @ temp 0.3**（同 pipeline MT/refiner/ai-edit 同一條 call path）
Script：`/tmp/gl_apply_validation.py`（session artifact；checker 邏輯記錄喺本檔）

## 結論：✅ Validated — 12/12 PASS，prompt 無需修改

| Case | 類型 | 輸入 → 輸出 | r1 | r2 |
|---|---|---|---|---|
| T1 | target·口語·句首 | 快活谷今晚嘅賽事… → **跑馬地**今晚嘅賽事…（其餘 byte-exact） | ✅ | ✅ |
| T2 | target·口語·人名 | 練馬師約翰施… → 練馬師**蔡約翰**… | ✅ | ✅ |
| T3 | target·書面·人名 | 帕頓於第五場策騎出色… → **潘頓**於第五場策騎出色… | ✅ | ✅ |
| T4 | target·書面·句中 | …賽事於快活谷舉行。 → …賽事於**跑馬地**舉行。 | ✅ | ✅ |
| S1 | source·EN·地名 | "…racing at Wong Nai Chung tonight." → "…racing at **Happy Valley** tonight."（原文：跑馬地今晚有夜馬） | ✅ | ✅ |
| S2 | source·EN·人名 | "Purton rode…" → "**Zac** Purton rode…"（純前綴插入，最小改動） | ✅ | ✅ |

## 每 call 檢查項

1. **parse**：`parse_response` 成功攞到 text（12/12）
2. **validate_applied**：包含標準名 + 有改動 + kept-ratio ≥40%（12/12）
3. **語體保持**：書面語 case（T3/T4）輸出零口語標記字（嘅/喺/咗/嚟/係）— ai-edit tracker 嘅 register-drift pattern 喺呢個 prompt **冇出現**
4. **逐字保留**：
   - target-side：`after.replace(canonical, alias) == before`（byte-exact 還原）4 case ×2 全過
   - source-side：prefix/suffix walk 證明係**單一連續改動區**，且 removed/inserted 長度 ≤ len(canonical)+8（防成句重寫）

## 驗證過程記錄（checker 迭代，唔係 prompt 迭代）

- r0 第一輪 8/12：4 個 source-side「FAIL」全部係 **checker 誤判** — source-side 嘅 alias 係原文觸發詞（中文），唔會出現喺英文 row，`replace(canonical, alias)` 還原檢查唔適用。肉眼核對嗰 4 個輸出全部正確（Wong Nai Chung→Happy Valley、Purton→Zac Purton，其餘逐字保留）。
- r1 修正後 10/12：S2 仍「FAIL」— 因為佢係**純插入**（inserted="Zac "，唔包含完整 canonical）；再修 checker 做「改動幅度有界」檢查。
- r2 最終 12/12。**Prompt 由始至終冇改過** — 三輪輸出完全一致（temp 0.3 下行為穩定）。

## 對 spec §9.4 嘅交代

- 改啱詞 ✅（12/12）
- 其餘逐字保留 ✅（target byte-exact；source 單span有界）
- 語體唔 drift ✅（書面語 case 零口語字）
