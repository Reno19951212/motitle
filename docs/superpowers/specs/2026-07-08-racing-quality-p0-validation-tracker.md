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

## 實驗 B — Regression（待）

原設計（50 cue × 2 prompt + 50 judge）本機退化下不可行。改**收窄針對性 spot-check**：改動術語鄰域 + 少量中性 cue，確認 append 術語冇整壞無關句。（進行中／視硬件狀態。）

## 實驗 C / D — 待 B 後

---

## 中期結論（待 B/C/D 補完）

- **高信心、低風險、可 ship**：track_work→晨操（決定性）、Reset 保護、單位米一致性加固、騎師 Luke→霍宏聲（純 glossary append）。呢啲全部係**append 唔改**現有已驗證規則，regression 風險本質低。
- **冗餘可考慮移除**：sprinter 規則（baseline 已識；真錯係 ASR spinner）。
- **soft nudge（closer/newcomer）**：純 append 指引，無害；本機未能乾淨量度命中率。
- **方法學收穫**：本地 35B 唔穩，未來大規模 MT 質量驗證需更穩定模型/硬件，或全部改乾淨隔離 probe + 小樣本。
