# Validation-First Tracker — V6 mlx-whisper timing hallucination fix (Directions 2 + 3)

**日期**：2026-05-31 ｜ **狀態**：Validation done — awaiting user review before plan/code
**Incident**：[2026-05-31-v6-cantonese-mlx-timing-misalignment.md](../incidents/2026-05-31-v6-cantonese-mlx-timing-misalignment.md)
**Reproducer**：file `de603727d3f8`（賽後兩點晚（中文語音）.mp4），pipeline `4696bbaa`，asr_primary profile `82338761`（mlx-whisper **large-v3**, zh, initial_prompt=「以下係香港賽馬新聞，繁體中文。」, condition_on_previous_text=**default True**）。
**Production alignment**：用 production 一致 model = mlx-whisper **large-v3** zh（CLAUDE.md 要求）。Prototype 跑喺 120s clip 加速迭代。
**Prototypes**：`backend/scripts/v6_prototype/diag_mlx_timing.py`（Direction 3）、`backend/scripts/v6_prototype/diag_mlx_detect_fallback.py`（Direction 2）。

---

## Direction 3 — 修 mlx 幻覺本身（mlx 設定）

跑 large-v3 / zh，喺 120s clip（covers 4 × 30s windows）：

| Hyp | 設定 | n_segs | median dur | 幻覺塊 | 結果 | 判定 |
|---|---|---|---|---|---|---|
| H3.1 | **cond=True**（production baseline）+ prompt | **4** | 29.98s | **4/4**（全部「字幕由 Amara.org 社群提供」） | 重現 cascade + 30s 塊 | ✅ Validated（confirm bug） |
| **H3.2** | **cond=False** + prompt | **40** | **2.24s** | 1（只剩頭 0–30s 塊） | **cascade 打斷**，body 變細段真內容 | ✅ **Validated（主修法）** |
| H3.3 | cond=False + word_timestamps=True | 45 | 1.66s | 1（頭塊縮到 13.56–29.98s） | 更細，頭塊縮短 | ✅ Validated（額外收窄頭） |
| H3.4 | cond=False, **no prompt** | 40 | 2.24s | 1 | 同 H3.2 | ✅ Validated（prompt 對 cascade 唔關鍵；**cond 先係 lever**） |

**結論 D3**：`condition_on_previous_text=False`（即 v3.8 對主 ASR 做過、但 asr_primary profile 從來冇收過嘅修法）**打斷 caption cascade**：由「4 段全 30s 幻覺」→「40 段 median 2.24s 真內容」。**但頭 30s 塊仍然幻覺**（head：0–7.8s 音樂前奏 + 首窗），所以 cond=False **修到 body（30s 之後全片），頭仍需額外處理**。

---

## Direction 2 — 偵測 mlx 失敗 + fallback 去 Qwen3/VAD 時間

純 Python 跑喺持久化 `stage_outputs`（production cond=True run）：

| Hyp | 測試 | 結果 | 判定 |
|---|---|---|---|
| H2.1 | Detector：coarse(≥20s)+ 幻覺文字塊 = 失敗 | bad stage[2]：**flag = true，5 個 coarse 幻覺塊共 150s**（頭 5 × 30s）；synthetic healthy：**false（無誤報）** | ✅ Validated（**v1 threshold 用 global fraction 誤判 false-negative；改用 head/coarse-block 簽名先啱**） |
| H2.2 | Qwen3 時間 fallback | Qwen3「今」@**7.88s**；現字幕 #0 @ 0.0–7.5s → **字幕早咗 7.88s**；block0 真 span = 7.88–29.92s（頭 7.88s 靜音被誤分配） | ✅ Validated（Qwen3 已有準時間，可重對齊） |

**結論 D2**：detector 用「coarse(≥20s) + 幻覺文字」簽名可靠 flag 失敗塊（呢條片頭 150s = 5 塊），synthetic healthy 唔誤報。flag 咗嘅 span 改用 **Qwen3 逐字時間**重對齊 → 頭塊由 0–29.98s 修正到真 7.88–29.92s。

---

## 綜合結論（empirical）

production mlx（cond=True）喺呢條片**頭 150s cascade**（5 × 30s 幻覺塊）然後先恢復——正好對應用戶報告嘅「第 5 段之前」嚴重錯位。兩個方向互補、都有量化支持：

1. **D3（cond=False）= 主修，平、影響全片 body**：4 段全幻覺 → 40 段真內容（median 2.24s）。修到 30s 之後成片。
2. **D2（detect + Qwen3 fallback）= 處理殘餘頭塊**：cond=False 之後仍剩頭 0–30s 塊；detector flag 佢 → 用 Qwen3 時間重對齊（7.88s）。

**建議方案（待 user confirm 先寫 plan/code）**：D3 + D2 一齊做 ——（a）asr_primary mlx profile / engine 預設 `condition_on_previous_text=False`；（b）time-anchored merge 之前/之中加 detector，對 coarse+幻覺 mlx 塊 fallback 去 Qwen3（或 VAD）時間。兩者都改 ASR/merge → 受 Validation-First 管制（本 tracker 即為證據）。

---

## 整合 re-run 結果（2026-05-31，full 862s，production V6，D3+D2 已落代碼）

對 reproducer `de603727d3f8` 真 re-run V6（VAD + Qwen3 per-region + mlx + merge + refiner，~480s 完成），讀新 `stage_outputs` + `translations`：

| 指標 | 修復前 | 修復後 | 判定 |
|---|---|---|---|
| 字幕 **#0 start** | 0.00s（早聲音 7.88s） | **7.80s**（對齊首 VAD 區間 / Qwen3「今」@7.88） | ✅ |
| mlx stage[2] coarse(≥20s) 塊 | 5（cascade 頭 150s） | **1**（只剩頭 0–30s） | ✅ D3 打斷 cascade |
| mlx stage[2] median dur | 30s 塊 | **2.14s**（真細段） | ✅ |
| 頭段邊界 | 30s 倍數對齊（29.98…） | **VAD 區間**（7.80–10.80 / 12.30–15.90 / …） | ✅ D2 fallback |
| detector 誤報 | — | 314 body 細段零 flag（只 flag 1 頭塊） | ✅ |

**結論**：D3（cond=False）修到 body（30s 之後全片真時間）；D2（VAD fallback）將殘餘頭塊由「0–30s 一大塊」重切成 6 段 VAD-aligned 真語音段。頭部錯位（早 7.88s）**消除**。整合 gate **PASS**。

**Spec/Plan/實作**：[spec](2026-05-31-v6-mlx-timing-fix-design.md) / [plan](../plans/2026-05-31-v6-mlx-timing-fix-plan.md)；commits `592e3eb`/`b6bb4cf`（T1 D2）、`2602ac7`（T2 D3）。
