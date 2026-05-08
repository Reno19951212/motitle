# 8 輪 Brainstorm 終極整理 (2026-04-30)

**輸入:** 8 round × 10 angle = 80 位專家 / ~591 個 actionable idea
**輸出:** 4 個篩選 (重複 vs 唯一 / 有用 vs 冇用)

---

## 🔁 PART 1 — 重複 vs 唯一

### A. HIGHLY DUPLICATED (跨 3+ 輪自發提到) — 17 個 backbone

呢啲係多個獨立專家（喺唔同 round、唔同 lens）都諗到嘅 idea。共識最強。

| # | Idea | 出現於 Rounds | Times |
|---|---|---|---|
| 1 | **CPS reading-rate guard** (字/秒 ≤ 7) | R1×3, R2 multi-lang, R3 a11y, R5 voice | **6** |
| 2 | **Frame-accurate timestamp snap** | R1 ASR, R1 broadcast, R3 ASR, R6 PTP | **4** |
| 3 | **Profile/Glossary bundle .tar.gz export** | R1 automation, R2 plugin, R3 versioning, R4 SaaS, R5 collab | **5** |
| 4 | **Demucs voice isolation pre-ASR** | R1 ASR, R3 audio, R3 sound, R6 music | **4** |
| 5 | **Speaker diarization (pyannote)** | R1 ASR, R2 dubbing, R3 podcast, R6 lyrics, R7 medical | **5** |
| 6 | **Webhook event chain** | R1 automation, R2 plugin, R3 scripting | **3** |
| 7 | **Number/date/quote invariance check** | R1 QA, R2 AI safety, R6 fact check | **3** |
| 8 | **NER cross-check consistency** | R1 QA, R2 AI safety, R6 knowledge graph | **3** |
| 9 | **Per-language line-length config** | R1 中文 display width, R2 multi-lang | **2** |
| 10 | **Crash recovery for stuck render jobs** | R1 perf, R2 observability, R5 chaos | **3** |
| 11 | **Workflow / Recipe preset bundle** | R2 onboarding, R3 scripting, R4 TM partition | **3** |
| 12 | **CLI tool (`motitle` batch)** | R2 plugin, R3 scripting | **2** |
| 13 | **Auto-TM build from approved segments** | R4 CAT, R5 hash-chain audit, R6 typeahead | **3** |
| 14 | **PostHog opt-in telemetry** | R4 analytics, R5 metric scratchpad | **2** |
| 15 | **GitHub Actions CI** | R4 DevEx, R5 chaos fuzz, R6 property test | **3** |
| 16 | **Hash-chained audit log** | R5 forensics, R6 OPSEC | **2** |
| 17 | **Per-doc `_sv` schema field** | R4 migration, R5 forensics | **2** |

**呢 17 項 = 5 輪都 stable，consensus 最強。**

### B. MEDIUM DUPLICATION (2 輪提到) — ~30 個

| # | Idea | Rounds |
|---|---|---|
| 18 | EBU-TT-D / TTML 輸出 | R1 formats, R3 broadcast |
| 19 | TVB speaker color coding | R1 broadcast, R3 sound design |
| 20 | Find & Replace toolbar | (regression noted in 2 rounds) |
| 21 | Audio loudnorm preprocessing | R1 ASR, R3 sound |
| 22 | Confidence/`no_speech_prob` flag | R1 ASR, R5 visualization |
| 23 | Editor undo/redo (Cmd+Z) | R1 UX, R2 onboarding |
| 24 | Waveform playhead sync | R1 UX, R3 podcast |
| 25 | Auto-save draft (debounce PATCH) | R1 UX, R6 autocomplete |
| 26 | Comprehensive QC dashboard | R1 QA, R2 chaos, R6 verification |
| 27 | Pre-render blocking gate | R1 QA, R2 compliance |
| 28 | OCR onscreen text → forced glossary | R2 multi-modal, R7 niche |
| 29 | Scene-cut detection | R2 video, R3 broadcast |
| 30 | Face-location subtitle push-up | R2 video |
| 31 | i18next.js UI 抽 string | R2 i18n |
| 32 | Render proxy preview (480p) | R2 perf, R7 NLE proxy-aware |
| 33 | VAD chunk parallel ASR | R2 perf, R3 audio |
| 34 | Token cost estimator pre-translate | R2 cost |
| 35 | Tier routing (cheap → expensive on review) | R2 cost |
| 36 | OpenRouter prompt prefix caching | R2 cost |
| 37 | Esc key closes modal (already shipped!) | R5 a11y |
| 38 | aria-label sweep (already shipped!) | R5 a11y |
| 39 | Per-language CPS config | R2 multi-lang |
| 40 | Sustainability eco preset | R4 green, R7 children |
| 41 | Privacy ephemeral processing mode | R5 privacy, R7 religious |
| 42 | Activity feed / audit history | R4 SaaS, R5 forensics, R7 legal |
| 43 | Pre-warmed model cache at startup | R2 perf |
| 44 | Render worker pool (concurrent FFmpeg) | R2 perf |
| 45 | Recipe profile library (TVB-news / sports) | R2 onboarding, R3 scripting |
| 46 | Inline `?` tooltip help | R2 onboarding |
| 47 | Cmd+/ keyboard shortcut sheet | R2 onboarding |
| 48 | Empty-state coaching | R2 onboarding |

### C. UNIQUE / SINGLE-LENS — ~480 個

呢啲只有一輪、一個專家提過，多數係 vertical / niche。

代表例子（non-exhaustive）：
- 廣東話 leakage detector (R2 only)
- HK-TW vocabulary localizer (R2 only)
- Mongolian Bichig vertical script (R7 niche scripts)
- Apple Vision Pro spatial subtitle (R6 XR)
- 6G sub-1ms broadcast (R8 speculative)
- Brain-to-text decoder (R8 speculative)
- Phonetic confusion matrix exchange (R6 federated)
- HKLII citation deep link (R7 legal)
- Buddhist sutra glossary (R7 religious)
- Net-zero blockchain offset (R8 climate)
- 字幕 Olympics 競賽 (R8 league)
- Steno keyboard input (R8 alt input)

**呢類佔 ~80% 嘅 idea total，但每個重要性低咗一個 magnitude。**

---

## ⭐ PART 2 — 有用 vs 冇用

### 🟢 高 useful — 直接服務你嘅核心 user (HK 廣播 EN→TC) — 23 項

呢啲 idea **同你今日做緊嘅工作直接相關**，即時可以提升質素或減省人手。

| # | Idea | Effort | Rationale |
|---|---|---|---|
| 1 | CPS reading-rate guard | S | 你直接提過「字句太長」係 pain point |
| 2 | Cantonese leakage detector | S | 你直接提過「廣東話→TC 書面語」係 pain |
| 3 | HK/TW vocab localizer | S | 你嘅 HK 廣播 market 必需 |
| 4 | Display width 計法 (CJK=1, ASCII=0.5) | S | 28 字 threshold 配合 mixed text |
| 5 | Punctuation widow prevention (前唔可以斷) | S | 廣播 style guide 標準 |
| 6 | Min-cue duration guard (≥833ms) | S | Netflix TC 規範 |
| 7 | Inter-cue gap enforcement (≥3 frames) | S | EBU R37 規範 |
| 8 | Quoted speech bracket enforcer (`""` → `「」`) | S | TC 規範 |
| 9 | Frame-accurate snap (PlayResX) | S | 廣播 NLE 必需 |
| 10 | Number/date invariance regex | S | 防 hallucination 數字錯 |
| 11 | NER consistency cross-check | S | 同上，保證人名一致 |
| 12 | Glossary-seeded ASR `initial_prompt` | S | hot-word boost，免費提升準確度 |
| 13 | Pre-render blocking gate | S | 防止帶錯字幕出街 |
| 14 | Webhook event chain | S | 同 MAM / Slack / Avid 整合 |
| 15 | Profile/Glossary bundle .tar.gz | S | team / show 之間共享 config |
| 16 | Hash-chained audit log + `_sv` schema | S | 你之前都 mention compliance |
| 17 | Crash recovery for stuck render | S | 已經實際遇過 (你今日 backend restart) |
| 18 | Demucs voice isolation pre-ASR | M | 廣播音 routinely 有 BGM |
| 19 | Speaker diarization (pyannote) | M | 訪問 / 體育 / 新聞 全部用得到 |
| 20 | Auto-TM build from approved | M | 每 approve 都係免費 quality data |
| 21 | GitHub Actions CI (425 tests 自動跑) | S | 你今日已 425 tests 但手動 run |
| 22 | Workflow Recipe preset bundle | S | 一鍵套用「TVB News」全套設定 |
| 23 | CLI tool (`motitle batch`) | M | 過夜 batch 處理多個檔 |

**呢 23 項 = v3.8 / v3.9 sprint 嘅實際內容。** 17 個喺 backbone 入面，再加 6 個高度相關 S/M effort idea。

### 🟡 條件性 useful — 等 product 成熟或 user base 擴展先做 — ~30 項

呢啲將來會有用，但宜家做太早：

- **Multi-tenant SaaS / RBAC** — 等你開始有第二個 team 用先做
- **PostHog telemetry** — 收 user data 前要先有用戶
- **Multi-language expansion (JA/KO/VI)** — 等 EN→TC 穩陣先擴
- **Edge / on-prem package** — 等有 enterprise 客戶先做
- **Cross-platform native (PyInstaller / Tauri)** — 等 non-tech 用戶要求先做
- **Cost / Token dashboard** — 等用 OpenRouter 多咗先做
- **A/B testing framework** — 等想驗證新 prompt 先做
- **Onboarding tour (Shepherd.js)** — 等有第 2 個用戶先做
- **Plugin / extension architecture** — 等有第三方想 contribute 先做
- **Translation Memory (TMX import/export)** — 等同 Trados 用戶整合先做
- **Real-time collab (Yjs CRDT)** — 等多人同時校對先做
- **Live streaming / 5-sec lookahead** — 等真係要做 live 先做
- **Render proxy 480p preview** — 用得多 4K MXF 先值得
- **Sustainability eco preset** — 等 ESG 報告需要先做
- **Documentation site / FUNDING.yml** — open-source 公開先做
- **Sentry crash reporter** — 等 user base 大先值得
- **Mobile / PWA / iPad UX** — 等真係用 iPad 先做

### 🔴 低 useful — 速度遞減或唔配 broadcast use case — ~20 項

呢啲 idea 列出咗但係執行性低 / 跨太遠 / 唔合用：

| # | Idea | 點解唔做 |
|---|---|---|
| 1 | **Brain-to-text decoder** (R8) | 10 年後嘅 research，唔係今日工程問題 |
| 2 | **Photonic chip ASR** (R8) | 5-7 年後 hardware，今日無得買 |
| 3 | **Smart contact lens captions** (R8) | 5+ 年後消費品，broadcast 唔關事 |
| 4 | **6G sub-1ms latency** (R8) | 7 年後標準，5G 仲未普及 |
| 5 | **Toucan blockchain offset** (R8) | 你客戶冇 blockchain ESG 要求 |
| 6 | **AGI co-editor full autonomous** (R8) | speculative，無法 deliverable |
| 7 | **Mongolian Bichig vertical** (R7) | 你冇 Mongolian 客戶 |
| 8 | **Cherokee Syllabary** (R7) | 同上 |
| 9 | **Yiddish RTL+Niqqud** (R7) | 同上 |
| 10 | **Inuktitut UCAS** (R7) | 同上 |
| 11 | **Hawaiian ʻokina** (R7) | 同上 |
| 12 | **Vai / N'Ko 西非** (R7) | 同上 |
| 13 | **Medical transcription vertical** (R7) | 唔係你 user base，要 HIPAA cert + RxNorm DB |
| 14 | **Court reporting vertical** (R7) | 同上，要法庭 cert |
| 15 | **Religious / sutra vertical** (R7) | niche，無 broadcast deadline |
| 16 | **Quantum ASR** (R8 speculative) | hardware 唔存在 |
| 17 | **Voice biometric watermark steganographic** (R8) | over-engineering vs threat model |
| 18 | **Federated learning cross-station** (R6) | 你係 single-station，無 fed learning 需要 |
| 19 | **Inter-station 字幕 Olympics 競賽** (R8) | 公關噱頭，唔影響 daily output |
| 20 | **Patent trolling / OIN membership** (R8) | 你只係單人開發，未到 IP 值錢階段 |
| 21 | **Carbon offset Stripe Climate** (R8) | 對 broadcast quality 0 影響 |
| 22 | **Smart-glasses teleprompter** (R6 XR) | 5 年後消費品 |

### ⚠️ 冷板凳 — 表面 fancy 但實際邊際效應低 — ~10 項

| # | Idea | 點解 |
|---|---|---|
| 1 | Game / esports (R7) | 唔係廣播 broadcast，係 livestream 用例 |
| 2 | DAW Pro Tools plugin (R7) | sound editor 唔係字幕用戶 |
| 3 | NLE Premiere panel (R7) | 客戶用 .srt 已 sufficient |
| 4 | Voice cloning XTTS-v2 dubbing (R3) | 字幕 vs 配音 係兩個 product |
| 5 | Knowledge graph RAG Q&A (R6) | 對廣播 daily output 0 助力 |
| 6 | Education / Anki flashcard (R3) | 唔係廣播 user persona |
| 7 | Podcast workflow (R3) | 同上，對 TV 廣播 0 影響 |
| 8 | Synthetic test data (R6) | 用真實檔測試已夠 |
| 9 | Inter-station leaderboard (R8) | political 唔可行（HK 廣播商唔會公開比較） |
| 10 | Hardware appliance Mac Mini (R8) | 你已經有 dev machine，無 deploy 需要 |

---

## 📊 PART 3 — 整理數據

| 類別 | 數量 | 佔比 |
|---|---|---|
| **總 ideas** | ~591 | 100% |
| 跨 3+ 輪 backbone | 17 | 3% |
| 跨 2 輪 medium-dup | ~30 | 5% |
| 單一輪 unique | ~480 | 81% |
| 真正核心 useful (Tier 🟢) | **23** | **4%** |
| 條件性 useful (Tier 🟡) | ~30 | 5% |
| 低 useful (Tier 🔴) | ~20 | 3% |
| 邊緣 / niche (Tier ⚪️) | ~518 | 88% |

**結論：591 個 idea 入面，真正 actionable 對你今日 broadcast pipeline 有用嘅，得 23 個。**

呢 23 個 = 8 輪 brainstorm 嘅實際淨收穫。

---

## 🎯 PART 4 — 建議下一步

### 真正應該做嘅 23 個 idea (排優先)

**Phase 1 — 立即 ship (v3.8 sprint, 1-2 週, 9 個 P0):**
1. CPS reading-rate guard
2. Frame-accurate snap
3. Number/date/quote invariance regex
4. NER cross-check
5. Per-language line-length config
6. Hash-chained audit log + `_sv` schema field
7. Profile/Glossary bundle .tar.gz
8. Webhook event chain
9. Pre-render blocking gate

**Phase 2 — 翻譯品質強化 (v3.9, 4 個):**
10. Cantonese leakage detector
11. HK/TW vocab localizer
12. Display width 計法
13. Quoted speech bracket enforcer

**Phase 3 — 廣播規範 (v3.9, 3 個):**
14. Punctuation widow prevention
15. Min-cue duration guard
16. Inter-cue gap enforcement

**Phase 4 — ASR + 自動化 (v4.0, 4 個):**
17. Glossary-seeded ASR `initial_prompt`
18. Crash recovery for stuck render
19. GitHub Actions CI
20. Workflow Recipe preset bundle

**Phase 5 — Infra (v4.1, 3 個):**
21. Demucs voice isolation
22. Speaker diarization (pyannote)
23. Auto-TM build + CLI tool

---

## 🔥 最終評語

**8 輪 brainstorm 嘅 brutal honest assessment:**

- 唔係 591 個 idea 都有用 — 真正核心得 **23 個 (4%)**
- 17 backbone 喺 R3 已經 surface，後面 5 輪都係 confirm + niche derivative
- R5/R6/R7/R8 加咗深度但無加 actionable 度
- 80 角度 / 80 個專家 / 30+ hr 計算時間 → 23 個 actionable item
- **每多 brainstorm 1 round，新增 actionable idea 從 R3 嘅 ~8 個跌到 R8 嘅 ~1 個**

呢個 consolidation 應該 supersede 1481 行嘅 roadmap doc，作為實際執行嘅單一 reference。

要不要我用 brainstorm + writing-plans skill 將 Phase 1 (9 個 P0 item) 整成 v3.8 嘅可執行 sprint plan？
