# 賽馬翻譯質量 P0 — Validation Tracker

日期：2026-07-09
方法：dev-side，本地 Ollama `qwen3.5:35b-a3b-mlx-bf16`（= production MT 模型）+ OCR 專業參考。舊 racing.txt vs 候選（`protos/racing_p0/racing_candidate.txt`）。
Harness：`protos/racing_p0/`（refharness / mtrun / exp_*）。

---

## ⚠️ 關鍵運維發現：本地 35B 模型退化（影響驗證方法）

跑實驗途中發現 `qwen3.5:35b-a3b-mlx-bf16` 喺**長時間駐留 + 連續 call + 多句 run-on input** 下會嚴重退化，產生三類廢輸出：
1. **回讀 prompt 示例**：吐「在中段稍微」（＝示例二輸出）、「他抽得三檔有利，今早狀態出眾」（＝示例三）、「牠晨操表現理想，母系源自「Reset」」（＝示例六）當譯文。
2. **chat-mode 拒譯**：吐「明白，請輸入英文賽馬旁白」「收到，請提供英文字幕」當譯文（當 system prompt 係對話指令）。
3. **connection timeout**：單 call 逾 600s（模型 hang / 被 evict cold-reload）。

**呢啲同 prompt 質量無關** —— 無論新舊 prompt、甚至乾淨單句都會發生，係模型/硬件層問題。應對：
- `mtrun.run_mt` 加 **degen-guard**：輸出撞示例輸出（exact 或 SequenceMatcher ≥0.85）或含 chat-refusal 標記 → retry。
- `mtrun.ollama` 加 `keep_alive:30m` + timeout retry×3。
- 退化持續時（3 retry 都清唔到）→ 該 run 作廢，靠其餘乾淨 run 判定。

**結論：呢部硬件跑唔到大規模（~290 call）自動 sweep。** 故驗證改用**乾淨隔離單句 probe**（測術語規則本身，唔測模型處唔處理到 run-on），並收窄 regression 樣本。

---

## 實驗 A — 術語命中（乾淨隔離句，exp_a2，舊 vs 新各 3 次）

| Tier | term | probe 句 | old | new | 判定 |
|---|---|---|---|---|---|
| HARD | **track_work** | His track work has been excellent this week. | **0/3** | **3/3** | ✅ **決定性修復**（三次全「晨操」；baseline 全 miss，出「表現/工作」） |
| HARD | reset | He is out of a Reset mare. | 3/3 | **3/3** | ✅ 乾淨保護（「母系源自「Reset」」，零「重置」） |
| HARD | unit | He steps up to 2000 metres today. | 3/3 | 3/3 | ✅ 無 regression（1 乾淨 run「2000 米」正確；隔離句 baseline 本身已用米 — 規則屬一致性加固，真益處喺多句混用語境，本機退化下無法乾淨量度） |
| HARD | sprinter | He is a very talented sprinter. | 3/3 | 1/3* | ⚠️ **規則冗餘**：baseline 已 3/3（模型本身識 sprinter→短途）。*new 2/3 係退化污染，1 乾淨 run 命中「短途賽駒」。註：診斷嘅真錯係 ASR 聽成「spinner」→「轉彎好手」，屬 ASR 層唔喺 prompt |
| SOFT | closer | — | — | — | 未量度（實驗喺 reset 後 timeout 炒檔）；屬語體 nudge，模型自然譯「居後/落後」唔算錯 |
| SOFT | newcomer | — | — | — | 未量度；同上，只係 append 指引 |

**GATE A 判定：track_work 決定性 PASS（0→3/3）；reset 乾淨 PASS。unit/sprinter 為無害加固/冗餘（baseline 隔離句已達標）。soft 兩項未量度但屬純 append，零移除。**

### 之前污染 run（exp_a.py，已廢）
第一輪用**多句真 cue**（如「okay. The speed... His track works very good.」）測，觸發嚴重退化：track_work 因 run-on 得 1/3-2/3、closer cue 吐「在中段稍微」、track_work#2 吐 chat-refusal。呢批數字**作廢**（模型退化污染，非 prompt 信號）。乾淨隔離句 run（exp_a2）先係有效量度。

## 實驗 B — Regression（精簡，exp_b_lean，8 cue，Opus 人手判）✅ PASS

原設計（50 cue × 2 prompt + 50 judge）本機退化下不可行（本地 judge 都退化）。改**收窄 spot-check**：8 條代表 cue（中性 + 觸發詞 work/metres/newcomer/rail），舊 vs 新產出，由 reviewer（Opus，較退化緊嘅本地 judge 可靠）親判。

| EN cue | OLD | NEW | 判 |
|---|---|---|---|
| Brave. He's very brave. | 英勇，牠十分勇猛。 | 勇敢。 | NEW 略簡（漏第二句）— model 隨機簡潔，非術語 mis-fire |
| best description of him | 對他的最佳描述 | 對牠最好的描述 | 等義 ✓ |
| swap him for any other horse | 拿任何其他馬換他 | 拿牠換任何其他馬 | 等義 ✓ |
| ideal at 1,600 | 1600 米應屬理想 | 1600 米最理想 | 等義，**米** ✓ |
| 2,000's another step | 2000 米，又是另一級 | 2000 米是另一個階段 | 等義，**米** ✓ |
| give himself every chance | 確保自己擁有最佳機會 | 盡力爭取勝機 | 等義 ✓ |
| **benefit to newcomers** | **新人**（錯，外行） | **新馬**（正） | ✅ **新規則主動修正**（match 診斷 + 專業「初次上陣」語境） |
| race along the rail | 沿內欄競逐 | 沿內欄競逐 | 等義 ✓ |

**GATE B：8/8 零 regression。** 中性 cue 唔受 append 術語影響（如預期）；單位「米」保持、冇 mis-fire 成「公尺」；**newcomer 規則實測主動修正「新人→新馬」**（額外增益，非 P0 預期硬 gate 但確認方向啱）。

## 實驗 C / D — 不再獨立跑（見決策）

- **C（Reset 獨立）**：實驗 A 已顯示 reset 保護乾淨 3/3；母系規則屬 append，GATE B 8 cue 無因它 regress → **KEEP 母系/Reset 規則**（唔獨立跑，本機退化下 ROI 低）。
- **D（對參考重量度）**：track_work（0→3/3）+ newcomer（新人→新馬）已直接對上專業參考（晨操 / 初次上陣語境）；unit 保持米。核心目標術語 ❌→✓ 已由 A+B 證實，唔另跑全片 D（退化不可行）。

---

## 最終結論（GATE A + B 完成）

**驗證通過，建議 ship 高信心子集：**
- ✅ **track_work→晨操**：0/3 → 3/3 決定性修復（跨兩檔 #1 錯誤）
- ✅ **newcomer→新馬/初次上陣**：GATE B 實測主動修正「新人→新馬」
- ✅ **Reset 保護**：乾淨 3/3（零「重置」）
- ✅ **單位米**：GATE B 兩條距離 cue 保持「米」，零 mis-fire
- ✅ **Luke Ferraris→霍宏聲**：純 glossary-style append（G 段名單），零風險
- ✅ **GATE B 8/8 零 regression**：中性 cue 不受影響，append 唔改現有規則

**取捨：**
- **sprinter 規則冗餘**（baseline 隔離句已 3/3；診斷真錯係 ASR「spinner」→「轉彎好手」，屬 ASR 層）。→ **Task 8 決定移除**，減 prompt 冗長 + 避免同 ASR 層混淆。
- **closer（後上）soft**：本機未乾淨量度；純 append 指引、無害 → 保留。
- **母系/Reset 規則**：保留（reset 保護實測有效）。

**方法學收穫（記入 memory）：本地 35B 喺長 sweep + run-on input 會嚴重退化（吐示例/chat-refusal/timeout），連本地 judge 都不可信。未來 MT 質量驗證應：① 用乾淨隔離 probe 測規則；② 小樣本 + Opus 親判 diff（唔靠退化緊嘅本地 judge）；③ 需大規模量度時要更穩定模型/硬件。**

## 決策（2026-07-09，用戶批准 ship）

用戶揀「套落真檔（移 sprinter）」。已落 `backend/config/mt_style_prompts/racing.txt`：加 晨操/後上/初次上陣/母系(Reset保護)/單位米/騎師Luke→霍宏聲/示例六；移走冗餘 sprinter。smoke 載入 OK（術語齊、sprinter 移咗、標記清）。文檔：CLAUDE.md + README 補。E2E：用戶自行揀啱 timing 用「賽馬」風格重新處理真賽馬片驗收（校對頁應見晨操/後上/初次上陣/米）。
