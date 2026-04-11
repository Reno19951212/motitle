# Engine Selector + Dynamic Params Panel — Design Spec

**Date:** 2026-04-11  
**Feature:** Dynamic Engine Selection with Schema-Driven Parameters  
**Scope:** `frontend/index.html` — Profile edit/create form (ASR 設定 + 翻譯設定 sections)

---

## 1. Overview

The backend exposes full engine discovery APIs (list engines with availability, per-engine param schemas, translation model lists), but the frontend profile form uses hardcoded engine dropdowns with **incorrect engine name values** ("qwen3" instead of "qwen3-asr"). This spec defines a schema-driven replacement where engine lists are fetched from the API and param fields are generated dynamically from each engine's schema.

**Only `frontend/index.html` is modified. No backend changes required.**

---

## 2. Layout & Components

The Profile form's **ASR 設定** and **翻譯設定** collapsible sections are replaced. **基本資訊** and **字型設定** are unchanged.

### ASR 設定 (new)

```
ASR 設定 ▼
┌────────────────────────────────────┐
│ 引擎:  [whisper ▼]  🟢 可用        │  ← dynamic from API, dot = availability
│                                    │
│  ── 引擎參數 ──                     │  ← dynamically generated from params schema
│ Model Size:  [small ▼]             │
│ Language:    [en ▼]                │
│ Device:      [auto ▼]              │
│                                    │
│ Language Config ID: [en      ]     │  ← static field (profile-specific, not in schema)
└────────────────────────────────────┘
```

### 翻譯設定 (new)

```
翻譯設定 ▼
┌────────────────────────────────────┐
│ 引擎:  [mock ▼]  🟢 可用           │  ← dynamic from API
│ Model: mock  ✓ 已載入              │  ← model name + availability from /models; e.g. "qwen2.5:72b ✗ 未載入"
│                                    │
│  ── 引擎參數 ──                     │  ← dynamically generated from params schema
│ Style: [formal ▼]                  │
│                                    │
│ 詞彙表: [無 ▼]                     │  ← static, from glossariesData (unchanged)
└────────────────────────────────────┘
```

### Availability Indicator

- Green dot (●) + label "可用" → `available: true`
- Grey dot (●) + label "不可用" → `available: false`
- Unavailable engines in dropdown: `disabled` attribute + `title="此引擎目前不可用"`

---

## 3. Data Flow & State

### New JS State Variables

Add after existing `let asrEnginesData` (reuse if already declared), otherwise add new:

```js
let asrEnginesData = []         // [{ engine, available, description }, ...]
let translationEnginesData = [] // [{ engine, available, description }, ...]
let currentAsrSchema = null     // last-fetched ASR params schema ({ engine, params: {...} })
let currentTranslationSchema = null  // last-fetched translation params schema
```

`currentAsrSchema` and `currentTranslationSchema` are updated on every engine change and cleared to `null` when the form is cancelled or a new form is opened. Models data is fetched and rendered directly into the DOM without being stored.

### Page Load

At page load (`DOMContentLoaded`), fetch engine lists once alongside existing `loadProfiles()` and `loadGlossaries()`:

```js
async function loadAsrEngines() {
  const resp = await fetch(`${API_BASE}/api/asr/engines`);
  const data = await resp.json();
  asrEnginesData = data.engines || [];
}

async function loadTranslationEngines() {
  const resp = await fetch(`${API_BASE}/api/translation/engines`);
  const data = await resp.json();
  translationEnginesData = data.engines || [];
}
```

Both are called in parallel at startup. Engine lists do not change at runtime, so no re-fetch is needed.

### Form Open (edit or create)

When `buildProfileFormHTML(profile)` renders the ASR and translation sections:

1. Render engine dropdown from `asrEnginesData` / `translationEnginesData`
2. Pre-select `profile.asr.engine` / `profile.translation.engine` (for new profiles: pre-select the first available engine; if none available, pre-select the first engine in the list regardless)
3. Immediately fetch params schema for the pre-selected engine
4. Render dynamic param fields, pre-filling with `profile.asr.*` / `profile.translation.*` values where the key matches; use schema `default` for unmatched keys

### Engine Change (onchange)

When the ASR engine dropdown changes:
```
→ show loading spinner in params area
→ fetch GET /api/asr/engines/<new>/params
→ clear params area → render new fields with schema defaults
→ hide spinner
```

When the translation engine dropdown changes:
```
→ show loading spinner in params area
→ fetch GET /api/translation/engines/<new>/params (parallel with models fetch)
→ fetch GET /api/translation/engines/<new>/models
→ clear params area → render new fields with schema defaults
→ update model info row
→ hide spinner
```

### API Calls Summary

| Action | API Call |
|--------|----------|
| Page load | `GET /api/asr/engines` + `GET /api/translation/engines` |
| Form open / engine pre-select | `GET /api/asr/engines/<engine>/params` |
| Form open (translation) | `GET /api/translation/engines/<engine>/params` + `GET /api/translation/engines/<engine>/models` |
| ASR engine changed | `GET /api/asr/engines/<new>/params` |
| Translation engine changed | `GET /api/translation/engines/<new>/params` + `GET /api/translation/engines/<new>/models` |

---

## 4. Schema → DOM Rendering

### `renderParamField(name, paramSchema, currentValue)`

Render one form field from a param schema entry:

| Condition | Rendered element |
|-----------|-----------------|
| `paramSchema.enum` exists | `<select>` with all enum values as `<option>` |
| `paramSchema.type === "number"` | `<input type="number">` |
| `paramSchema.type === "string"` (no enum) | `<input type="text">` |

**Value priority:** `currentValue` (from existing profile) → `paramSchema.default` → empty

**Label:** Use `name` (formatted as human-readable label). Show `paramSchema.description` as `title` tooltip on the label.

### Static Fields (always present, not schema-driven)

| Section | Field | Notes |
|---------|-------|-------|
| ASR 設定 | Language Config ID | text input, pre-fill from `profile.asr.language_config_id`, default `"en"` |
| 翻譯設定 | 詞彙表 | select from `glossariesData`, pre-fill from `profile.translation.glossary_id` |

Static fields are rendered **after** dynamic params fields in their respective sections.

### Engine Params Container Structure

```html
<div class="pf-engine-params" id="asr-params-container">
  <!-- loading spinner OR dynamically rendered fields -->
</div>
```

---

## 5. Save Payload

`saveProfile()` must always send **complete** `asr`, `translation`, and `font` blocks (backend PATCH does shallow top-level merge — partial nested objects replace the entire block).

**Collecting dynamic ASR params:**

```js
// currentAsrSchema is the last-fetched schema for the current ASR engine
const asrParams = {};
for (const [name] of Object.entries(currentAsrSchema.params)) {
  const el = document.getElementById(`pf-asr-${name}`);
  if (el) asrParams[name] = el.type === 'number' ? Number(el.value) : el.value;
}
const asrBlock = {
  engine: asrEngineDropdown.value,
  language_config_id: document.getElementById('pf-asr-language_config_id').value,
  ...asrParams,
};
```

Same pattern for translation block (append `glossary_id` from the static glossary dropdown; set `glossary_id: null` if "無" selected).

**`currentAsrSchema` and `currentTranslationSchema`** are JS variables declared alongside the other state vars (`editingProfileId`, etc.), set each time a params fetch completes. They are updated on every engine change and cleared (`null`) when the form is cancelled or a new form is opened.

---

## 6. Error Handling

| Scenario | Handling |
|----------|----------|
| `GET /api/asr/engines` or `/translation/engines` fails on page load | Toast "無法載入引擎清單"; engine dropdown shows placeholder "-- 載入失敗 --"; Save disabled |
| `GET /api/.../params` fails | Params area shows "無法載入引擎參數，請重試"; Save button disabled until resolved |
| `GET /api/.../models` fails | Model info row shows "—"; does NOT block save |
| Engine `available: false` selected | Allowed (user may be preparing offline config); backend validate will catch runtime errors |
| Params fetch in progress | Spinner shown in params area; Save disabled during fetch |
| Duplicate submission | Save button disabled during API call (existing behaviour, unchanged) |

---

## 7. Files Changed

- `frontend/index.html` — modify Profile form's ASR 設定 and 翻譯設定 sections only

No new files. No backend changes.
