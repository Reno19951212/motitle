# B2 — ASR initial_prompt biasing 實驗結果

**日期**: 2026-06-12 · **音訊**: audio.wav 108.6s（沙田銀瓶賽事評述）· **模型**: mlx-whisper large-v3, `language='yue'`, `condition_on_previous_text=False`（同 production 一致）· **量度**: A1 error catalog（high 36 項為主指標；扣除 5 項 acceptable_variant 後 fixable pool = 31；medium 4 項次級；low 6 項唔計）

## 結論一句話

**ASR 層 prompt biasing 確實救到同音錯字 — 但 mlx_whisper 喺 `condition_on_previous_text=False` 之下 initial_prompt 只入到第一個 30 秒窗口**（`prompt_reset_since` 每窗 reset，無 `carry_initial_prompt`）。一行 patch 將 prompt 每窗 re-inject（V5）即由 9/31 跳到 **22/31 高置信錯誤修復、馬名提及 39/40、零 regression**。

## 變體 × 量化結果

| 變體 | 高置信修復/31 | 第一窗(<29.4s) | 其後 | 馬名提及/40 | regression | cue 數 | 乾淨段漂移 | 耗時 |
|---|---|---|---|---|---|---|---|---|
| V0 baseline（production rerun） | 0 | 0/12 | 0/19 | 20 | — | 48 | 0 | 6s |
| V1 賽馬通用 prompt | 7 | 5/12 | 2/19* | 21 | **5** | 46 | 8 | 6s |
| V2 V1+出馬表 10 馬名（理想） | 8 | 8/12 | 0/19 | 25 | 2 | 58 | 5 | 6s |
| V3 V1+phonetic prefilter 候選（現實） | 9 | **9/12** | 0/19 | 25 | 2 | 58 | 5 | 6s |
| V4 V3 prompt 按 ~30s chunk 重注入 | 22 | 9/12 | 13/19 | 37 | 1 | 24 | 6 | 16s |
| **V5 V3 prompt + carry patch（單 pass）** | **22** | 9/12 | **13/19** | **39** | **0** | 24 | 8 | 31s |

\* V1 嘅 2 項「其後」修復係 cue 邊界漂移帶嚟嘅 decode-path 運氣，唔係 biasing（V1 同時造成 5 個馬名 regression + 大量書面語 register 漂移 — 單用通用 prompt **有害**）。

- V0 rerun 同 production segments.json byte-identical（淨係 説/說 字形 + 標點闊度差異）→ decoding deterministic，可比性成立。
- 計分規則：recovered = 正字出現**且**錯字消失（鄰 cue 滲漏算 ambiguous 唔記分）；説/說 歸一；標之星河/幸運有你 等完全同音變體按 A1 指引算 acceptable。

## 三個核心發現

### 1. 機制：prompt 只 bias 第一個 30s 窗口（已源碼+實證雙確認）

V1–V3 嘅修復 **100% 集中喺 <29.4s**（第一窗 9/12 修復，window 之後 0/19）。源碼確認：`mlx_whisper/transcribe.py` 喺 `condition_on_previous_text=False` 時每窗執行 `prompt_reset_since = len(all_tokens)`，initial_prompt 只服務第一窗。mlx_whisper 冇 openai-whisper（>=20240930）嘅 `carry_initial_prompt` 參數。

**V5 一行 patch** 還原 carry 語義（`cond_on_prev` 保持 False，唔會引入前文 conditioning 嘅幻覺循環風險）：
```python
# mlx_whisper/transcribe.py
decode_options["prompt"] = initial_prompt_tokens + all_tokens[prompt_reset_since:]
#                          ^^^^^^^^^^^^^^^^^^^^^^ 加呢段（原本只有後半）
```

### 2. Phonetic prefilter 完勝：唔使出馬表

由 V0 輸出做 fuzzy-jyutping 滑窗對 1352 條 glossary 馬名匹配（聲調容差 0.85、n/l 聲母合流／ng 脫落／m-n 韻尾 0.70、L=2 要 exact），**11 個候選命中全部 10 隻真實出賽馬 + 只有 1 個 false positive（飈誌）**。V3（prefilter）成績 ≥ V2（人手出馬表），所以「知唔知場次出馬表」唔係瓶頸 — 自動化路線成立。代價：要行兩次 ASR（V0 pass 出 prefilter 候選 → biased pass）。

### 3. 修復範圍 = glossary 覆蓋範圍；殘留錯誤全部係 prompt 以外嘅嘢

V5 修復晒所有 in-glossary 馬名錯誤（升制快車×4、精算部說×6、好有心得×5、內欄位置×2、幸運有利、有愛心得、標之星我…），仲附帶 register 改善（V0 中段普通話漂移「是/還有/那匹/真的」→ V5 出返「係/仲/嗰匹/真係…㗎」）。殘留 9 項高置信：M4/M3/M2（顯示格式）、大愛當（大外檔）、尾指（尾二）、馬威有勢→馬位有勢（半修復）、沙田銀平/銀屏×2（**沙田銀瓶係獎盃名，唔喺 glossary／prompt 入面**）、山山來遲→生生來遲（成語）。呢啲要靠 prompt 加入賽馬術語詞表（唔止馬名）或下游 LLM 修。

## 代價／風險（誠實申報）

1. **Cue 結構變粗**：V5 24 cues vs V0 48（最長 9.3s，數個 6–9s）— carry prompt 令 decoder 傾向逗號連寫唔切段。yue bound-base 路徑 `do_clause_split=False`，直接落地會出長字幕 cue，**要配 clause-split 或 cue 再切先 production-ready**。對齊 grid 喺新檔案處理係 ASR 出嘅，唔構成 break，但同舊檔 cue-level A/B 唔再可比。
2. **新增錯誤 ~2-3 個（minor）**：300多米→三百零米、響→向（×1）、片尾 garbled 區出「WKC WKC」junk。對比修復 22 項，淨收益明顯，但唔係零成本。
3. **耗時 5×**：V5 31s vs V0 6s（每窗重餵 prompt tokens）；加埋 prefilter 嘅 V0 pass 共 ~37s／108.6s 音訊，仍 ~3× realtime，可接受。
4. **單 clip 證據**：N=1（108.6s、48 段）。Validation-First 要求多 clip 重複先可定案。
5. **V5 係 runtime patch**：vendor/monkeypatch mlx_whisper 一行；升級 mlx_whisper 時要 re-check（script 內有 assert 護欄）。其他平台 backend（faster-whisper/whispercpp）嘅 prompt-carry 行為各異，要逐個驗。

## Production 建議

採納方向：**兩-pass 流程** — ① 標準 V0 transcription → ② fuzzy-jyutping prefilter 對 glossary 揀 ≤12 候選馬名 → ③ V5 carry-patch + 「通用賽馬 prompt + 候選名」re-transcribe。配套要做：cue 再切（或開 clause-split）、多 clip 驗證、prompt 加常用賽馬術語（沙田銀瓶/大外檔/尾二三四/殿後）。同 B1（譯後 phonetic 替換）比較：ASR 層修復係源頭修復，連 register 都有改善，但要兩次 ASR；兩者可以互補（ASR 層救大宗，B1 兜底）。

## 檔案

- `results/B2-asr-bias.json` — 全部量化數據 + 6 個 variant 完整 transcript + 每項錯誤逐行判定
- `protos/b2_asr_bias.py` — V0–V3 transcribe + prefilter + 初版 scorer
- `protos/b2_rescore.py` — 修正 window 滲漏嘅 v2 scorer
- `protos/b2_final.py` — V4 chunked + 最終 scorer（字形歸一/acceptable_variant/第一窗拆解/regression 偵測）
- `protos/b2_v5_carry.py` — V5 carry_initial_prompt 一行 patch 實驗
- `protos/b2_out/V{0..5}.json` — 各 variant 原始 transcript cache
