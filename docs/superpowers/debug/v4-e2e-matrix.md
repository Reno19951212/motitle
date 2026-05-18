# v4.0 Debug — Manual E2E Matrix

每個 section 開頭列 prerequisite。環境唔具備就 mark `[N/A — missing <X>]` 入 Track B tracker，唔當失敗。

## Section 1: 真實 ASR
**Prerequisite:** M-series Mac + mlx-whisper medium model (~3GB downloaded)

- [ ] mlx-whisper medium 跑廣東話樣本
- [ ] mlx-whisper medium 跑英文樣本
- [ ] mlx-whisper medium 跑中英混合樣本
- [ ] 確認 cn_convert s2hk flag 真正 trigger
- [ ] 確認 merge_short_segments 唔產 1-word fragment
- [ ] 確認 initial_prompt bias decoder

## Section 2: 真實 MT — Ollama
**Prerequisite:** Local Ollama + qwen3.5-35b-a3b (~22GB) + 32GB+ RAM

- [ ] batch_size=1 single-segment mode
- [ ] batch_size=10 batched mode
- [ ] parallel_batches=4
- [ ] prompt_overrides 真正 inject 入 LLM payload
- [ ] translation_passes=2 enrich pass trigger

## Section 3: 真實 MT — OpenRouter
**Prerequisite:** OPENROUTER_API_KEY env + paid credit

- [ ] claude-sonnet-4-5
- [ ] gpt-4o-mini
- [ ] custom model id 自訂 input

## Section 4: 真實 FFmpeg render
**Prerequisite:** FFmpeg installed + 30s test MP4 + 5GB free disk

- [ ] MP4 CRF mode + ffprobe metadata check
- [ ] MP4 CBR mode + ffprobe check
- [ ] MP4 2-pass mode + ffprobe check
- [ ] MXF ProRes profile 0 (Proxy)
- [ ] MXF ProRes profile 1 (LT)
- [ ] MXF ProRes profile 2 (Standard)
- [ ] MXF ProRes profile 3 (HQ)
- [ ] MXF ProRes profile 4 (4444)
- [ ] MXF ProRes profile 5 (4444 XQ)
- [ ] XDCAM HD 422 @ 10 Mbps
- [ ] XDCAM HD 422 @ 50 Mbps
- [ ] XDCAM HD 422 @ 100 Mbps

## Section 5: WebSocket reliability
**Prerequisite:** Chromium DevTools available

- [ ] Pipeline 中段 network throttle → progress event 保留
- [ ] Kill backend server 中途 → frontend 顯示 disconnected
- [ ] 刷新 page 中途 → 重連後 state restore
- [ ] WebSocket reconnect dedupe（spec §8 hypothesis）

## Section 6: Bundle code-split runtime
**Prerequisite:** npm run build + serve dist available

- [ ] First paint 只 load entry + vendor-react + Login chunk
- [ ] Navigate /pipelines → vendor-dnd lazy load
- [ ] Slow 3G throttle → PageLoader fallback 顯示 OK

## Section 7: Structured logging
**Prerequisite:** Backend runnable + full pipeline E2E

- [ ] LOG_JSON=1 LOG_LEVEL=DEBUG → JSON 輸出
- [ ] X-Request-ID 由 inbound HTTP → log line → 子 thread 都貫穿
- [ ] ApiError exception → JSON 422/4XX 而非 HTML 500
