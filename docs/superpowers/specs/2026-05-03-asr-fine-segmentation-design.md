# ASR Fine Segmentation — Design Spec

**Date:** 2026-05-03
**Branch:** `feat/asr-fine-segmentation`
**Predecessor branch:** `feat/subtitle-source-mode` (HEAD `4e3c33a`)
**Validation tracker:** [`2026-05-03-asr-fine-segmentation-validation.md`](2026-05-03-asr-fine-segmentation-validation.md)
**Status:** Design approved by user 2026-05-03

## Goal

廣播字幕優化：將 mlx-whisper 出嚟嘅英文 ASR segments 由 baseline 平均 4-7s / 14 字 細化到 mean ~3.2s / max ~5.5s / sent_end boundary 約 40%，並架構性消除「sentence 跨 30s window mid-clause cut」（典型例子：「...what the team really needs is a」+「radical overhaul...」應為一句但被 Whisper 30s window 強行切開）。

## Non-Goals

- 修改 faster-whisper / openai-whisper / Qwen3-ASR / FLG-ASR engine 行為
- 自動 re-transcribe 既有 file（grandfather 策略）
- frontend UI 暴露超過 2 個調節欄位
- Multi-VAD library support（只用 Silero）
- LLM-based re-segmentation
- pySBD post-process（design pivot 已 drop）

## Background — Validation Evidence

11-config A/B 跑 large-v3 + Real Madrid 5min + Trump 政治演講 5min cross-style，empirical 證實：

1. **Pure mlx-whisper kwargs 無法解決 cross-30s-window mid-clause cut**:
   - `length_penalty` / `beam_size` / `patience` — mlx 唔支援 beam search → noop / FAIL
   - `max_initial_timestamp` (0.5/1.0/2.0) — 完全 noop
   - `sample_len` (lower) — 反效果（max segment 變更長）
   - `compression_ratio_threshold` / `logprob_threshold` — 唔影響邊界
   - `hallucination_silence_threshold=4.0` — medium 上 work，但 large-v3 上 max segment 跳到 9.58s（反效果）
   - 唯一有效 lever：`temperature=0.0`（固定）— 大幅提升 boundary quality（sent_end% 翻倍）但解唔到 cross-window cut

2. **3-way prototype 對比**（large-v3 + Real Madrid 5min）:
   - A. faster-whisper + vad_filter + max_speech_duration_s=10：n=77, mean 3.61s, ❌ 仍 mid-clause cut, wall 332s（5× 慢）
   - B. mlx temp=0.0 + word-gap split alone：n=113, mean 2.40s, ❌ word gap 唔夠細, tiny rate 35%
   - C. mlx temp=0.0 + Silero VAD chunk-mode：n=74, mean 3.74s, **✅ #3+#4 修復**, wall 65.6s

3. **Stack tuning（C + word-gap refine post-process）**:
   - C alone：mean 3.74s, max 6.12s, func% 16.2%
   - C + wordgap(max_dur=4.0, gap=0.10)：mean 3.19s, max 5.48s, func% 14.0%, ✅ 仍修復 #3+#4

**Conclusion:** Silero VAD pre-segment + chunk-mode mlx-whisper transcribe + word-gap refine 係唯一架構性解決 cross-30s-window cut 嘅可行 stack。

---

## Section 1: High-Level Architecture

```
audio.wav (16kHz mono, extracted from upload)
       ↓
  Silero VAD pre-segment (threshold=0.5, min_silence_ms=500)
       ↓ list of (start_sample, end_sample) speech spans
  Sub-cap > vad_chunk_max_s (25s) chunks
       ↓
  for each chunk:
       mlx-whisper transcribe(
           audio=wav[chunk_start:chunk_end],
           temperature=0.0, word_timestamps=True,
           condition_on_previous_text=False,  # chunk-isolated
       )
       shift segment + word offsets by chunk_start / 16000
       ↓
  concat all chunks' segments
       ↓
  Word-gap refine (max_dur=4.0s, gap_thresh=0.10s, min_dur=1.5s)
       ↓
  List[Segment] with words[] preserved
```

### Engine Compatibility Matrix

| Engine | fine_segmentation 支援 |
|---|---|
| `mlx-whisper` | ✅ Phase 1 target |
| `whisper` (faster-whisper / openai-whisper) | ❌ Phase 1 唔做（佢有 vad_filter built-in） |
| `qwen3-asr` / `flg-asr` | ❌ Stub engines |

`fine_segmentation: true` + `engine != mlx-whisper` → Profile validation reject。

### Integration Point (`app.py:transcribe_with_segments`)

```python
if profile["asr"].get("fine_segmentation") and profile["asr"]["engine"] == "mlx-whisper":
    segments = sentence_split.transcribe_fine_seg(audio_path, profile, ws_emit)
else:
    segments = engine.transcribe(audio_path, language)
    segments = split_segments(segments, ...)  # legacy path 100% unchanged
```

---

## Section 2: Module Layout

### NEW: `backend/asr/sentence_split.py` (~280 lines)

Public API:
- `class FineSegmentationError(Exception)` — setup-level failure
- `transcribe_fine_seg(audio_path, profile, ws_emit) -> list[Segment]` — full pipeline
- `word_gap_split(segments, *, max_dur, gap_thresh, min_dur, safety_max_dur) -> list[Segment]` — testable post-process

Private helpers:
- `_get_silero_model(load_fn)` — module-level singleton with thread-safe lazy init
- `_vad_segment(audio_path, asr_cfg, ...)` — Silero VAD pre-segment
- `_subcap_chunks(spans, max_s)` — sub-cap > 25s
- `_transcribe_chunks(audio_path, chunks, asr_cfg, mlx, ws_emit)` — per-chunk + offset shift
- `_fallback_whole_file(audio_path, asr_cfg, mlx)` — used when VAD返 0 chunks 或 all chunks fail
- `_split_one(seg, max_dur, gap_thresh, min_dur, safety_max_dur)` — word-gap recursion helper

### MODIFIED: `backend/asr/mlx_whisper_engine.py:34-73`

Forward `temperature` kwarg to `mlx_whisper.transcribe()`. Default behavior preserved when `temperature=None` (uses mlx fallback tuple).

`get_params_schema()` adds `temperature` field with `nullable: true`, `min: 0.0`, `max: 1.0`.

### MODIFIED: `backend/profiles.py:_validate_asr()` + `_validate_translation()`

Accepts new fields per Section 3 schema; cross-field validation rejects `fine_segmentation: true` with `engine != mlx-whisper`. Auto-coerces `word_timestamps` → `true` when `fine_segmentation: true`.

### MODIFIED: `backend/app.py`

- `transcribe_with_segments`: branch logic; `transcribed_with_fine_seg` flag into registry
- `_auto_translate`: bypass `merge_to_sentences` when `translation.skip_sentence_merge: true`
- New WebSocket event: `transcription_warning` for runtime fallback notifications

### MODIFIED: `backend/requirements.txt`

```
silero-vad>=6.2.0
```

### NOT MODIFIED

- `backend/asr/segment_utils.py:split_segments()` — legacy path 100% unchanged
- `backend/asr/whisper_engine.py` — faster-whisper engine 唔加 fine_seg
- `backend/translation/sentence_pipeline.py` — only bypassed via flag, no internal change
- `backend/translation/alignment_pipeline.py` / `post_processor.py`

---

## Section 3: Profile Schema

### ASR block 新增 10 個欄位

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `fine_segmentation` | bool | `false` | — | ★ 主開關 |
| `temperature` | float \| null | `null` | [0.0, 1.0] | `0.0` = 固定 greedy（建議 fine_seg=true 配合）；`null` = mlx fallback tuple |
| `vad_threshold` | float | `0.5` | [0.0, 1.0] | Silero VAD speech probability cutoff |
| `vad_min_silence_ms` | int | `500` | [200, 2000] | 兩 chunk 間最少 silence |
| `vad_min_speech_ms` | int | `250` | [100, 1000] | chunk 最短 speech |
| `vad_speech_pad_ms` | int | `200` | [0, 500] | chunk 邊界 padding |
| `vad_chunk_max_s` | int | `25` | [10, 30] | chunk 上限（避 30s window） |
| `refine_max_dur` | float | `4.0` | [3.0, 8.0] | word-gap split 觸發閾值 |
| `refine_gap_thresh` | float | `0.10` | [0.05, 0.50] | inter-word gap 觸發閾值 |
| `refine_min_dur` | float | `1.5` | [0.5, 2.0] | 必須 < `refine_max_dur` |

### Translation block 新增 1 個欄位

| Field | Type | Default | Notes |
|---|---|---|---|
| `skip_sentence_merge` | bool | `false` | bypass `merge_to_sentences` when fine_seg active (Q3 manual flag) |

### Cross-field validation

- `fine_segmentation: true` 必須配 `engine: "mlx-whisper"`，否則 reject
- `fine_segmentation: true` 自動隱式 coerce `word_timestamps: true`
- `refine_min_dur` 必須 < `refine_max_dur`，否則 reject

### Backward compatibility

所有既有 profile JSON 缺呢 11 個 fields → 自動 default。`fine_segmentation: false`（grandfather）→ legacy path 完全不變。

### Frontend UI exposure (per Q4)

`mlx_whisper_engine.py:get_params_schema()` 暴露 2 個 fields：
- `fine_segmentation` (boolean switch)
- `temperature` (float input, nullable)

其餘 8 fields (vad_*, refine_*) 唔出現喺 schema → frontend 唔 render，只 JSON edit。

`translation.skip_sentence_merge` UI checkbox（subtle，hint：「fine_segmentation 開時建議勾選」）。

---

## Section 4: Data Flow + Integration

### transcribe_with_segments branch logic

```python
asr_cfg = profile["asr"]
if asr_cfg.get("fine_segmentation") and asr_cfg["engine"] == "mlx-whisper":
    from backend.asr import sentence_split
    ws_emit = lambda kind, msg: socketio.emit(
        'transcription_warning',
        {'kind': kind, 'message': msg}
    )
    segments = sentence_split.transcribe_fine_seg(audio_path, profile, ws_emit)
else:
    engine = create_asr_engine(asr_cfg)
    segments = engine.transcribe(audio_path, language)
    segments = split_segments(segments, ...)
```

### Auto-translate bypass

```python
translation_cfg = profile["translation"]
skip_merge = translation_cfg.get("skip_sentence_merge", False)
if skip_merge:
    results = engine.translate(segments, ...)
else:
    # 既有邏輯 100% 不變
    ...
```

### WebSocket events

| Event | Type | When |
|---|---|---|
| `subtitle_segment` | existing | unchanged; `words` field populated when fine_seg active |
| `transcription_warning` | NEW | `{kind: "vad_zero" \| "vad_fail" \| "chunk_fail" \| "fine_seg_unavailable", message: str}` |
| `transcription_status` / `_complete` / `_error` | existing | unchanged |
| `pipeline_timing` | existing | unchanged |

Frontend 加 listener handle `transcription_warning` → render amber toast (reuse v3.7 `warning_missing_zh` toast pattern)。

### REST API

| Endpoint | Change |
|---|---|
| `POST /api/transcribe` | unchanged |
| `GET /api/files/<id>` | unchanged but `transcribed_with_fine_seg` field auto-exposed |
| `GET /api/files/<id>/segments` | unchanged but fine_seg files have `words: [...]` populated |
| `PATCH /api/profiles/<id>` | accepts new 11 fields |
| `GET /api/profiles/active` | response includes new fields |

### Registry schema additions

```jsonc
{
  "<file_id>": {
    "...existing fields...": "...",
    "transcribed_with_fine_seg": true,        // ★ NEW
    "segments": [
      { "id": 0, "start": 0.0, "end": 5.38, "text": "...", "words": [...] }
    ]
  }
}
```

舊 file 缺呢 field → app.py 讀時 default `false`（grandfather）。

**Flag semantics**：`transcribed_with_fine_seg: true` 標記「呢個 file 用咗 `transcribe_fine_seg()` pipeline 入口」，**包括** VAD-fallback path（VAD 0 chunks 觸發 `_fallback_whole_file`）— 因為 fallback 仍係 fine_seg pipeline 一部分，segments 仍有 word_timestamps[]。Profile 唔開 fine_seg 走 legacy path 嗰啲 file 唔 set 呢個 flag。

---

## Section 5: Algorithm Specs

### 5.1 Silero VAD model load (singleton)

```python
_silero_model = None
_silero_lock = threading.Lock()

def _get_silero_model(load_fn):
    global _silero_model
    with _silero_lock:
        if _silero_model is None:
            _silero_model = load_fn(onnx=True)
    return _silero_model
```

### 5.2 `_vad_segment(audio_path, asr_cfg, ...)`

```python
def _vad_segment(audio_path, asr_cfg, load_fn, get_ts_fn, read_fn):
    model = _get_silero_model(load_fn)
    wav = read_fn(audio_path, sampling_rate=16000)
    spans = get_ts_fn(
        wav, model, sampling_rate=16000,
        threshold=asr_cfg["vad_threshold"],
        min_speech_duration_ms=asr_cfg["vad_min_speech_ms"],
        min_silence_duration_ms=asr_cfg["vad_min_silence_ms"],
        speech_pad_ms=asr_cfg["vad_speech_pad_ms"],
        return_seconds=False,
    )
    return [(s["start"], s["end"]) for s in spans]
```

### 5.3 `_subcap_chunks(spans, max_s)`

```python
def _subcap_chunks(spans, max_s):
    SR = 16000
    chunk_max = max_s * SR
    out = []
    for cs, ce in spans:
        if (ce - cs) <= chunk_max:
            out.append((cs, ce))
        else:
            cur = cs
            while cur < ce:
                out.append((cur, min(cur + chunk_max, ce)))
                cur += chunk_max
    return out
```

### 5.4 `_transcribe_chunks(audio_path, chunks, asr_cfg, mlx, ws_emit)`

```python
def _transcribe_chunks(audio_path, chunks, asr_cfg, mlx, ws_emit):
    SR = 16000
    from silero_vad import read_audio
    wav = read_audio(audio_path, sampling_rate=SR)
    repo = MODEL_REPO[asr_cfg.get("model_size", "large-v3")]
    
    out = []
    failed_count = 0
    for ci, (cs, ce) in enumerate(chunks):
        chunk_audio = wav[cs:ce]
        if hasattr(chunk_audio, "numpy"):
            chunk_audio = chunk_audio.numpy()
        offset = cs / SR
        try:
            with _mlx_lock:
                r = mlx.transcribe(
                    chunk_audio,
                    path_or_hf_repo=repo,
                    language=asr_cfg.get("language", "en"),
                    task="transcribe",
                    verbose=False,
                    condition_on_previous_text=False,
                    word_timestamps=True,
                    temperature=asr_cfg.get("temperature", 0.0) or 0.0,
                )
        except Exception as e:
            failed_count += 1
            logger.warning(f"chunk {ci} ({cs/SR:.1f}-{ce/SR:.1f}s) transcribe failed: {e}")
            continue
        
        for s in r.get("segments", []):
            text = s.get("text", "").strip()
            if not text:
                continue
            words = [
                Word(
                    word=w.get("word", ""),
                    start=float(w.get("start", 0.0)) + offset,
                    end=float(w.get("end", 0.0)) + offset,
                    probability=float(w.get("probability", 0.0) or 0.0),
                )
                for w in s.get("words", [])
            ]
            out.append({
                "start": float(s["start"]) + offset,
                "end": float(s["end"]) + offset,
                "text": text,
                "words": words,
            })
    
    if failed_count > 0 and ws_emit:
        ws_emit("chunk_fail", f"{failed_count}/{len(chunks)} chunks failed; output may have gaps")
    return out
```

`_mlx_lock` 共用 `mlx_whisper_engine._model_lock` (Apple Silicon Metal context single-thread requirement)。

### 5.5 `word_gap_split(...)` — Public API

```python
def word_gap_split(
    segments,
    *,
    max_dur: float = 4.0,
    gap_thresh: float = 0.10,
    min_dur: float = 1.5,
    safety_max_dur: float = 9.0,
):
    out = []
    for s in segments:
        out.extend(_split_one(s, max_dur, gap_thresh, min_dur, safety_max_dur))
    return out


def _split_one(seg, max_dur, gap_thresh, min_dur, safety_max_dur):
    duration = seg["end"] - seg["start"]
    words = seg.get("words", [])
    if duration <= max_dur or len(words) < 4:
        return [seg]
    
    seg_start, seg_end = seg["start"], seg["end"]
    candidate_gaps = []
    for i in range(1, len(words)):
        gap = words[i]["start"] - words[i-1]["end"]
        left_dur = words[i-1]["end"] - seg_start
        right_dur = seg_end - words[i]["start"]
        if left_dur >= min_dur and right_dur >= min_dur:
            candidate_gaps.append((i, gap))
    
    if not candidate_gaps:
        return [seg]
    
    candidate_gaps.sort(key=lambda x: -x[1])
    best_i, best_gap = candidate_gaps[0]
    
    force_split = duration > safety_max_dur
    if best_gap < gap_thresh and not force_split:
        return [seg]
    
    left_words = words[:best_i]
    right_words = words[best_i:]
    left = {**seg,
            "text": " ".join(w["word"].strip() for w in left_words).strip(),
            "start": left_words[0]["start"],
            "end": left_words[-1]["end"],
            "words": left_words}
    right = {**seg,
             "text": " ".join(w["word"].strip() for w in right_words).strip(),
             "start": right_words[0]["start"],
             "end": right_words[-1]["end"],
             "words": right_words}
    
    result = []
    for c in (left, right):
        result.extend(_split_one(c, max_dur, gap_thresh, min_dur, safety_max_dur))
    return result
```

### 5.6 `_fallback_whole_file(audio_path, asr_cfg, mlx)`

Used when VAD returns 0 spans 或 all chunks fail. Calls baseline `mlx.transcribe(audio_path, ..., temperature=temp, word_timestamps=True, condition_on_previous_text=True)`. Returns Segment list with words[] preserved.

### 5.7 Edge cases

| Case | Behavior |
|---|---|
| Audio < 1s | VAD returns [] → ws_emit("vad_zero", ...) → fallback whole-file |
| Full silence | Same as above |
| Music BGM false positive chunks | mlx transcribe returns empty segments → skip silently |
| Individual chunk audio corrupted | mlx raises → ws_emit("chunk_fail", ...) at end |
| word_timestamps DTW fails (rare mlx bug) | `len(words) < 4` → skip word-gap split |
| All chunks fail | `out == []` → ws_emit("vad_fail", ...) → fallback whole-file |

---

## Section 6: Acceptance Criteria

### 6.1 Functional

| Metric | Target | Test |
|---|---|---|
| `#3+#4 case fix` | ✅ FIXED on Real Madrid 5min fixture | Integration |
| Mean segment duration | 2.5–3.5s | Integration |
| P95 segment duration | ≤ 5.5s | Integration |
| Max segment duration | ≤ 6.0s (hard); ≤ 9.0s (safety) | Integration |
| Sentence-end boundary % | ≥ 35% (interview); ≥ 45% (monologue) | Integration |
| Tiny rate (< 1.5s) | < 8% | Integration |
| `transcribed_with_fine_seg` flag | true after fine_seg run | Unit |
| Grandfather: existing files unchanged | identical content + count | Regression |
| Profile validation reject invalid configs | per Section 3 rules | Unit |
| `skip_sentence_merge: true` bypasses merge | merge_to_sentences NOT called | Unit (mock spy) |

### 6.2 Performance

| Metric | Target |
|---|---|
| Wall clock for 5min audio | ≤ baseline + 15% |
| Silero VAD load | < 3s first call, instant subsequent (singleton) |
| VAD detect on 5min audio | < 2s |
| Memory footprint | ≤ baseline + 50 MB |

### 6.3 Robustness (Q7 Hybrid)

| Case | Expected |
|---|---|
| `silero-vad` missing + fine_seg=true | Raise `FineSegmentationError` with install hint |
| Audio < 1s / all silence | Fallback whole-file + emit `vad_zero` warning |
| Individual chunk fail | Skip + emit `chunk_fail` summary at end |
| All chunks fail | Fallback whole-file + emit `vad_fail` warning |
| word_timestamps missing | `word_gap_split` no-op without crash |
| Segment with < 4 words | Never split |

### 6.4 Backward Compatibility

- Profile JSON 缺新 11 fields → defaults applied，行為不變
- `fine_segmentation: false` → ASR pipeline 100% legacy path
- 既有 469 backend pytest（v3.7 baseline）全部繼續 PASS

### 6.5 Test Coverage

| Test file | New tests | Coverage |
|---|---|---|
| `tests/test_sentence_split.py` (NEW) | 16 | word_gap_split (8), _subcap_chunks (4), setup error (2), edge cases (2) |
| `tests/test_mlx_whisper_engine.py` | +3 | temperature forward, schema, MODEL_REPO |
| `tests/test_profiles.py` | +6 | range validation, cross-field, backward compat |
| `tests/test_app.py` | +4 | branch logic, registry flag, warning event, skip merge |
| `tests/integration/test_fine_segmentation.py` (NEW) | 2 (`@pytest.mark.live`) | Real Madrid + Trump cross-style |

**Total**: ~31 new tests. Backend pytest 由 v3.7 baseline 469 PASS / 12 pre-existing FAIL (481 total) 升至 500 PASS / 12 FAIL (512 total)。

### 6.6 Validation Run

```bash
cd backend && source venv/bin/activate
pytest tests/test_sentence_split.py -v       # 16 PASS
pytest tests/test_mlx_whisper_engine.py -v   # +3 PASS
pytest tests/test_profiles.py -v             # +6 PASS
pytest tests/test_app.py -v                  # +4 PASS
pytest tests/integration/test_fine_segmentation.py -v --run-live  # 2 PASS
pytest tests/ -q                              # 500 PASS / 12 pre-existing FAIL (512 total)
```

End-to-end CLI smoke：active profile fine_seg=true → upload Real Madrid mp4 → check registry transcribed_with_fine_seg=true + segments with words[] → manual eyeball #3+#4 boundary fix。

---

## Section 7: Test Strategy Detail

### 7.1 Unit tests `tests/test_sentence_split.py` (16)

**word_gap_split (8)**:
- `test_no_split_when_under_max_dur` (3.5s, max_dur=4.0)
- `test_splits_at_largest_gap` (5s with 0.5s gap mid-way)
- `test_respects_min_dur` (would create <min_dur side → skip)
- `test_safety_override_for_super_long` (10s, no gaps meet threshold; safety_max_dur forces split)
- `test_keeps_under_safety` (6s, no big gaps, ≤safety → kept)
- `test_recursive_splits_long_chains` (12s with two gaps → 3 segments)
- `test_handles_missing_words` (words[] empty → no split)
- `test_handles_too_few_words` (3 words → no split)

**_subcap_chunks (4)**:
- `test_no_subcap_needed`
- `test_splits_long_span` (60s with max_s=25 → 3 sub-chunks)
- `test_empty_input`
- `test_exact_boundary` (span exactly = max_s)

**Setup error (2)**:
- `test_raises_when_silero_missing` (monkeypatch sys.modules["silero_vad"] = None)
- `test_falls_back_when_vad_returns_zero` (mock VAD → []; assert ws_emit kind="vad_zero")

**Edge cases (2)**:
- `test_safety_max_dur_recursion_bounded` (avoid infinite recursion on pathological input)
- `test_split_preserves_text_content` (concat children's text == parent's text)

### 7.2 `tests/test_mlx_whisper_engine.py` (+3)

- `test_forwards_temperature_kwarg` (capture kwargs in monkeypatched mlx.transcribe)
- `test_omits_temperature_when_null` (temperature=None → kwarg not in call)
- `test_schema_includes_temperature_nullable` (assert schema field with nullable: true)

### 7.3 `tests/test_profiles.py` (+6)

- `test_fine_segmentation_requires_mlx_whisper` (engine="whisper" → ValueError)
- `test_vad_chunk_max_s_range` (5 too low, 35 too high)
- `test_refine_min_dur_less_than_max_dur` (5.0 vs 4.0 → ValueError)
- `test_backward_compat_defaults_fine_seg_false` (missing field → false)
- `test_skip_sentence_merge_bool_validation` (string "yes" → ValueError)
- `test_temperature_range` (1.5 out of range → ValueError)

### 7.4 `tests/test_app.py` (+4)

- `test_routes_to_fine_seg_when_enabled` (monkeypatch transcribe_fine_seg, assert called)
- `test_routes_to_legacy_when_fine_seg_disabled`
- `test_registry_records_transcribed_with_fine_seg_flag` (assert reg[id].transcribed_with_fine_seg == true)
- `test_auto_translate_skips_merge_when_flag_set` (spy on merge_to_sentences, assert not called)

### 7.5 Integration tests `tests/integration/test_fine_segmentation.py` (2 live)

```python
@pytest.mark.live
def test_real_madrid_5min_stack_metrics():
    audio = "/tmp/l1_real_madrid.wav"
    if not os.path.exists(audio): pytest.skip("fixture not available")
    profile = _profile_with_fine_seg(model="large-v3")
    segs = transcribe_fine_seg(audio, profile, ws_emit=None)
    durs = [s["end"] - s["start"] for s in segs]
    assert 70 <= len(segs) <= 100
    assert 2.5 <= sum(durs)/len(durs) <= 3.5
    assert max(durs) <= 6.0
    for i, s in enumerate(segs[:-1]):
        text = s["text"].strip().lower()
        if "needs is a" in text:
            assert not text.endswith(" a"), f"#3+#4 cut still present at seg {i}"

@pytest.mark.live
def test_trump_speech_5min_cross_style():
    ...
```

`tests/conftest.py` add `--run-live` flag; integration tests skipped unless flag set.

### 7.6 Fixtures

| Fixture | Source | Use |
|---|---|---|
| `tests/fixtures/silence_1s.wav` (NEW, generated in conftest) | numpy + soundfile | Test F2 (vad_zero) |
| `tests/fixtures/short_speech_3s.wav` (NEW, generated) | numpy + soundfile | Test fast path |
| `/tmp/l1_real_madrid.wav` | existing prototype fixture | Live integration |

---

## Section 8: Documentation + Rollout

### 8.1 CLAUDE.md v3.8 section

(See spec body in Section 8 of brainstorm; will be added verbatim under "Completed Features" before v3.7 entry.)

### 8.2 README.md addition (Traditional Chinese, user-facing)

```markdown
## v3.8 細粒度 ASR 分句

廣播字幕優化：用 Silero VAD 先切 audio → mlx-whisper 逐 chunk 轉錄 → 
word-gap refine 切細到 mean 約 3 秒、max 約 5.5 秒。

**啟用方式**：Profile 設定
- ASR engine 選 `mlx-whisper`
- 開「細粒度分句（廣播字幕優化）」
- 解碼溫度設 `0.0`（停 fallback，最穩定 boundary）
- 翻譯設定建議勾選「跳過句子合併」

**新 dependency**：`pip install silero-vad`（已加入 requirements.txt）
```

### 8.3 docs/PRD.md

Flip ASR fine segmentation feature row from 📋 → ✅ v3.8。

### 8.4 Implementation phases

| Phase | Tasks | Risk |
|---|---|---|
| A. Setup + Schema | requirements.txt, profiles.py validation, mlx_engine temperature plumbing, +9 unit tests | Low |
| B. Core algorithm | sentence_split.py module, +16 unit tests | Med |
| C. Pipeline integration | app.py branch + WS warning + skip_sentence_merge + registry flag, +4 tests | Med |
| D. UI exposure | Profile form 2 fields + warning toast | Low |
| E. Live validation | Integration tests --run-live; update validation tracker post-impl | Low |
| F. Documentation | CLAUDE.md / README.md / PRD.md | Low |

### 8.5 Critical files

| File | Phase |
|---|---|
| `backend/asr/sentence_split.py` (NEW) | B |
| `backend/asr/mlx_whisper_engine.py` | A |
| `backend/profiles.py` | A |
| `backend/app.py` | C |
| `backend/requirements.txt` | A |
| `frontend/index.html` (Profile form) | D |
| `tests/test_sentence_split.py` (NEW) | B |
| `tests/test_mlx_whisper_engine.py` | A |
| `tests/test_profiles.py` | A |
| `tests/test_app.py` | C |
| `tests/integration/test_fine_segmentation.py` (NEW) | E |
| `tests/conftest.py` | E |

### 8.6 Estimated effort + Risk

- **時間**: 12-18 小時 implementation + tests + live validation
- **Risk**: **Low**
  - Empirical validation 已有 11-config A/B + 3-way prototype + stack tuning 數據
  - Algorithm 簡單（無 NLP heuristic）
  - Opt-in flag → 既有 user 100% backward compat
  - Permissive runtime fallback → individual edge case 唔 break workflow

### 8.7 Out-of-scope (defer to v3.9+)

- Manual re-transcribe button per-file (Q6 phase 2)
- faster-whisper engine 加 fine_seg flag
- Multi-VAD libraries (WebRTC / energy-based)
- Live A/B harness 自動化
