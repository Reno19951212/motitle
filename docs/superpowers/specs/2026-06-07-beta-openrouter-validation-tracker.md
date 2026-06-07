# Beta OpenRouter Validation Tracker — 2026-06-07

Production stack 對齊：ASR = OpenRouter `openai/whisper-large-v3` vs 本地 mlx-whisper large-v3。
Script: `backend/scripts/validate_openrouter_whisper.py`（ffmpeg → 16k mono wav → base64 → `/api/v1/audio/transcriptions`）。

## V1 — OpenRouter whisper 回應有冇 segment timestamp（ASR 硬 gate）
- 狀態：⬜ 待跑
- 成功嘅 request param 形狀（Probe A verbose_json 定 Probe B base）：（待填）
- 回應 top_level_keys：（待填）
- first_segment shape（field 名 start/end/text？）：（待填）
- 結論：⬜ ✅ Validated / ❌ Rejected / ⚠️ Partial

## V2 — word-level timestamp
- 狀態：⬜ 待跑
- first_word shape：（待填）
- 結論：⬜

## V3 — 轉錄質素 + latency vs 本地 large-v3
- 狀態：⬜ 待跑
- latency_sec：（待填）
- 質素 directional 觀察 vs 本地 mlx large-v3：（待填）

## Gate 判定
- V1 ✅ → Task 6/7 可進行，將確認嘅 request param 形狀 + segment field 名帶入 `OpenRouterWhisperEngine`。
- V1 ❌（淨係 flat text）→ 停 Task 6/7，Beta 只切 LLM、ASR 留本地（design §7）。
