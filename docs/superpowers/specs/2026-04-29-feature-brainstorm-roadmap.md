# Multitool 強化 Roadmap — 10 個角度 Brainstorm

**日期:** 2026-04-29
**方法:** Ralph loop + 10 個專家 agent 並行 brainstorm
**範圍:** Whisper-subtitle-ai broadcast pipeline 整體強化

10 位專家從不同角度出發，每人提交 6-8 個具體 idea (effort: S=≤1 day / M=≤1 week / L=multi-week)。下面係去重 + 排優先級之後嘅完整 roadmap。

---

## 🥇 Tier 1 — 高槓桿、低成本 (S effort, 高價值)

呢批係「應該做」嘅，每項 1 日內可以搞掂，但即時影響廣播品質。

| # | Title | 角度 | 解釋 |
|---|---|---|---|
| 1 | **Reading-rate (CPS) Guard** | 語言 / 廣播 / a11y | 計 `len(zh) / duration`，>7 CPS 加 `"fast"` flag。三位專家獨立提到——最缺嘅 QC 指標 |
| 2 | **Frame-Accurate Timestamp Snap** | ASR / 廣播 | Profile 加 `frame_rate`，`round(t * fps) / fps`。現時 ASR 浮點時間搞亂 NLE |
| 3 | **Cantonese Leakage Detector** | 翻譯品質 | Regex 撞 ~40 個粵語助詞 (呢個/喺度/㗎)。`"cantonese_leak"` flag |
| 4 | **HK/TW Vocabulary Localizer** | 翻譯品質 | Profile `locale: hk\|tw`。post-process 自動換 80+ 對 vocab (軟件↔軟體) |
| 5 | **Display Width 唔等於 len()** | 語言 | ASCII = 0.5 unit, CJK = 1 unit。修正 28-char threshold 計法 |
| 6 | **Punctuation Widow Prevention** | 語言 | 唔可以 break 喺 「。」「？」之前；擴展 `_snap_to_punctuation` |
| 7 | **Min-Cue Duration Guard** | 廣播 / a11y | Netflix ≥833ms / BBC ≥1.0s；過短自動 merge |
| 8 | **Inter-Cue Gap Enforcement** | 廣播 | EBU R37 / TVB ≥3 frames；過密自動 shrink end |
| 9 | **Quoted Speech Bracket Enforcer** | 翻譯品質 | EN `"..."` → ZH `「」`，自動 substitution |
| 10 | **Glossary-Seeded ASR Initial Prompt** | ASR | 將 glossary EN term 注入 `initial_prompt` (~224 tokens)，hot-word boost |
| 11 | **`no_speech_prob` Confidence Flag** | ASR | faster-whisper 已計但 discard。Surface 出嚟做 review priority |
| 12 | **High-Contrast Black-Box Preset** | a11y | ASS `BorderStyle=3` + `BackColour`，1 個 toggle |
| 13 | **Dyslexia-Friendly Font Drop-in** | a11y | OpenDyslexic / Atkinson Hyperlegible drop 入 `assets/fonts/` 即用 |
| 14 | **`prefers-reduced-motion` Respect** | a11y | CSS `@media` wrap toast / progress 動畫 |
| 15 | **Pre-warm ASR Model at Startup** | 性能 | Boot 時加載 active profile model；省 30-90s 首次 latency |
| 16 | **Render Worker Pool** | 性能 | `ProcessPoolExecutor` N 個 FFmpeg 並行 |
| 17 | **Proxy-First Render (480p QA)** | 性能 | 30s vs 5-10min；render modal 加 mode toggle |
| 18 | **Adaptive Translation Batch Size** | 性能 | First 2 batches 量 latency，AIMD 調 batch_size |
| 19 | **Watch Folder Auto-Ingest** | 自動化 | 後台 thread poll `watch/` directory |
| 20 | **Render-Complete Webhook** | 自動化 | 完成 POST 個 JSON 去 Slack / MAM endpoint |
| 21 | **Pre-Render Blocking Gate** | QA | 有 critical flag 就唔俾 render，列 issues 出嚟 |
| 22 | **Time-Overlap / Gap Detector** | QA | 撞 segment boundary，加 `"overlap"` flag |
| 23 | **Missing zh_text Detector** | QA | Pre-render scan 空白 zh 段 |
| 24 | **FFprobe Render Integrity Check** | QA | 確保 output 真係有 video stream + duration 對 |
| 25 | **Proper Noun Glossary Category Tag** | 翻譯 | 分人名 / 地名 / 機構，UI 過濾用 |
| 26 | **Auto-Save Draft (Debounced PATCH)** | UX | 800ms debounce 避免 lost edit |
| 27 | **Approval Progress Sticky Header** | UX | `47/200` + jump-to-first-unapproved |
| 28 | **Keyboard-Only Row Nav (J/K/U/Enter)** | UX | 速度提升 vs mouse click |
| 29 | **Per-Segment Inline Notes** | UX | 字段 `note` for QC reviewer |
| 30 | **"Questionable" 第三狀態** | UX | 介乎 approve / unapprove，amber 顯示 |
| 31 | **Audio loudnorm Pre-process** | ASR | `-af loudnorm=I=-16:TP=-1.5:LRA=11` 改善準確度 |

**S-tier 合共 31 個 idea。** 任揀 5-10 個即時做，可以喺 1-2 週內全部 ship 完。

---

## 🥈 Tier 2 — 中型功能 (M effort, 高價值)

每項一週左右，需設計 + 測試。

### A. 翻譯品質 (3 個)
- **Register-Aware System Prompt** — Profile 加 `register: news\|sports\|entertainment\|documentary`，唔同 prompt variant
- **Date / Number / Unit Formatter** — Regex + lookup deterministic rewrite (May 5 2024 → 2024年5月5日)
- **Idiom / Literal Translation Flag** — ~150 EN idioms 列表 + hint tooltip

### B. 語言處理 (2 個)
- **Fixed-Phrase Integrity Checker** — 200+ 4-char chéngyǔ + political NPs，唔分割
- **Disyllabic Compound Anti-Split** — jieba word-boundary 標記 break point

### C. ASR (2 個)
- **Speaker Diarization (pyannote-audio)** — `[Speaker 1]` 標註 + per-speaker register
- **Demucs / RNNoise Pre-process** — Music suppression，減少 hallucination

### D. 廣播標準 (3 個)
- **Shot-Boundary Subtitle Straddle Detection** — FFmpeg `select='gt(scene,0.4)'`，flag 跨 cut 嘅 cue
- **EBU-TT-D / TTML Sidecar Export** — XML output，HbbTV/BBC iPlayer required
- **Per-Speaker Color Coding** — TVB-style outline color，Profile 配 speaker roster

### E. 性能 / Infra (3 個)
- **VAD-Gated Audio Chunking for ASR** — silero-vad 切點，N 個 worker 並行；1hr → ~5 min
- **SQLite Registry** — 取代 JSON file，thread-safe + 大檔加速
- **Persistent Job Queue (Celery + Redis)** — 重啟唔失 job

### F. UX (3 個)
- **Undo/Redo (Cmd+Z) History** — Client stack record 每次 PATCH，inverse replay
- **Waveform Playhead Sync** — WaveSurfer.js，row click → seek + highlight
- **Compare with Original ASR Toggle** — Myers diff 顯示飄離程度

### G. QC (2 個)
- **Comprehensive QC Dashboard** — 所有 flag 集中一個 panel，click 跳 segment
- **Number / Date Parity Check** — EN 同 ZH 數字 set 比對
- **Proper-Noun Consistency Check** — Cross-segment EN→ZH 一致性

### H. 自動化 (3 個)
- **Final Cut Pro X .fcpxml Export** — Title role mapping 入 timeline
- **Avid / Premiere Marker Export** — `.srtx` / sequence marker XML
- **S3 / Wasabi Cloud Pull&Push** — `s3://` URL 輸入 / 輸出
- **Project / Show Grouping** — 一系列 episodes lock 同 profile + glossary

### I. 自動化 / lint (1 個)
- **`backend/lint_subtitles.py` CLI** — Jenkins / CI 用，exit 0/1

### J. a11y (3 個)
- **SDH Sound-Effect Annotation** — `panns-inference` 加 `[♪ music]` `[applause]`
- **Multi-Track Output Bundle** — 一鍵渲染 ZH + EN + SDH + bilingual zip
- **Plain-Language Translation Mode** — `translation_style: "plain"` for cognitive a11y

### K. 廣播 (1 個)
- **HDR-Aware Burn-in** — ffprobe 偵測 HDR10/HLG，white 自動 cap 200nit

### L. 輸出格式 (2 個)
- **STL (EBU-3264) Export** — 歐洲 broadcaster sidecar
- **IMSC 1.1 / Netflix TTML Profile** — Netflix/Disney+/Apple TV+ premium 必需

**M-tier 合共 ~22 個。** 揀 5-7 個排第二輪 sprint。

---

## 🥉 Tier 3 — 大型 / 戰略 (L effort, 多週)

值得做，但要計 budget。

| Title | 角度 | 何時做 |
|---|---|---|
| **SCC (CEA-608) Closed Caption Export** | 輸出格式 | 攻入 ATSC 1.0 北美市場時 |
| **Partial Re-Render (Changed Segments Only)** | 性能 | 用戶痛訴 re-render 慢時 |
| **Multi-User SSO + Audit Log** | 自動化 | Multi-editor team 上線時 |

---

## 推薦執行次序 — 第一個 sprint (建議)

如果立即啟動，揀 8-10 個 S-tier 做第一個 release `v3.8`：

```
v3.8 — Broadcast QC Hardening
1. Reading-rate (CPS) Guard
2. Frame-Accurate Snap
3. Cantonese Leakage Detector
4. HK/TW Vocabulary Localizer
5. Display Width Calc
6. Min-Cue / Gap Enforcement (合併做一個)
7. Quoted Speech Bracket Enforcer
8. Pre-Render Blocking Gate
9. Glossary-Seeded ASR initial_prompt
10. Comprehensive QC Dashboard (M effort 但係 keystone)
```

完成後再揀 v3.9 做翻譯品質 + UX (Register prompt, Idiom flag, Undo/Redo, Waveform sync, Auto-save draft)。

---

## 統計

- **10 位專家提交咗 ~70 個 idea** (去重後 ~58 個)
- **S effort: 31 個** (≤1 日)
- **M effort: 22 個** (≤1 週)
- **L effort: 5 個** (多週)
- **去重重疊度高嘅 area:** Reading-rate (3 位獨立提到)、HK/TW vocab (2 位)、Frame-snap (2 位)、TTML export (2 位)、Speaker color (2 位)
  - 呢啲重疊度高嘅 idea 應該優先做

---

## 角度分布

| 角度 | Idea 數 | 主要 focus |
|---|---|---|
| 中文語言處理 | 8 | CPS / 標點 / 詞組完整 / display width |
| 翻譯品質 | 8 | 粵語洩漏 / 地區詞 / register / 引號 |
| 廣播標準 | 8 | Netflix TC / EBU-TT-D / shot-boundary / TVB color |
| ASR 準確度 | 8 | hot-word / confidence / diarization / loudnorm |
| UX | 8 | undo / waveform / 鍵盤 / sticky progress |
| 性能 | 8 | Celery / VAD chunk / proxy render / SQLite |
| 輸出格式 | 8 | EBU-TT-D / SCC / STL / IMSC / HDR |
| QA | 8 | 統一 dashboard / pre-render gate / consistency |
| 自動化 | 8 | watch folder / webhook / fcpxml / S3 |
| a11y | 8 | SDH / dyslexia font / multi-track / WCAG |

---

**結論:** 系統有 30+ 個易實現 (S effort) 強化點，建議由 broadcast QC 強化呢條主線開始 (v3.8)，再向翻譯品質 / UX (v3.9) 同自動化 (v4.0) 推進。

---
---

# Round 2 — 10 個全新角度 (2026-04-29)

第一輪已覆蓋語言/翻譯/廣播/ASR/UX/性能/格式/QA/自動化/a11y。第二輪轉換角度，發掘前一輪冇撞落嘅深層機會。

## R2 角度分布

| Loop | 角度 | 主要 focus |
|---|---|---|
| R2-1 | 成本 / 效率 | Tier routing / Pass2 confidence gate / segment hash cache / prompt caching / dry-run / cost dashboard |
| R2-2 | 多語言擴展 | EN→JA/KO/VI/AR multi-target / per-language CPS + 字長 + glossary / RTL / reverse direction (ZH→EN) |
| R2-3 | AI 安全 / 防 hallucination | back-translation 驗證 / NER cross-check / number invariance regex / prompt injection 過濾 / critic LLM / consistency vote |
| R2-4 | Live / Streaming | 5-sec lookahead / batched streaming whisper / auto-glossary from RSS / press-conf template / anti-flicker / HLS WebVTT 注入 / replay-and-upgrade / latency dashboard |
| R2-5 | Docs / Onboarding | Shepherd.js tour / demo mode / inline ? tooltip / recipe profiles / wizard / Cmd+/ cheat sheet / glossary CSV templates |
| R2-6 | Observability / Reliability | structured JSON log / deep readiness / Prometheus / per-job audit trail / golden snapshot / crash recovery / perf regression CI |
| R2-7 | Compliance / Moderation | profanity bleep / 自殺報導 WHO 標準 / factual claim flag / brand blocklist / age rating / embargo timestamp / 政治敏感 dictionary |
| R2-8 | Plugin / Extension | setuptools entry point / Jinja2 prompt 模板 / drop-in QC validator / output serializer ABC / webhook chain / Sheets/Notion glossary loader / .tar.gz 設定包 |
| R2-9 | Multi-modal (video frames) | OCR 解析 chyron / lower-third 偵測閃位 / face location 字幕避面 / scene cut 分句提示 / logo verbatim 保留 / sentiment register / shot-scale 動態字號 / sensitive blur |
| R2-10 | UI i18n | i18next.js 抽 string / 自動 detect locale / TC+SC+EN seed / 時區 / Intl 數字 / IME-safe shortcut / Weblate TMS |

---

## R2 全部 idea 列表 (按 Effort + Tier)

### 🥇 R2 Tier 1 — Quick Wins (S effort)

| # | Title | 角度 |
|---|---|---|
| R2-1 | **Confidence-Gated Pass 2 Enrichment** — only enrich flagged segments，慳 30-70% bill | 成本 |
| R2-2 | **Pre-Translate Token + Cost Estimator** — tiktoken 計 + 模型價，POST 前彈 toast | 成本 |
| R2-3 | **Glossary Apply String-Substitute-First** — 安全 substitution 直接做，避咗一堆 LLM call | 成本 |
| R2-4 | **OpenRouter Prompt Prefix Caching** — `cache_control: ephemeral` header 注入，輸入 token 慳 ~90% on Claude | 成本 |
| R2-5 | **Dry-Run / Preview Mode** — 唔出 API call 但見到 prompt | 成本 |
| R2-6 | **Per-Language Sidecar SRT Bundle** — 一鍵出 zh + ja + ko + vi 嘅 zip | 多語言 |
| R2-7 | **Per-Language Reading-Speed Guard** — JA 4cps / ZH 7cps / EN 17wps, language_config 加 max_cps | 多語言 |
| R2-8 | **Per-Language Line-Length per Profile** — 唔再 hardcode 28，move into language_config | 多語言 |
| R2-9 | **Number/Date/Quote Invariance Regex** — 純 regex，零 LLM 成本，catch 23%↔32%, 2024↔2025 | AI 安全 |
| R2-10 | **Prompt Injection Sanitization** — strip "ignore previous"、`<\|im_start\|>` 等 pattern | AI 安全 |
| R2-11 | **Hallucination Pattern Library** — JSON-driven blacklist，"感謝大家收看" 等 broadcast filler | AI 安全 |
| R2-12 | **NER Diff Cross-Check** — spaCy `en_core_web_sm` 確保 PERSON/ORG/GPE 喺 ZH 有對應 | AI 安全 |
| R2-13 | **Anti-Flicker Hold Buffer** — 8 frame pending → confirmed state，廣播 QA 必需 | Live |
| R2-14 | **HLS WebVTT Sidecar 注入** — rolling .vtt + manifest，OTT 直播即 work | Live |
| R2-15 | **Latency Budget Dashboard** — P50/P95 per stage，OFCA 3s 目標 | Live |
| R2-16 | **Replay-and-Upgrade Mode** — live 完用 large-v3 重新整一次 | Live |
| R2-17 | **Inline `?` Contextual Help Tooltips** — `data-help=""`，所有 setting 點解 | Onboarding |
| R2-18 | **Recipe Profile Library** — `recipes/tvb-news.json` 等，clone 即用 | Onboarding |
| R2-19 | **Empty-State Coaching** — 0 file 時顯示 3-card "How it works" | Onboarding |
| R2-20 | **Cmd+/ Keyboard Shortcut Cheat Sheet** | Onboarding |
| R2-21 | **Glossary CSV Starter Templates** — sports/politics/tech 已 seed | Onboarding |
| R2-22 | **Structured JSON Logging** — replace print，每行帶 file_id + event + duration | 觀測 |
| R2-23 | **Deep Readiness Endpoint** — ffmpeg/Ollama/data-write 3 件事都 OK 先 ready | 觀測 |
| R2-24 | **Per-Job Audit Trail** — registry 加 history[] | 觀測 |
| R2-25 | **Crash Recovery for Stuck Render Jobs** — 5-min 以上 processing 自動 → failed | 觀測 |
| R2-26 | **Profanity Bleep Marker** — `[***]` + FFmpeg `volume=enable=between(t,T1,T2):volume=0` | 合規 |
| R2-27 | **Sensitive-Event Helpline Auto-Append** — WHO 自殺報導標準，render 尾自動加熱線 | 合規 |
| R2-28 | **Brand Mention Guardrail** — JSON blocklist + override-with-reason | 合規 |
| R2-29 | **Source Attribution Completeness Check** — 引號 → 必有 PERSON/ORG entity | 合規 |
| R2-30 | **Webhook Chain (config/webhooks.json)** — event → URL array + HMAC sign | Plugin |
| R2-31 | **User-Supplied Jinja2 Prompt Templates** — `config/prompts/*.j2` 覆蓋 default | Plugin |
| R2-32 | **Profile + Glossary Bundle .tar.gz Export/Import** — share / community | Plugin |
| R2-33 | **Scene Cut Detection → Segmentation Hint** — OpenCV histogram diff，純 NumPy | Multi-modal |
| R2-34 | **Browser Auto-Detect Locale + Picker** — `navigator.language`，header 揀 locale | i18n |
| R2-35 | **Locale-Aware Timestamp + Number Formatting** — `Intl.NumberFormat`/`Intl.DateTimeFormat` | i18n |
| R2-36 | **Server TZ → User TZ Display** — backend 出 epoch，frontend formatter | i18n |
| R2-37 | **IME-Safe Shortcut Registry** — `event.isComposing` 檢查，避免 IME composition 觸發 | i18n |

**R2 S-tier 合共 37 個**，加上 R1 31 個 = **68 個 S effort idea**。

### 🥈 R2 Tier 2 (M effort)

| # | Title |
|---|---|
| R2-M1 | **Tier Routing — Cheap → Expensive on Review** (cost ~50-80% reduction) |
| R2-M2 | **Segment-Level Translation Cache (Hash Dedup)** — re-translate 唔重複 |
| R2-M3 | **Token Usage Dashboard** — JSONL ledger + monthly per-profile breakdown |
| R2-M4 | **Multi-Target Batch Render** — 1 source → N langs in 1 click |
| R2-M5 | **Per-Language Font Asset Routing** — Noto JP/KR/Thai 自動選 |
| R2-M6 | **Reverse Direction ZH→EN** — HK content → 國際版 |
| R2-M7 | **Per-Language Glossary 對應** — schema add target_language field |
| R2-M8 | **Back-Translation Round-Trip Verification** — embedding similarity，hallucination 偵測 |
| R2-M9 | **Critic LLM Spot-Check** — 不同 model rates 已 flag 段 |
| R2-M10 | **Auto-Glossary Build from RSS Headlines** — 每週 cron + NER 採集 |
| R2-M11 | **Press-Conference Template** — 預設 speakers + topic + glossary |
| R2-M12 | **Streaming Whisper (faster-whisper batched mode)** — 重新引入 live |
| R2-M13 | **5-second Lookahead Buffer** — broadcast safety delay 用做 LLM context |
| R2-M14 | **Shepherd.js Guided Tour** — 第一次入嚟一步步教 |
| R2-M15 | **Pre-Loaded Demo Mode** — 30s 樣本 file，唔需要 upload 都見到 pipeline |
| R2-M16 | **Profile Builder Wizard** — 4-step instead of 15-field form |
| R2-M17 | **Prometheus Metrics Endpoint** — queue depth / latency histogram |
| R2-M18 | **Snapshot Translation Tests** — 防 prompt 改動引致 regression |
| R2-M19 | **ASR/Translation Latency Regression Gate** — `@pytest.mark.perf` |
| R2-M20 | **Sensitive-Event WHO Filter (Suicide/Self-harm)** — 報導標準 + 自動加熱線 |
| R2-M21 | **Factual Claim / Named-Accusation Flag** — spaCy NER + accusatory verb |
| R2-M22 | **Age-Rating Estimator (G/PG/M/I)** — lexicon 計分 → CA symbol overlay |
| R2-M23 | **Embargo Timestamp Tag** — `embargo_until` 屬於 segment + render gate |
| R2-M24 | **Setuptools Entry Points for Engines** — 第三方 pip install 即 register |
| R2-M25 | **Drop-in QC Validator Hook** — `config/validators/*.py` auto-load |
| R2-M26 | **Output Serializer ABC + Plugin Format** — IMF / TTML / 自定義 |
| R2-M27 | **Google Sheets / Notion Glossary Loader** — 唔再 maintain JSON |
| R2-M28 | **Onscreen OCR → Forced Glossary Override** — chyron 認到名 → translate 唔 mistranslate |
| R2-M29 | **Lower-Third Detector → Subtitle Repositioning** — bottom 20% YOLO，避免擋 graphic |
| R2-M30 | **Face Location → Subtitle Push-Up** — MediaPipe face detect，唔擋 close-up 嘴 |
| R2-M31 | **Visual Sentiment → Register Hint** — emotion classifier → 形 prompt 書面語 vs 口語 |
| R2-M32 | **i18next.js String Extraction** — 抽走所有硬編碼字 → JSON |
| R2-M33 | **TC+SC+EN UI Translations Day 1** — `opencc` 自動 TC→SC，EN 手譯 |

**R2 M-tier 合共 33 個**。

### 🥉 R2 Tier 3 (L effort) — 戰略級

| # | Title |
|---|---|
| R2-L1 | **Local Model Distillation from Claude outputs** — fine-tune Qwen-7B 脫離 OpenRouter |
| R2-L2 | **Bidi RTL Support (Arabic/Hebrew)** — MENA 市場 |
| R2-L3 | **Self-Consistency Voting (N=3)** — high-stakes 段 majority vote |
| R2-L4 | **Logo / Brand Detection (CLIP zero-shot)** — verbatim 保留 |
| R2-L5 | **Sensitive Region Auto-Blur** — 車牌 / 護照 / 醫療熒幕 detect + 第二 FFmpeg pass |
| R2-L6 | **Weblate Self-Hosted TMS** — community 翻譯 UI 嘅 workflow |

---

## R1 + R2 終極合併 — 推薦執行路線圖

10 個 release，每個 1-2 週，所有 broad area 都會掂到。

| Release | 主題 | 重點 idea (Tier 1 主導) |
|---|---|---|
| **v3.8** | Broadcast QC Hardening | R1: CPS / frame snap / Cantonese leak / HK-TW vocab / display width / min-cue / pre-render gate / glossary-seeded ASR + R2: NER diff / number invariance / hallucination pattern lib |
| **v3.9** | Translation Quality + UX | R1: register prompt / idiom flag / undo-redo / waveform sync / auto-save + R2: prefix caching / Pass2 confidence gate / NER cross-check |
| **v4.0** | Cost & Telemetry | R2: tier routing / cost estimator / token dashboard / segment hash cache + R2: structured logging / Prometheus / readiness |
| **v4.1** | Onboarding & Recipes | R2: Shepherd tour / demo mode / inline `?` tooltip / recipe profiles / wizard / Cmd+/ |
| **v4.2** | Output Format Expansion | R1: EBU-TT-D / IMSC / SCC / TVB speaker color + R2: per-lang sidecar bundle |
| **v4.3** | Compliance & Safety | R2: profanity bleep / WHO suicide standard / brand guard / attribution check / age rating / embargo |
| **v4.4** | Live Streaming Return | R2: streaming whisper / 5-sec lookahead / anti-flicker / HLS WebVTT / latency dashboard / replay-upgrade |
| **v4.5** | Multi-modal Visual | R2: scene cut / face location / lower-third / OCR chyron / sentiment register |
| **v4.6** | Multi-Language + i18n | R2: per-lang config / multi-target render / reverse ZH→EN + R2: i18next.js / locale picker / TC+SC+EN UI |
| **v4.7** | Plugin Ecosystem | R2: entry points / Jinja2 prompts / QC validator hook / output serializer / Sheets glossary / .tar.gz bundles |

---

## 兩輪總計

- **2 輪 × 10 角度 = 20 位專家**
- **Round 1: ~58 個 deduped ideas** (S 31 / M 22 / L 5)
- **Round 2: ~76 個 deduped ideas** (S 37 / M 33 / L 6)
- **總共 ~134 個 actionable ideas**
- **如果只做 S-tier**：68 個 quick win，平均 1 日一個 = ~3 個月可全部 ship 完

---

## 跨輪重疊嘅高優先級 (兩輪獨立提到)

呢啲 idea 兩輪都有專家自發提到，極高 confidence：

1. **CPS reading-rate guard** (R1×3 + R2 multi-language reinforces)
2. **Frame-accurate snap** (R1 ASR + R1 broadcast)
3. **Number / date invariance check** (R1 QA + R2 AI safety)
4. **NER consistency check** (R1 QA + R2 AI safety)
5. **Webhook for events** (R1 自動化 + R2 plugin)
6. **Per-language line length** (R1 中文 display width + R2 multi-language)
7. **Profile bundle / sharing** (R1 自動化 show grouping + R2 .tar.gz)
8. **Crash recovery for jobs** (R1 性能 + R2 觀測)

呢 8 個應該係 v3.8 嘅核心。

---
---

# Round 3 — 再 10 個全新角度 (2026-04-29)

R1+R2 已覆蓋 20 角度。R3 再撈 10 個未撞落嘅切入點，主要圍繞：產品延伸方向 (dubbing / podcast / 教育)、深層 infra (versioning / archive)、新型客戶端 (mobile / agent API)、垂直工作流 (music / sound mix / scripting)。

## R3 角度分布

| Loop | 角度 | 重點 focus |
|---|---|---|
| R3-1 | Mobile / Tablet UX | PWA / swipe-to-approve / iPad split / PiP / Pencil / push notif / share sheet / dark mode |
| R3-2 | Voice Cloning + Dubbing | TTS engine ABC / XTTS-v2 voice clone / lip-sync 持續時間 / prosody envelope / duck-and-replace / karaoke preview / phonetic glossary / per-show TTS preset |
| R3-3 | Audio-Only Podcast | mp3/wav/m4a 直入 / speaker diarization / chapter markers / show notes 自動產生 / waveform UI / bilingual SRT / podcast profile recipe |
| R3-4 | Versioning (Git for Subtitles) | Merkle snapshot / time-travel scrubber / tag milestones / segment-level revert / branches / unified diff / bundle export / blame view |
| R3-5 | Power-User Scripting | CLI tool / workflow presets / bulk action / conditional auto-rules / filename templates / re-run pipeline button / recipe export-import / macOS Shortcuts |
| R3-6 | AI Agent API | MCP server / OpenAI tools schema / NL-CLI / autonomous QC agent / self-improving glossary / structured 422 / agent-bundle / explain pipeline |
| R3-7 | Music + Lyrics | music region detector / lyrics-mode whisper / hallucination guard / instrumental ♪ skip / Demucs voice isolation / rhyme-aware translation / theme song fingerprint skip / LRCLIB lyrics fetch |
| R3-8 | Sound Design | EBU R128 loudnorm / RNNoise / per-segment LUFS dashboard / auto-fade / Demucs stem / click-hum removal / phase-cancel mono fold / transient preserve markers |
| R3-9 | Education / Learning | word-click dictionary / pinyin/jyutping ruby / HSK difficulty heatmap / practice mode / cloze / Anki .apkg / per-segment speed / Aha-word tracker |
| R3-10 | DR / Archive | hot/warm/cold tier / 7-year retention lock / restic + B2 dedup / project bundle .tar.gz / WORM immutable / Meilisearch metadata / monthly restore-test drill |

---

## R3 全部 idea (按 Effort)

### 🥇 R3 Tier 1 — Quick Wins (S)

| # | Title | 角度 |
|---|---|---|
| R3-1 | **Swipe-to-Approve Gesture** — touch right-swipe → approve, mirrors iOS Mail | Mobile |
| R3-2 | **iPad Split-Screen Layout** — `@media landscape min-width:768px` grid 1fr 1fr | Mobile |
| R3-3 | **Picture-in-Picture Auto on Scroll** — `requestPictureInPicture()` + IntersectionObserver | Mobile |
| R3-4 | **Apple Pencil Double-Tap Toggle Review** — `pointerType==='pen'` 偵測 | Mobile |
| R3-5 | **Push Notification on Render Complete** — `Notification.requestPermission` | Mobile |
| R3-6 | **System Dark Mode Respect** — `@media (prefers-color-scheme: dark)` | Mobile |
| R3-7 | **Lyrics-Mode Whisper Run** — sung region 用 `initial_prompt: "Song lyrics follow:"` + drop conditioning | 音樂 |
| R3-8 | **Hallucination Guard on Music Silence** — denylist 加 `no_speech_prob > 0.6` | 音樂 |
| R3-9 | **Instrumental Skip + ♪ Auto-Placeholder** — translate 唔 call LLM | 音樂 |
| R3-10 | **Lyrics Translation Special Prompt** — `translation_style: "lyrics"` | 音樂 |
| R3-11 | **EBU R128 Loudness Norm** — FFmpeg `-af loudnorm=I=-23:TP=-1:LRA=11` | 音頻 |
| R3-12 | **Speech-Triggered Auto-Fade** — word_timestamps 找 first/last → afade | 音頻 |
| R3-13 | **Stereo→Mono Phase-Aware Fold** — aphasemeter 偵測 < 0.3 → 取 L only | 音頻 |
| R3-14 | **Workflow Preset Bundle** — `{profile_id, glossary_id, render_options}` | Scripting |
| R3-15 | **Output Filename Template** — `{show}_{episode}_subtitled.mp4` | Scripting |
| R3-16 | **Re-render Button** — 唔需要 re-transcribe 即重整輸出 | Scripting |
| R3-17 | **macOS Shortcuts.app Recipe** — Finder 右掣 batch render | Scripting |
| R3-18 | **OpenAI Function-Calling Schema Export** — `GET /api/openai-tools` | Agent |
| R3-19 | **Structured 422 Errors** — `{error: {field, value, constraint, suggestion}}` | Agent |
| R3-20 | **Agent-Bundle Single Endpoint** — `GET /api/files/<id>/agent-bundle` 一啖 long-context 餵 LLM | Agent |
| R3-21 | **Explain Pipeline Endpoint** — plain-language state summary | Agent |
| R3-22 | **Native Audio File Ingest** — mp3/m4a/flac/opus 直接 upload | Podcast |
| R3-23 | **Plain Transcript / Bilingual SRT Export** — audio-only deliverable | Podcast |
| R3-24 | **Show-Notes Auto Generator** — POST 攞 summary + key quotes + 名 | Podcast |
| R3-25 | **Podcast-Specific Profile Recipe** — VAD on + condition_on_previous + glossary | Podcast |
| R3-26 | **Tag Milestones (approved-for-air)** — 命名 snapshot 嘅 hash | Versioning |
| R3-27 | **Segment-Level Revert** — 個別 segment 還原唔影響其他 | Versioning |
| R3-28 | **Unified Diff Between Snapshots** — `GET /api/files/<id>/diff?from=&to=` | Versioning |
| R3-29 | **Blame View (Last Touch Provenance)** — author + ts + action per segment | Versioning |
| R3-30 | **Pronunciation Override via Glossary `tts_phonetic`** — Jyutping/IPA SSML | Dubbing |
| R3-31 | **Karaoke Preview Per Segment** — TTS short clip play overlay | Dubbing |
| R3-32 | **Per-Show TTS Profile Preset** — voice_id + speaker_voice_map | Dubbing |
| R3-33 | **Word-Click Dictionary Popup** — CC-CEDICT / WordNet | 教育 |
| R3-34 | **Pinyin / Jyutping `<ruby>` Annotation** — pycantonese / pypinyin | 教育 |
| R3-35 | **Per-Segment Playback Speed Button** — videoElement.playbackRate | 教育 |
| R3-36 | **Aha-Word Tracker (localStorage)** — 學生 lookup 歷史 → 個人 vocab dashboard | 教育 |
| R3-37 | **7-Year Retention Lock** — HK Broadcasting Ordinance Cap. 562，DELETE 返 423 | DR |
| R3-38 | **Project Bundle Tarball per Job** — media + SRT + JSON + glossary snapshot HMAC sign | DR |

**R3 S-tier 合共 38 個**。

### 🥈 R3 Tier 2 (M)

| # | Title |
|---|---|
| R3-M1 | **PWA + Service Worker Offline Cache** — manifest + SW |
| R3-M2 | **Mobile Share-Sheet Upload Target** — `share_target` in manifest，AirDrop pipe in |
| R3-M3 | **Music Region Detector** — librosa energy + spectral flatness → speech/sung/instrumental |
| R3-M4 | **Demucs Voice Isolation Pre-ASR** — vocals stem 餵 whisper 提升 WER |
| R3-M5 | **Cantonese TTS Engine ABC + 3 Backends** — Azure / Google / Coqui XTTS |
| R3-M6 | **Duration-Aware Translation** — target_syllable_count 注入 prompt |
| R3-M7 | **Prosody / Emotion Transfer** — librosa 抽 pitch+energy → SSML prosody |
| R3-M8 | **Speaker Diarization for Podcasts** — pyannote + speaker label |
| R3-M9 | **Chapter Marker Generator** — LLM 60s window topic detect → ID3 CHAP |
| R3-M10 | **Audio-Only Proofread UI (WaveSurfer)** — replace video player |
| R3-M11 | **Merkle Snapshot Chain** — content-addressed dedup history |
| R3-M12 | **Time-Travel Scrubber UI** — timeline notch per snapshot |
| R3-M13 | **CLI Tool `motitle`** — click-based wrapper + entry_point |
| R3-M14 | **Bulk Action Toolbar (multi-select)** — checkbox + sticky bottom bar |
| R3-M15 | **Conditional Auto-Profile Rules** — `if filename matches /STUDIO_*/ → profile X` |
| R3-M16 | **MCP Server for Claude Desktop** — pipeline tools 經 MCP 直接 expose |
| R3-M17 | **Natural-Language CLI** — `motitle "subtitle keynote.mp4 to TC"` |
| R3-M18 | **Autonomous QC Agent** — poll → fix → re-render，長期 cron |
| R3-M19 | **Self-Improving Glossary Agent** — diff approved vs original → propose entries |
| R3-M20 | **RNNoise Pre-ASR Background Removal** — `noisereduce` Python |
| R3-M21 | **Per-Segment LUFS History Dashboard** — sparkline + ebur128 measure |
| R3-M22 | **Click-Hum Removal** — sox noisered + librosa spectral gate |
| R3-M23 | **Transient Preserve Markers** — silencedetect inverted → applause/laughter window |
| R3-M24 | **HSK Difficulty Heatmap Highlight** — HSK 1-6 lookup + jieba tokenize |
| R3-M25 | **Practice Mode Hide ZH + Type-and-Score** — sentence-transformer cosine grade |
| R3-M26 | **Cloze-Deletion Generator** — endpoint 接 HSK level 即出 fill-in |
| R3-M27 | **Tiered Hot/Warm/Cold Storage** — 30/90 day cron promote |
| R3-M28 | **Restic + Backblaze B2 Dedup Backup** — encrypted + content-addressed |
| R3-M29 | **WORM Immutable Archive (S3 Object Lock)** — Approved + Aired → permanent |
| R3-M30 | **Monthly Restore-Test Drill** — APScheduler 自動 restore + ffprobe verify + webhook 報失敗 |

**R3 M-tier 合共 30 個**。

### 🥉 R3 Tier 3 (L)

| # | Title |
|---|---|
| R3-L1 | **XTTS-v2 Per-Speaker Voice Cloning** — 6s reference + diarization → pyl voice clone |
| R3-L2 | **Demucs Voice + Background Stem Mix-down (dubbed render mode)** |
| R3-L3 | **Theme Song Fingerprint Skip** — chromaprint per-show signature → cache subtitle |
| R3-L4 | **LRCLIB Official Lyrics Fetch** — ISRC/title 撈現成 LRC |
| R3-L5 | **Parallel Translation Branches (Branch A vs B)** — split-pane compare + per-row merge |
| R3-L6 | **Recipe Export/Import .json with cross-ref remap** |
| R3-L7 | **Anki .apkg Auto-Flashcard Export** — genanki + per-segment audio clip via FFmpeg seek |
| R3-L8 | **Meilisearch Metadata Index for Archive Search** — 跨年搜舊 segments |

---

## 三輪 Grand Total

| Round | Ideas Total | S-effort | M-effort | L-effort |
|---|---|---|---|---|
| R1 (10 角度) | 58 | 31 | 22 | 5 |
| R2 (10 角度) | 76 | 37 | 33 | 6 |
| R3 (10 角度) | 76 | 38 | 30 | 8 |
| **Grand Total** | **~210** | **106** | **85** | **19** |

**30 位專家 / 30 個獨立切入點 / ~210 個 deduped actionable idea / ~106 個 quick win (S effort)。**

每日 ship 一個 S，4 個月可全部交付。

---

## 跨三輪重疊 — 終極高 confidence list

呢啲 idea 三輪都自發 surface (兩位以上獨立提到)，極度應該優先做：

| Idea | 出現於 | 優先級 |
|---|---|---|
| **CPS reading-rate guard** | R1×3 + R2 多語言 | P0 |
| **Frame-accurate timestamp snap** | R1 ASR + R1 廣播 | P0 |
| **Number/date/quote invariance check** | R1 QA + R2 AI 安全 | P0 |
| **NER cross-check (proper noun consistency)** | R1 QA + R2 AI 安全 | P0 |
| **Webhook event chain** | R1 自動化 + R2 plugin | P0 |
| **Per-language line-length config** | R1 中文 display width + R2 multi-lang | P0 |
| **Profile/Glossary bundle .tar.gz export** | R1 show grouping + R2 .tar.gz + R3 project bundle | P0 |
| **Crash recovery for stuck render jobs** | R1 性能 + R2 觀測 | P1 |
| **Demucs voice isolation pre-ASR** | R1 ASR + R3 音樂 + R3 音頻 | P1 |
| **Speaker diarization (pyannote)** | R1 ASR + R2 dubbing + R3 podcast | P1 |
| **Workflow / Recipe preset bundle** | R2 onboarding + R3 scripting | P1 |
| **Profile bundle export / import** | R2 plugin + R3 versioning | P1 |
| **TTS / dubbing track output** | R3 dubbing + R3 a11y | P2 |
| **CLI tool for batch ops** | R2 plugin + R3 scripting | P2 |

呢 14 個 cross-round 高 confidence idea = 必做核心 backbone。

---

## 最終建議路線圖 — v3.8 → v5.0

| Release | 主題 |
|---|---|
| **v3.8** | Broadcast QC Hardening (P0 大集合) |
| **v3.9** | Translation Quality + Editor UX |
| **v4.0** | Cost Control + Telemetry |
| **v4.1** | Onboarding (Tour / Recipe / Demo) |
| **v4.2** | Output Format Expansion (TTML / IMSC / SCC) |
| **v4.3** | Compliance + Safety |
| **v4.4** | Live Streaming Return |
| **v4.5** | Multi-modal (frames + OCR + face) |
| **v4.6** | Multi-Language + UI i18n |
| **v4.7** | Plugin Ecosystem |
| **v4.8** | Mobile / PWA |
| **v4.9** | Audio-Only / Podcast |
| **v5.0** | TTS Dubbing + Voice Cloning |
| **(Future)** | Education Mode / Versioning UI / WORM Archive / Music handling |

每 release 1-2 週 ship。整個 backlog 跑完約 6-9 個月。

---
---

# Round 4 — 又 10 個全新角度 (2026-04-29)

R1+R2+R3 已掂 30 個切入點。R4 鎖定產品成熟階段先會出現嘅關注點：科學評估、SaaS 化、發行工程、深層 ASR 訓練、可持續性、企業部署。

## R4 角度分布

| Loop | 角度 | 重點 focus |
|---|---|---|
| R4-1 | Translation Quality Benchmarking | BLEU/chrF/COMET / LLM-as-judge / 反饋 corpus / cost-per-quality / domain recommendation |
| R4-2 | Multi-Tenant SaaS | Workspace 隔離 / RBAC / approval workflow / share link / quota / API token / white-label / activity feed |
| R4-3 | Product Analytics | PostHog opt-in / funnel / time-to-render P50/P90 / heatmap / format popularity / abandonment / setting churn |
| R4-4 | Schema Migration | _sv version field / boot-time backfill / atomic .bak / dry-run / jsonschema / lazy migration / migration test fixtures |
| R4-5 | CI/CD + DevEx | GitHub Actions / pre-commit / pip-compile lockfile / Conventional Commits / git-cliff / pip-audit / cz bump / Dependabot |
| R4-6 | Translation Memory / CAT | Auto-TM / fuzzy match pre-fill / TMX import-export / concordance search / partition / glossary auto-extract / contradiction warning |
| R4-7 | ASR Fine-Tune | Whisper LoRA / 主動學習 (proofread → train) / per-show adapter / Distil-Whisper / Claude knowledge distill / code-switch model / audio aug |
| R4-8 | Sustainability / Green | Smaller-model escalation / CPU-only short clip / job batch / idle GPU sleep / Wh estimate badge / eco preset / carbon-aware scheduling |
| R4-9 | Cross-Platform Native | PyInstaller + Nuitka / file-association / system tray daemon / first-run model download / Sentry crash / hardware auto-detect / signed .dmg.msi / portable USB |
| R4-10 | Edge / On-Prem | Air-gapped install / LAN multi-op / mDNS discovery / nginx template / hardware sizing / NAS output / outbound leak guard / USB update bundle |

---

## R4 全部 idea (按 Effort)

### 🥇 R4 Tier 1 — Quick Wins (S)

| # | Title | 角度 |
|---|---|---|
| R4-1 | **Adversarial Test Set** — 30 hard EN/TC 對 + per-domain BLEU 監控 | Quality Eval |
| R4-2 | **Proofreader Correction Log → Eval Corpus** — 每個 PATCH 都係 ground truth | Quality Eval |
| R4-3 | **Daily Regression Alert via Cron** — BLEU 跌 -2 → webhook 警告 | Quality Eval |
| R4-4 | **Public Share Link (Read-Only)** — signed UUID + expiry，外人 preview | SaaS |
| R4-5 | **API Tokens (Bearer Auth)** — 程式化接入，per-workspace scoped | SaaS |
| R4-6 | **Org-Wide Activity Feed** — append-only event stream + sidebar | SaaS |
| R4-7 | **PostHog Opt-In Telemetry** — funnel + heatmap + abandonment 一個 SDK 全部 cover | Analytics |
| R4-8 | **Pipeline Funnel Drop-off Tracking** — 5 checkpoints 自動量轉化率 | Analytics |
| R4-9 | **Time-to-First-Render Histogram** — P50/P90 wall-clock | Analytics |
| R4-10 | **Render Format Popularity** — MP4 vs MXF vs XDCAM 真實使用比例 | Analytics |
| R4-11 | **Profile Setting Churn Tracker** — 邊個 field 用戶最多改 → 揀 default | Analytics |
| R4-12 | **Per-document `_sv` Schema Version Field** — 為將來 migration 做準備 | Migration |
| R4-13 | **Atomic .bak Snapshot Before Write** — registry crash safe + 一秒 rollback | Migration |
| R4-14 | **Lazy Per-Entry Migration on First Read** — 唔阻塞 boot | Migration |
| R4-15 | **Migration Test Fixtures (registry_sv0/1.json)** — regression 防護 | Migration |
| R4-16 | **GitHub Actions pytest CI** — PR 必跑全測試套 | DevEx |
| R4-17 | **Pre-commit Hook (ruff + smoke)** — 唔好 push 醜 code | DevEx |
| R4-18 | **pip-compile Lockfile** — 鎖死 transitive dep，避免 surprise 更新 | DevEx |
| R4-19 | **Conventional Commits + Commitizen** — 鋪 semver + auto-changelog 路 | DevEx |
| R4-20 | **Auto CHANGELOG via git-cliff** — 唔再手寫 v3.x 版本記錄 | DevEx |
| R4-21 | **pip-audit Vulnerability Scan in CI** — CVE 即時阻 merge | DevEx |
| R4-22 | **Dependabot Weekly Updates** — 自動開 PR 升 dep | DevEx |
| R4-23 | **Cross-File Concordance Search** — 過去點翻過呢句 EN？ | TM/CAT |
| R4-24 | **TM Partition by Show** — `tm_partition: hk_news_2026` 隔開 namespace | TM/CAT |
| R4-25 | **Contradiction Warnings** — 同一 EN 譯做唔同 ZH，render 前彈 yellow | TM/CAT |
| R4-26 | **Distil-Whisper Drop-In Base** — 6× 快、49% 細，一行 checkpoint swap | ASR |
| R4-27 | **Audio Augmentation in Training** — audiomentations noise/RIR/codec 模擬 | ASR |
| R4-28 | **CPU-Only Mode for Short Clips** — `<90s` 唔開 GPU，慳 10-20Wh spin-up | Green |
| R4-29 | **Idle GPU Sleep After 5min** — 15-30W idle draw 即時零 | Green |
| R4-30 | **Energy / CO₂ Estimate Per File** — 已記錄 wall-clock × TDP × HK grid 0.7kg/kWh | Green |
| R4-31 | **Eco Profile Preset** — 一鍵 small + vad + qwen 7b + parallel=1 | Green |
| R4-32 | **PyInstaller `--onedir` Bundle** — 單一 directory，無需 setup.sh | Native |
| R4-33 | **First-Run Whisper Model Download Wizard** — splash + tqdm 進度 | Native |
| R4-34 | **Sentry Desktop Crash Reporter** — opt-in，PII scrub | Native |
| R4-35 | **Hardware Auto-Detection at Launch** — CUDA / MLX / ROCm 自動選 | Native |
| R4-36 | **mDNS / Zeroconf LAN Discovery** — `_motitle._tcp.local.`，唔需 IP | Edge |
| R4-37 | **Nginx Reverse Proxy Template** — TLS + `client_max_body_size 4G` + WebSocket header | Edge |
| R4-38 | **Hardware Sizing Reference Card** — CPU/MLX/CUDA 對應表 + RAM/NVMe 建議 | Edge |
| R4-39 | **Studio NAS Output Mount** — `OUTPUT_DIR` env 直接寫去 NFS/SMB | Edge |
| R4-40 | **Outbound Network Leak Guard** — `MOTITLE_AIRGAP=1` disable OpenRouter | Edge |

**R4 S-tier 合共 40 個**。

### 🥈 R4 Tier 2 (M)

| # | Title |
|---|---|
| R4-M1 | **BLEU/chrF on Reference Fixture (sacrebleu)** — pytest -m eval target |
| R4-M2 | **LLM-as-Judge — Claude 評分 anonymized engines** — fluency/accuracy/register 0-5 rubric |
| R4-M3 | **Cost-Per-BLEU Metric** — 計 OpenRouter 用量 / 質量單位 |
| R4-M4 | **Per-Engine Win-Rate Dashboard `/eval/summary`** — head-to-head leaderboard |
| R4-M5 | **Workspace / Org Isolation (Slug Routes)** — `/ws/{slug}/proofread` |
| R4-M6 | **Role-Based Access (Admin/Editor/Viewer/QC)** — `@require_role` decorator |
| R4-M7 | **Approval Workflow (junior→senior→publish)** — `review_stage` enum |
| R4-M8 | **Per-Workspace Compute Quota with Hard Stops** — 402 + 80% warning |
| R4-M9 | **Tenant White-Label Branding** — host header → workspace brand_config |
| R4-M10 | **Startup Backfill Migration Pass** — `_migrate_sv0_to_sv1` 鏈式 |
| R4-M11 | **Dry-Run Migration Mode** — `--migrate-dry-run` 出 diff 唔寫 |
| R4-M12 | **jsonschema Validation at Boundaries** — Profile + RegistryEntry schema |
| R4-M13 | **Semantic Version Tagging (cz bump)** — auto-detect feat/fix/break |
| R4-M14 | **Auto-TM Build from Approved Segments** — 100% match 直接 skip LLM |
| R4-M15 | **TMX Import / Export** — SDL Trados / memoQ 互通 |
| R4-M16 | **Glossary Auto-Extract from TM** — 重複 ≥3次 + ≥80% 一致 → 提示加入 |
| R4-M17 | **Confidence-Weighted TM Aging** — `base_sim × recency × approval_weight` |
| R4-M18 | **Whisper LoRA Fine-Tune (HK Broadcast)** — 10-50hr corpus + peft |
| R4-M19 | **Active Learning Loop (proofread → retrain)** — 校對差異即訓練樣本 |
| R4-M20 | **Per-Show LoRA Adapter Switching** — 50MB swap base model unchanged |
| R4-M21 | **Smaller-Model Whisper Escalation** — tiny → large fallback by `avg_logprob` |
| R4-M22 | **Job Batching with Keep-Alive Window** — 30s drain，model 唔重複 load |
| R4-M23 | **Shorter Default Retention + Lossy Cold Archive** — `retention_days` + proxy re-encode |
| R4-M24 | **PyInstaller File-Association Registration** — Open With MoTitle |
| R4-M25 | **System Tray Daemon (pystray + auto-launch)** — Backend 持續活，唔需 cmd |
| R4-M26 | **Portable USB Stick Build** — relative path，零 registry 寫入 |
| R4-M27 | **Air-Gapped Install Bundle** — wheel cache + Ollama blob + offline setup script |
| R4-M28 | **LAN Multi-Operator Mode** — `X-Operator-Id` header + Socket.IO room |
| R4-M29 | **USB / Internal CDN Update Bundle** — diff since tag + manifest + apply script |

**R4 M-tier 合共 29 個**。

### 🥉 R4 Tier 3 (L)

| # | Title |
|---|---|
| R4-L1 | **Engine Recommendation Per Domain** — 收夠 sample 至有信心 |
| R4-L2 | **Auto-Generated Schema Changelog** — decorator registry + introspection |
| R4-L3 | **Signed macOS .dmg + Windows .msi (CI)** — Apple Developer ID + DigiCert EV cert |
| R4-L4 | **Knowledge Distillation from Claude Transcripts** — teacher/student loss |
| R4-L5 | **Code-Switch ASR Model (EN+ZH mixed)** — SEAME + 廣東話 broadcast clip |
| R4-L6 | **Carbon-Aware Job Scheduling (electricityMaps)** — defer to clean grid window |
| R4-L7 | **Fuzzy Match TM Pre-fill (sentence-transformer)** — 95%+ 直接填 |

---

## 四輪 GRAND TOTAL

| Round | 角度 | Ideas | S | M | L |
|---|---|---|---|---|---|
| R1 | 10 | 58 | 31 | 22 | 5 |
| R2 | 10 | 76 | 37 | 33 | 6 |
| R3 | 10 | 76 | 38 | 30 | 8 |
| R4 | 10 | 76 | 40 | 29 | 7 |
| **TOTAL** | **40** | **~286** | **146** | **114** | **26** |

**40 位專家 / 40 個角度 / ~286 個 actionable idea / 146 個 quick win**

每日 ship 一個 S idea = ~5 個月做完晒 quick win。

---

## 跨四輪終極 P0/P1 backbone

仍然係最高 confidence 嗰幾個 (跨 ≥2 round)：

**P0 (v3.8 必做核心):**
1. CPS reading-rate guard
2. Frame-accurate timestamp snap
3. Number/date/quote invariance check
4. NER cross-check
5. Webhook event chain
6. Per-language line-length config
7. Profile/Glossary bundle export-import (v3.8 / v4.7)

**P1 (v3.9-v4.0):**
8. Crash recovery for stuck render jobs
9. Demucs voice isolation pre-ASR (R1+R3+R3 三度提到)
10. Speaker diarization (R1+R2+R3 三度提到)
11. Workflow / Recipe preset bundle
12. CLI tool for batch ops
13. **Auto-TM build (R4 新增)** — 每次 approve 都係 free quality data
14. **PostHog telemetry (R4 新增)** — 量度先可以改進
15. **GitHub Actions CI (R4 新增)** — 425 個 test 應該自動跑

呢 15 個係未來 6 個月嘅 critical path。

---

## 一個 sprint 嘅樣 (v3.8 build-out)

如果聽日就開 v3.8 sprint，呢 10 個 S-effort idea (~10 日工作量) 直接做：

```
1. CPS reading-rate guard (R1)
2. Frame-accurate snap (R1)
3. Number/date invariance regex (R2)
4. NER diff cross-check (R2)
5. Per-language line-length config (R1+R2)
6. Per-doc _sv schema field (R4)
7. Atomic .bak snapshot before write (R4)
8. GitHub Actions pytest CI (R4)
9. Profile bundle .tar.gz export (R1+R2+R3)
10. Webhook event chain (R1+R2)
```

呢 10 個 ship 完，產品就有：質量 QC 強化 + 資料安全強化 + CI 防護 + 自動化整合 = 全部 broadcast 必需 baseline。
