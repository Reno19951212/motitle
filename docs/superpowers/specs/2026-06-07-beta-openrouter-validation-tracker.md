# Beta OpenRouter Validation Tracker — 2026-06-07

Production stack 對齊：ASR = OpenRouter `openai/whisper-large-v3` vs 本地 mlx-whisper large-v3。
Script: `backend/scripts/validate_openrouter_whisper.py`（ffmpeg → 16k mono wav → base64 → `/api/v1/audio/transcriptions`）。
測試素材：`馬會騎師訪問（英文語音）.mp4` 頭 90 秒（英文 broadcast 語音，racing 域，16k mono wav 2.88MB）。

## V1 — OpenRouter whisper 回應有冇 segment timestamp（ASR 硬 gate）
- 狀態：✅ 已跑（2026-06-07）
- **結論：❌ Rejected** —— OpenRouter `/api/v1/audio/transcriptions` **唔會返 segment timestamp**。
- 實測 matrix（同一段 90s wav）：
  | provider | params | HTTP | 回應 keys | segment? |
  |---|---|---|---|---|
  | default route | verbose_json + timestamp_granularities=[segment,word] | 200 | `['text','usage']` | ❌ |
  | groq (pinned) | verbose_json + timestamp_granularities=[segment] | 200 | `['text','usage']` | ❌ |
  | groq (pinned) | verbose_json only / json | 400 | — | — |
  | together (pinned) | verbose_json (±granularities) | 400 | — | — |
  | default route | verbose_json only（無 granularities） | 400 | — | — |
  | default route | base payload（無 response_format） | 400 | — | — |
- Provider 池：`GET /api/v1/models/openai/whisper-large-v3/endpoints` → 得 **Together** + **Groq** 兩個。即使 Groq 原生支援 verbose_json segment timestamp，經 OpenRouter 抽象層之後回應仍然被正規化成淨係 `{text, usage}`。
- 凡係攞到 200 嘅組合，回應都**只有** `text` + `usage`，冇 `segments` 亦冇 `words`。

## V2 — word-level timestamp
- 狀態：✅ 已跑
- **結論：❌ Rejected** —— 同 V1，所有 200 回應都冇 `words`。

## V3 — 轉錄質素 + latency
- 狀態：✅ 已跑（單跑 OpenRouter；未做本地逐句對比，因 V1 已否決 ASR 路徑）
- latency：~10.2s（90s 音訊，Probe A 200）
- 文字質素：乾淨、可讀（"What is your favorite horse? Golden Sixty is a special horse to me..."）—— **text-only 質素冇問題**，純粹係攞唔到 timestamp。
- 成本：$0.0015/分鐘。

## Gate 判定 — ❌ 停 ASR 半邊
- V1/V2 = ❌（OpenRouter 攞唔到 timestamp）→ **ASR-on-OpenRouter 唔可行**（output_lang 一定要 per-segment `{start,end}` 砌 cue）。
- **執行 design §7 fallback**：Task 6/7（OpenRouterWhisperEngine + ASR override）**取消**；Beta 測試模式**只切 LLM**（Qwen3.5 → OpenRouter，Task 5 已完成），**ASR 永遠留本地 mlx-whisper large-v3**。
- 連帶要改：前端 Beta 分頁文案（移除「語音轉文字會上雲」）、admin GET 回應移除/改 `asr_model`、Task 8 文檔反映 LLM-only Beta。
- 已知 evidence（將來如要 retry ASR-on-OpenRouter 必須 cite）：OpenRouter `/audio/transcriptions` 抽象層**唔會 surface** provider 嘅 timestamp 欄位，即使底層 provider（Groq）原生支援。要 cloud ASR + timestamp 必須**繞過 OpenRouter**，直接打 provider（如 Groq 原生 API / OpenAI Whisper `/audio/transcriptions` verbose_json）。
