# B5 — 文獻＋工具調研（Whisper hotword / 中文音近糾錯 / 馬名數據 / 粵語同音工具）

日期：2026-06-12 ｜ 純 web research + 本地 read-only 驗證（無實驗）

## TL;DR

1. **mlx-whisper 冇 beam search**（本地驗證 v0.4.3：`NotImplementedError("Beam search decoder is not yet implemented")`）→ 文獻入面所有 trie/shallow-fusion decoder bias 方案都直接port唔到；mlx 上唯一現成 lever 係 `initial_prompt`。
2. **最有 evidence 嘅方向係 ASR 後處理**：jyutping edit-distance 候選生成 + 受限 LLM rerank（PY-GEC / PERL / PMF-CEC / 粵語 homophone-extension 全部指向呢個 architecture）。**警告**：ASR-EC benchmark 實證 zero-shot LLM 成句 rewrite 會令 CER 由 12.4% 惡化到 20-34% — LLM 只可以喺候選之間揀，唔准自由改寫。
3. **重大發現：glossary 覆蓋缺口細過報告** — 「幸運有你」其實註冊名係「幸運有**您**」(E356)、「標之星河」其實係「**錶**之星河」(J343)，**兩個都喺 glossary 入面**（你/您、標/錶 粵拼相同）。即係 jyutping-level 匹配本身已救返 3 個 reported miss 之中嘅 2 個。真正缺嘅只有退役馬（美麗傳承＝Beauty Generation，2021 退役 — glossary 1352 條就係現役馬全名單 scrape）。
4. **HKJC 冇官方 open data/API**，但 legacy .aspx 頁係 static HTML 可以 fetch（已驗證）；**每場排位表（Racecard）畀到該場 ~14 隻馬嘅中英名 → 最理想嘅 per-video hotword 名單**。退役馬可經 SCMP racing stats（已驗證雙語、static HTML）backfill。

---

## 方向 1：Whisper contextual biasing / hotword boosting

| 技術 | 成熟度 | mlx 適用 | 成本 | 預期效果 |
|---|---|---|---|---|
| `initial_prompt`（zero-shot prompt biasing） | 原生參數 | ✅（本地驗證有） | 0.5-1 日 | 提升 rare-word recall，但 [2502.11572](https://arxiv.org/html/2502.11572v1) 實證 prompt-list biasing 會**推高 unbiased WER**（整體 12.1% vs 8.9%）；上限 ~70 詞（224 tokens）。我哋每場只需 ~14 隻馬名，風險細好多。中文社群實證：prompt 同時影響繁/簡 — 必須用繁體 prompt |
| faster-whisper `hotwords` | 已 ship | ❌（我哋用 mlx）| n/a | **只係 prompt injection**（prefix 為 None 時塞入 prompt window），唔係 decoder bias — 等價 initial_prompt，無增量價值 |
| TCPGen（[WhisperBiasing](https://github.com/BriansIDP/WhisperBiasing), [2306.01942](https://arxiv.org/pdf/2306.01942), [2410.18363](https://arxiv.org/html/2410.18363v1)）| 研究代碼（MIT、不活躍）| ❌ 要訓練 | 數星期 | 域內勁（maritime WER 27.8→11.1）；LibriSpeech R-WER 8.1→7.0；但要 17k aligned samples 訓練 + PyTorch → 同我哋 inference-only Apple-Silicon stack 唔夾 |
| KWS-Whisper / CB-Whisper（[2309.09552](https://arxiv.org/abs/2309.09552)）| 研究、要 multitask 訓練 | ❌ | 數星期 | 中文 Aishell hotword subsets entity recall 顯著提升；概念啱（先聲學偵測 entity 再 prompt decoder）但要訓 KWS module |
| Trie-based zero-shot + TTS 多讀音（[2508.17796](https://arxiv.org/html/2508.17796)）| 研究、無 code | ⚠️ 被 beam search 缺失 block | 3-5+ 日（自製 LogitFilter）| B-WER −43-44%、整體 WER −18-21%（LibriSpeech、1000 distractors、零訓練）— decoder-side 最強零訓練 evidence，但靠 beam search；mlx 只有 greedy，行 greedy 逐 token 加分容易一錯到底。mlx-whisper 冇任何現成 hotword fork/issue（已搜證）；whisper.cpp 同類請求 [#1979](https://github.com/ggml-org/whisper.cpp/issues/1979) 至今未實現 |

**結論**：mlx 上低成本只有 `initial_prompt`（值得用每場馬名做 A/B）；真 decoder bias 係研究級 + 被 mlx 缺 beam search 卡死，唔建議第一波做。

## 方向 2：中文/粵語 ASR 音近後處理糾錯（⭐ 最強方向）

- **[ASR-EC benchmark (2412.03075)](https://arxiv.org/html/2412.03075v1)** — 反面 evidence：zero/few-shot LLM 成句糾錯令 CER 12.42% → 20-34%（LLM 乜句都改）。LoRA 先有用；audio+text multimodal 最好（3.2-6.1%）。只測普通話。→ **我哋嘅 LLM step 必須受限：只裁決候選/接受拒絕 span 替換，唔准 free-rewrite**（同現有 glossary_stage LLM review 哲學一致）。
- **[PY-GEC (2409.13262)](https://arxiv.org/html/2409.13262v1)** — 文字+拼音齊餵 LLM：CER 11.48→10.53、entity recall 70.2→72.9；**只需 1-best**；用「拼音 CER 對輸入」做 rerank 防幻覺 → 直接可以譯做 jyutping 版（ToJyutping 做 verifier）。
- **[Pinyin Regularization (2407.01909)](https://arxiv.org/html/2407.01909v1)** + **[PERL (2412.03230)](https://arxiv.org/html/2412.03230)** — prompt 加拼音一致有效；PERL 嘅 length predictor 概念對字幕 cue（長度要穩）有參考價值。
- **[PMF-CEC (2506.11064)](https://arxiv.org/pdf/2506.11064)** — 完全係我哋場景：post-correction 時用 phoneme 檢索 biasing list、只改偵測到嘅 error span；EN+ZH 有效；但係 trained model，唔係即插即用。
- **[Integrated semantic+phonetic post-correction (2111.08400)](https://arxiv.org/pdf/2111.08400)** — 非 LLM 經典：可疑 span → 音近候選（phonetic edit distance）→ BERT rescore。驗證咗「候選生成＋rerank」架構。
- **粵語專屬**：[Homophone extension for low-resource Cantonese (2302.00836)](https://arxiv.org/abs/2302.00836)（同音詞典注入 decode + LM rescore 改善 rare words）；[CantoASR (2511.04139)](https://arxiv.org/html/2511.04139v1)（受限 decode + 輕量粵語 validator「對同音字/地名糾正特別有效」）。
- **開源工具**：[pycorrector](https://github.com/shibing624/pycorrector)（Apache-2.0, 6k★）— ConfusionCorrector 自訂混淆集模式可以照搬（對已知固定錯誤做 deterministic 替換）；但拼音層係普通話，要自己換 jyutping。

**推薦 architecture（1-2 日 prototype）**：① glossary/roster 建 jyutping 倒排索引 → ② ASR 文字 sliding-window jyutping edit-distance 揾候選 span → ③ qwen3.5 受限裁決（只准揀候選或不改）→ ④ 輸出再用 jyutping 距離 verify。可救 錶之星河/幸運有您/星際快車 類錯誤；**救唔到 lexicon 冇嘅名**（美麗傳承）→ 要方向 3 補數據。

## 方向 3：馬名數據源（HKJC）

- **冇官方 open data / API**（data.gov.hk 冇 HKJC；私人機構）。Scrape 受 HKJC ToS 約束 — production 用前要過 legal。⚠️
- **Legacy .aspx 頁 static HTML 可 fetch（已驗證）**：英文按字母列表 `SelectHorsebyChar.aspx?ordertype=A..Z`（每字母 ~70+，格式 `NAME (rating)`，link 帶 `HorseId=HK_YYYY_BRANDNO`）；中文版列中文名；馬匹個人頁中英版各示一邊名 + brand number → join brand number 得全雙語表。現役 ~1,300-1,400 → **同 glossary 1352 條吻合：glossary 本身就係現役名單 scrape，缺口＝退役＋新命名馬**。
- **每場排位表（[Racecard.aspx](https://racing.hkjc.com/racing/information/Chinese/Racing/Racecard.aspx)）= 最佳 targeted 源**：該場 ~14 隻馬中英對照 → per-video hotword/lexicon（餵 initial_prompt + D2 候選庫），0.5 日工程。
- **退役馬 backfill**：HKJC `OtherHorse.aspx?HorseId=...` 可達但冇列表；**[SCMP racing stats](https://www.scmp.com/sport/racing/stats/horses/E356/lucky-with-you) 已驗證**：`/sport/racing/stats/horses/<BRAND>/<slug>` 顯示 "LUCKY WITH YOU (E356) 幸運有您"、含退役馬、static HTML、URL 可預測 — 較易 bulk。社群數據（[Kaggle gdaley/hkracing](https://www.kaggle.com/datasets/gdaley/hkracing)、[eprochasson/horserace_data](https://github.com/eprochasson/horserace_data) 到 2018、[j-csc scraper](https://github.com/j-csc/HK-Horse-Racing-Data-Scraper)）可作歷史補充但要核實中文名覆蓋。
- **核心發現**：reported MISSING 3 個之中 2 個其實係字形變體（你→您、標→錶，粵拼相同）**已在 glossary** — jyutping-level 匹配零新數據即救返；只有真退役馬先要 backfill（而且只係舊片先需要）。

## 方向 4：粵語同音字典/工具（ToJyutping 以外）

| 工具 | 用途 | License |
|---|---|---|
| [rime-cantonese](https://github.com/rime/rime-cantonese)（CanCLID）| `jyut6ping3.dict.yaml` 詞級 word→jyutping 大詞庫（ToJyutping 嘅底層數據）；反轉做 jyutping→words 同音索引 | CC BY 4.0（商用 OK）|
| [PyCantonese](https://pycantonese.org/) | `characters_to_jyutping()` 詞境感知（HKCanCor + rime-cantonese），多音字處理好過逐字查；兼有分詞 | MIT |
| [words.hk 粵典](https://words.hk/faiman/analysis/) | 全條目 wordlist+讀音 可下載（request_data）；補口語詞覆蓋 | 字表/讀音 public domain（辭典釋文有版權）|
| Fuzzy jyutping 規則 | ASR 級匹配前 normalize：聲調剝離、n-/l- 合流、ng-/∅ 聲母、-k/-t 韻尾混淆 — rime-cantonese fuzzy 規則有文檔，regex map 幾粒鐘搞掂 | n/a |

**結論**：工具鏈完備且 license 友好；ToJyutping（pylib 已有）+ rime-cantonese 倒排索引 + fuzzy normalize 已足夠候選生成。

## 落地排序建議

1. **D2 jyutping 候選 + 受限 LLM rerank**（evidence 最強、零訓練、1-2 日）— 單係 glossary 匹配升級到 jyutping-level 已救 2/3 reported miss
2. **D3 排位表 per-video 名單**（0.5 日；legal caveat）— 同時餵 D2 同 initial_prompt
3. **D1 initial_prompt A/B**（每場 ~14 名，遠低於 70 詞風險線；驗 unbiased WER + 繁簡 drift）
4. **D1b mlx LogitFilter 自製 bias** — 只當 D2 之後仲有殘餘錯誤先考慮（高成本高風險：冇 beam search、零先例）
- **避開**：zero-shot 成句 LLM rewrite（ASR-EC 實證會衰 8-22pt CER）；TCPGen/KWS-Whisper 訓練路線（stack 唔夾）
