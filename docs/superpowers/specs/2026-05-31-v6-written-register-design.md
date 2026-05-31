# V6 粵語「書面語」輸出 Pipeline — 設計 Spec

**日期**：2026-05-31 ｜ **狀態**：Approved — implement ｜ **Branch**：`fix/profile-and-v6`
**前置**：[研究 workflow `v6-cantonese-written-research`] + [Validation tracker（PASS）](2026-05-31-v6-written-register-validation-tracker.md)（殘餘口語 marker 16.63→0.13/100 字、專名保留 100%、silent no-op 0.8%、長度 median 1.0×、over-cap +3–4/120，真 Ollama qwen3.5-35b 實證）。
**Prior art**：`feat/phase-1-frontend-design` commits `ac96d75`（prompt template）/`43d614d`（refiner profile）/`42bc3d1`（pipeline）。

## 目標
新增一條**獨立、可揀**嘅 V6 粵語 pipeline「[v6] 賽馬廣播 (書面語)」，輸出**現代正式繁體書面中文**，取代現時口語化粵語輸出。**唔影響**現有口語 pipeline。**純 config + test**，零 Python 邏輯改動。

## 已鎖定設計決定（user 拍板）
1. **數字格式**：保留**阿拉伯數字**（`1650 米` 唔轉「一千六百五十」）—— 廣播可讀性。
2. **正式力度**：**現代正式書面語**（規範新聞/公文書面語，清晰專業）—— 明文禁過度文言（唔強用 惟/縱/乃/之 等文言虛詞）+ 禁累贅公文腔；**保留生動四字詞/成語**。
3. **over-cap**：**接受** clause_split（cap=24）自動再切（同口語 pipeline 一致行為）。
4. 採 **two-pass chained refiner**；reject 單-pass-on-raw / translate-second / OpenCC（理由見 tracker + 研究報告）。

## 架構 / Data flow
V6 五階段不變：Stage 0 VAD → 1A Qwen3（內容）→ 1B mlx（時間）→ Stage 2 time-anchored merge（口語文字 + timing）→ **Stage 3 refiner 鏈** → `_persist_by_lang` → clause_split → render。

`backend/pipeline_runner.py:588-646` 嘅 `refinements[target_lang]` loop **已原生支援多個 refiner 順序執行**（逐個 instantiate `RefinerStage`，`lang_segments` 喺 pass 之間 mutate）。新 pipeline 將 `refinements.zh` 設為 2 元素：
```
[ 口語 refiner f7f72bd9 (pass 1，不變),  書面語 refiner 9dbe1aa3 (pass 2，新增) ]
```
Pass 2 收到 pass 1 已清理好嘅粵語（專名/時間/詞邊界已正確），淨係做 register flip。**零 Python 改動。**

## 要新增 / 改嘅檔（全部 config + 1 test）

### 1. `backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json`（新增）
移植 `ac96d75` 嘅結構，`system_prompt` **按上述 dial 重寫成現代正式書面語**。最終 `system_prompt` 內容：

```
你係專業繁體中文新聞編輯。輸入係一句已經粵語校對好嘅廣播字幕（人名、地名、賽馬術語、數字、時間軸都已正確）。
任務：淨係將呢句由【粵語口語 register】轉換成【現代正式繁體中文書面語 register】，貼近規範新聞書面語。唔好保留口語感，亦唔好過度文言或公文化。

轉換規則：
1. 粵語特徵字 → 書面語：嘅→的、係→是、咗→了、喺→在、唔→不、冇→沒有、俾/畀→給或被(按語境)、嘢→東西/事物(按語境)、佢→他/她/它、哋→們、而家→現在、點解→為何、睇→看、嗰→那、呢→這、乜/乜嘢→什麼、邊個→哪位/哪個、幾多→多少、咁→這樣/如此、喺度→在此。
2. 句末語氣助詞（啦/㗎/㗎啩/囉/喎/呀/咩/喇/嘅）一律刪除，必要時改為規範語氣（了/吧/呢）。
3. 用規範現代書面句式（如「表示」「指出」「進行」「準備就緒」），但**嚴禁**過度文言虛詞（惟/縱/乃/之乎者也）同累贅公文腔（茲/予以/上述/該項/之事宜）。
4. **保留生動四字詞同成語**（如「傷病纏身」「大刀闊斧」「旗開得勝」），唔好拆成冗長學術詞。
5. 數字、時間保留**阿拉伯數字**原狀（如「1650 米」唔好寫成「一千六百五十米」）。
6. 必須 byte-for-byte 保留唔變：人名、地名、賽馬術語、英文詞、賽事名（袁幸堯、潘頓、沙田、HIGHLAND BLINK、寶馬香港打吡大賽 等）。
7. 長度 0.8–1.3× 原文字數。唔加外部資訊、唔加原文冇嘅句首連接詞。

輸出：純 JSON object，無 markdown fence，無其他文字。
只輸出 keep 格式：{"action": "keep", "text": "<書面語校對後文字>"}

例子 1：輸入「準備起步啦。咁出閘嘅時候，都望住喺內欄啊。」→ 輸出 {"action": "keep", "text": "準備起步。出閘時均望向內欄。"}
例子 2：輸入「飛輪八夠唔夠快？佢反應都 OK 㗎。」→ 輸出 {"action": "keep", "text": "飛輪八速度是否足夠？其反應亦屬良好。"}
例子 3（保人名/數字）：輸入「第六場係四班 1650 米嚟㗎」→ 輸出 {"action": "keep", "text": "第六場為四班 1650 米賽事。"}
```
其他欄：`id`/`name`/`version`/`lang:"zh"`/`style:"written_register_v6"`，跟 `ac96d75` + 現有 template schema（同 `zh_broadcast_hk_v6.json` 對齊）。

### 2. `backend/config/refiner_profiles/9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa.json`（新增）
移植 `43d614d`，**`user_id: 627 → null`**（match 現有 4696bbaa/f7f72bd9 嘅 `user_id:null, shared:false`）：
```json
{"id":"9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa","name":"Refiner ZH 書面語 register conversion v6",
 "lang":"zh","style":"written_register_v6","llm_profile_id":"9402593c-184d-4a4d-a160-ebdf55e678e8",
 "prompt_template_id":"refiner/zh_written_register_v6","shared":false,"user_id":null,
 "created_at":1779874657.732016,"updated_at":1779874657.732016}
```
Reuse 現有 LLM profile `9402593c`（qwen3.5:35b-a3b-mlx-bf16）—— 無新 model stack。

### 3. `backend/config/pipelines/1443afcb-198b-4821-8e64-47d02bf877f3.json`（新增）
移植 `42bc3d1`（已係 clone 自 4696bbaa 嘅 `[v6] 賽馬廣播 (書面語)`，`refinements.zh = [f7f72bd9, 9dbe1aa3]`），**`user_id: 627 → null`**。其餘（vad / asr_primary `82338761` / qwen3_asr context + `post_s2hk` / font）同口語 pipeline 一致，不變。

### 4. `backend/tests/test_v6_written_register.py`（新增）
移植 `42bc3d1` 帶嘅 test，**`user_id` assertion 由 `isinstance(..., int)` 改成接受 `None`**。Assertions：
- prompt template `zh_written_register_v6` load 到，含書面語轉換規則關鍵字（的/是/了 + 「阿拉伯數字」+「禁文言」）。
- refiner profile `9dbe1aa3` load 到，`lang=="zh"`、`prompt_template_id=="refiner/zh_written_register_v6"`、`user_id is None`。
- pipeline `1443afcb` load 到，`refinements["zh"]` 係 2 元素、順序 `[f7f72bd9, 9dbe1aa3]`、`user_id is None`。
- Regression guard：口語 pipeline `4696bbaa` 嘅 `refinements["zh"]` 仍係 1 元素（`[f7f72bd9]`），確認無被誤改。

## 錯誤處理 / 兼容
- Pass-2 LLM 失敗（refuse / drop / JSONDecodeError）→ `LLMRefiner` fallback 落 src（= pass-1 口語）：silent，唔 crash；現有 `compute_refiner_flags` 出 long/empty。整合 re-run 會量 silent no-op rate（prototype 0.8%）。
- 新 pipeline 獨立檔；口語 pipeline 零 storage migration、零行為改動。
- Managers（`PipelineManager`/`RefinerProfileManager`）boot 自動 load `*.json`；`user_id:null` → 所有 user 喺 strip preset menu 見到。

## 測試
**Config 層**（pytest，上述 test 4 項）。

**整合驗證（Validation-First mandate，必做，寫入 tracker）**：
1. 重啟 backend → `GET /api/pipelines` 確認「[v6] 賽馬廣播 (書面語)」出現 + 口語版 `4696bbaa` 不變。
2. 對真片 `de603727d3f8`（賽後兩點晚）跑新 pipeline 端到端 → 持久化 `by_lang.zh`。
3. 量度（對比口語 baseline）：殘餘口語 marker /100 字（目標 ≤2.0）、專名 byte 保留（=100%）、over-cap rate（vs 口語 1.8%）、length ratio、latency（2× refiner，confirm 喺 `R5_QWEN3_TIMEOUT_SEC=900` 內 + 4–6 min broadcast budget）。
4. 口語 pipeline `4696bbaa` 跑同片 → output byte-identical 於 pre-change baseline（零 regression）。
5. 結果寫 [validation tracker](2026-05-31-v6-written-register-validation-tracker.md) 嘅「整合驗證」段。

## 範圍外
單-pass refiner；EN pipeline；>2 refiner 鏈；register flag for proofreader（pass-2 silent no-op 偵測）；per-file 口語↔書面語 toggle；其他語言/領域書面語 pipeline。

## Implementation 次序（TDD，writing-plans 會展開）
1. 寫 config-load test（RED）。
2. 加 3 個 config 檔（prompt template + refiner profile `user_id:null` + pipeline `user_id:null`）→ test GREEN。
3. Regression：`pytest -k "v6 or pipeline or refiner"` 無新 fail。
4. 整合 re-run + 量度 + 寫 tracker；commit per step + CLAUDE.md entry。
