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
