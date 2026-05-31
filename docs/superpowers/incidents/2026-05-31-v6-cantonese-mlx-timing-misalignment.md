# V6 粵語廣播字幕嚴重錯位 — 診斷報告

**日期**：2026-05-31 ｜ **狀態**：Diagnosis only（已定位 root cause，**未修復**；修復方向受 Validation-First 管制）
**檔案**：`de603727d3f8` — `賽後兩點晚（中文語音）.mp4`
**Pipeline**：V6 Dual-ASR `4696bbaa`（`[v6] 賽馬廣播 (Cantonese)`，source_lang=zh），404 segments，862s
**用戶報告**：頭幾段（大約第 5 段之前）字幕同聲音**嚴重錯位**——顯示嘅字幕對唔上嗰個時間實際講緊嘅嘢。

---

## 1. 結論（TL;DR）

**mlx-whisper（V6 嘅「時間軸權威」/Stage 1B）喺呢條片完全失敗**：成條片每 30 秒輸出一格、文字全部 hallucinate 成 **「字幕由 Amara.org 社群提供」**（Whisper 經典 YouTube 字幕鳴謝幻覺）。pipeline 採用咗呢堆 30 秒視窗塊做字幕時間軸，再用 clause_split **按字數比例**喺每個 30 秒塊入面切細——所以**每一句字幕嘅 start/end 都係假時間（比例砌出嚟），唔係真語音時間**。

最諷刺：**Qwen3（Stage 1A）本身已經有極準嘅逐字時間軸**（「今」字 @7.88s），但 pipeline 為咗時間軸採用咗 mlx 嘅幻覺塊，將 Qwen3 嘅靚時間軸丟棄。

**量化**：字幕 #0「今晚第五場…」顯示喺 `0.0–7.5s`，但「今」字實際 **7.88s** 先講 → 字幕比聲音**早咗約 7.9 秒**。Confidence：**High**（由實際持久化 `stage_outputs` 直接證實）。

---

## 2. 症狀

- 頭 4 段（`#0–#3`）每段長 **7.5 / 7.17 / 6.84 / 8.47 秒**（之後 `#4+` 正常 2–4 秒）。
- 時間軸連續無 gap / overlap，但每段邊界都剛好落喺 30 秒倍數：`#3` end=`29.98`、`#14` end=`59.98`、`#23` end=`89.98`、`#32` end=`119.98`——**每段都困喺一個 30 秒塊入面，永遠唔跨 30 秒**。
- 字詞被切開：`#0` 尾「…都望」/`#1` 頭「住…」（「望住」被斷開）。

---

## 3. 調查方法

- 4-angle 並行唯讀 workflow（time-anchored merge / VAD+mlx+Qwen3 stages / refiner / clause_split+persist）+ synthesis。
- **關鍵**：workflow synthesis 只去到 medium confidence，並且**自我標記**其中一個 angle 講「mlx 出 30 秒塊」嘅證據未經驗證、可能 hallucinate。我跟住**親自驗證** registry 嘅 `stage_outputs`，證實該證據真實，並**推翻**了 synthesis「mlx 原生 7–8 秒塊」嘅猜測 → confidence 升到 high。

---

## 4. 逐階段證據（直接讀 `registry.json` → file entry → `stage_outputs`）

| Stage | 係咩 | 頭幾項邊界 + 文字 | 判斷 |
|---|---|---|---|
| **[0] Silero VAD** | 真實語音區間（87 段） | `7.80–10.80`、`12.30–27.20`、`27.20–41.80`…（無文字） | ✅ 正常。**第一段語音 7.80s 先開始**（0–7.8s 係前奏/靜音） |
| **[1] Qwen3 逐字** | 內容 + 逐字時間（4359 字） | 「今」`7.88–7.96`、「晚」`8.04–8.12`、「嘅」`8.12–8.20`… | ✅ **極準逐字時間軸** |
| **[2] mlx-whisper**（時間軸權威） | 全音訊 ASR（371 段） | `0.00–29.98`「字幕由 Amara.org 社群提供」、`30.00–59.98` 同上、`60–89.98` 同上… | 🚨 **完全失敗**：30 秒等長塊 + 全片 hallucination |
| **[3] time-anchored merge** | Qwen3 內容塞入 mlx 時間格（360 段） | `0.00–29.98`「今晚嘅第五場…出閘」、`30.00–59.98`… | 跟咗 mlx 嘅 30 秒塊 |
| **[4] Refiner** | 清理文字（360 段，時間不變） | `0.00–29.98`「今晚第五場…出閘時，佢」… | 仍然 30 秒塊（refiner 保留時間） |
| **最終 translations** | clause_split 後 | `#0` `0.0–7.5`、`#1` `7.5–14.66`…（每 30 秒塊切細） | 按**字數比例**切，時間係假 |

> mlx 嘅 `字幕由 Amara.org 社群提供` 喺頭 6 格全部一樣（已抽查），係成條片嘅 uniform hallucination。

---

## 5. 因果鏈（root cause）

1. **Stage 1B mlx-whisper hallucinate**：對呢條音訊（粵語急口令賽評 + 0–7.8s 前奏）完全失準，每 30 秒視窗（Whisper 原生 30s chunk）出一格、文字全部「字幕由 Amara.org 社群提供」。實際只提供咗一堆 **30 秒等長邊界**。
2. **Stage 2 time-anchored merge 盲信 mlx**（`backend/stages/v6/time_anchored_merge_stage.py`）：以 mlx 段邊界為字幕時間骨架，用 midpoint 測試將 Qwen3 字塞入。→ 繼承晒 30 秒塊。
3. **Qwen3 嘅靚逐字時間被丟棄**（只攞內容，唔攞時間）。
4. **clause_split**（refiner 之後）將每個 30 秒塊喺中文標點切細，**按字數比例**分配時間（`s = start + span*(acc/total)`）。→ 每句嘅時間 = 字數比例 × 30 秒，**唔係真語音時間**。
5. 結果：全片字幕時間系統性錯位。頭段最明顯，因為 (a) 第一個 30 秒塊由 0.0 開始但語音 7.8s 先有；(b) 開場長句、標點少 → 只切到 4 段 → 每段 7–8 秒 → 比例誤差最大。

**「望住」斷字**：merge 用 midpoint 硬切跨兩條唔同步時鐘（Qwen3 逐字 vs mlx 30 秒塊），一個詞嘅兩個字 midpoint 落喺塊邊兩側就被斬開；refiner 逐段孤立處理修唔返。

---

## 6. Primary vs Contributing

- **Primary**：Stage 1B mlx hallucination + Stage 2 盲信 mlx 做時間軸（同一 root cause 嘅生產端 vs 消費端）。
- **Contributing（放大但非源頭）**：
  - Refiner 逐段孤立（`llm_refiner.py`）——prompt template 設計咗收 neighbor/±5s context 但實作只傳裸文字，所以修唔到斷字。
  - clause_split 按字數比例切時間——喺已經錯嘅 30 秒塊上面切，無法復原真時間。

---

## 7. 修復方向（**全部未做**；受 CLAUDE.md「Validation-First」管制，要先 prototype 量化驗證先寫 plan/落代碼）

1. **【最根本】唔好用 mlx 做時間軸**：直接用 **Qwen3 逐字時間**（佢已經係內容權威兼時間極準）或 VAD 區間做 segment 時間。Prototype：對呢條片重對齊，量度首字 7.5s→7.88s、錯位消失、char distribution / over-cap / 斷字率。
2. **偵測 mlx 失敗並 fallback**：當 mlx 輸出係 30 秒等長塊 / hallucination 文字（「字幕由…提供」類）→ 自動改用 Qwen3/VAD 時間，唔好信 mlx。
3. **（次要）修 mlx 幻覺本身**：試 `condition_on_previous_text=False` / head `initial_prompt` / VAD filter，量度頭段會唔會由 7–8s 收窄。要 cite v3.8 head-hallucination 既有 evidence。
4. **（次要）refiner 真正收 neighbor context**：兌現 `zh_broadcast_hk_v6.json` 設計，修斷字。
5. **【低管制】加 per-stage dump debug toggle**：將今次靠 `stage_outputs` 定位嘅能力變成常設，將來一次 re-run 就 localize。

---

## 8. 附錄：數據引用
- 證據來源：`backend/data/<...>/registry.json` → file `de603727d3f8` → `stage_outputs["0".."4"]` + `translations[]`。
- Workflow run：`wf_8a7cd593-99f`（4 angles + synthesis）。我親自驗證 `stage_outputs` 推翻 synthesis 嘅 medium-confidence 猜測。
- 關鍵反差：Qwen3「今」@`7.88s`（真）vs 最終字幕 `#0` @`0.0–7.5s`（假）= **~7.9s lead**。
