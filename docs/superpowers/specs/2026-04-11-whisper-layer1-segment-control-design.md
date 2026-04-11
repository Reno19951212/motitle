# Whisper Layer 1 Segment Control — Design Spec

**Date:** 2026-04-11
**Feature:** Expose Whisper-native segmentation parameters in Profile ASR settings
**Scope:** `backend/asr/whisper_engine.py`, `frontend/index.html`

---

## 1. Overview

ASR segment length is currently controlled by two independent layers:

- **Layer 1 — Whisper native segmentation** (inside `WhisperEngine.transcribe()`): faster-whisper's internal beam search and silence detection. Currently no parameters are passed — all defaults used.
- **Layer 2 — Post-processing split** (`split_segments()`): cuts oversized segments after ASR using `max_words_per_segment` and `max_segment_duration` from Language Config.

This spec adds Layer 1 control: three faster-whisper parameters are exposed via `WhisperEngine.get_params_schema()` and wired into `_transcribe_faster()`. The existing dynamic params panel in the Profile form surfaces them automatically with no additional frontend routing code.

Layer 2 (Language Config panel) is unchanged.

---

## 2. New Parameters

### Added to `WhisperEngine.get_params_schema()`

| Param | Type | Label in UI | Default | Effect |
|-------|------|-------------|---------|--------|
| `max_new_tokens` | integer (nullable) | 每句字幕長度上限（Token） | `null` (unlimited) | Hard cap on tokens generated per segment. ~1 token ≈ 0.75 English words. |
| `condition_on_previous_text` | boolean | Condition On Prev | `true` | `true` = use prior segment text as context (more coherent); `false` = each segment independent (shorter, cleaner) |
| `vad_filter` | boolean | VAD Filter | `false` | Voice Activity Detection — auto-split at silence boundaries |

Schema entries:

```python
"max_new_tokens": {
    "type": "integer",
    "description": "每句字幕長度上限（Token）。留空 = 無限制。約 1 token ≈ 0.75 個英文字",
    "minimum": 1,
    "default": None,
},
"condition_on_previous_text": {
    "type": "boolean",
    "description": "用上句文本做 context（true = 更連貫；false = 每句獨立更短）",
    "default": True,
},
"vad_filter": {
    "type": "boolean",
    "description": "語音活動偵測 — 在靜音位置自動切割 segment",
    "default": False,
},
```

---

## 3. Backend Changes

### `WhisperEngine._transcribe_faster()`

Pass the three new params to `model.transcribe()`:

```python
def _transcribe_faster(self, model, audio_path: str, language: str) -> list[Segment]:
    max_new_tokens = self._config.get("max_new_tokens") or None  # 0 / null → None
    seg_iter, _info = model.transcribe(
        audio_path,
        language=language,
        task="transcribe",
        max_new_tokens=max_new_tokens,
        condition_on_previous_text=self._config.get("condition_on_previous_text", True),
        vad_filter=self._config.get("vad_filter", False),
    )
    segments = []
    for seg in seg_iter:
        segments.append(Segment(start=seg.start, end=seg.end, text=seg.text.strip()))
    return segments
```

### `WhisperEngine._transcribe_openai()`

openai-whisper does not support `max_new_tokens` or `vad_filter`. Only `condition_on_previous_text` is supported. The other two params are silently ignored for the openai-whisper path.

```python
def _transcribe_openai(self, model, audio_path: str, language: str) -> list[Segment]:
    result = model.transcribe(
        audio_path,
        language=language,
        task="transcribe",
        verbose=False,
        fp16=False,
        condition_on_previous_text=self._config.get("condition_on_previous_text", True),
    )
    ...
```

### `WhisperEngine.__init__()`

No change needed — `self._config` already stores the full config dict, and the new params are read from it in `_transcribe_faster()`.

---

## 4. Frontend Changes

Only `frontend/index.html` is modified.

### `renderParamField()` — boolean type support

Add a new branch for `paramSchema.type === 'boolean'`:

```js
} else if (paramSchema.type === 'boolean') {
    const trueSelected  = String(value) === 'true'  ? 'selected' : '';
    const falseSelected = String(value) === 'false' ? 'selected' : '';
    input = `<select id="${id}">
      <option value="true"  ${trueSelected}>true</option>
      <option value="false" ${falseSelected}>false</option>
    </select>`;
}
```

**Value priority:** `currentValue` (from existing profile) → `paramSchema.default` → `false` for booleans.

### `renderParamField()` — nullable integer placeholder

For integer params whose `default` is `null` (i.e. `max_new_tokens`), render a number input with a placeholder instead of a value:

```js
} else if (paramSchema.type === 'number' || paramSchema.type === 'integer') {
    const min = paramSchema.minimum !== undefined ? ` min="${paramSchema.minimum}"` : '';
    const max = paramSchema.maximum !== undefined ? ` max="${paramSchema.maximum}"` : '';
    const step = paramSchema.type === 'number' ? ' step="0.1"' : '';
    const displayValue = (value === null || value === undefined) ? '' : String(value);
    const placeholder = paramSchema.default === null ? ' placeholder="留空 = 無限制"' : '';
    input = `<input type="number" id="${id}" value="${escapeHtml(displayValue)}"${min}${max}${step}${placeholder}>`;
}
```

### `saveProfile()` — schema-aware param collection

Replace the current type-only check with a schema-aware loop that handles boolean and nullable integer:

```js
for (const [name, schema] of Object.entries(currentAsrSchema.params || {})) {
    if (EXCLUDED_ASR_PARAMS.includes(name)) continue;
    const el = document.getElementById(`pf-asr-${name}`);
    if (!el) continue;
    if (schema.type === 'boolean') {
        asrParams[name] = el.value === 'true';
    } else if (schema.type === 'number' || schema.type === 'integer') {
        asrParams[name] = el.value === '' ? null : Number(el.value);
    } else {
        asrParams[name] = el.value;
    }
}
```

Apply the same pattern to the translation param collection loop (for future boolean params in translation engines).

---

## 5. What Is NOT Changed

- **Layer 2** (`split_segments()`, Language Config panel) — unchanged
- **Profile storage / API** — no changes; the dynamic params system already handles arbitrary ASR fields
- **Other ASR engines** (Qwen3-ASR, FLG-ASR) — their schemas do not include these params; unaffected
- **Translation engine params** — the save loop update is a defensive fix only; no translation schema changes

---

## 6. Files Changed

| File | Change |
|------|--------|
| `backend/asr/whisper_engine.py` | Add 3 params to schema; pass to `_transcribe_faster()`; pass `condition_on_previous_text` to `_transcribe_openai()` |
| `frontend/index.html` | Add boolean branch to `renderParamField()`; add nullable integer placeholder; update ASR + translation param collection in `saveProfile()` |
