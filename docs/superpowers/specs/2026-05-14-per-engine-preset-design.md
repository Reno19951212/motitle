# Per-Engine Preset + Danger Warning Refactor (v3.16 stop-gap)

**Status**: Draft 2026-05-14
**Branch**: `chore/v3.15-cleanup-2026-05-13`
**Replaces**: v3.15 Profile UI MVP（commit `1db559d`）嘅 pipeline-level preset / danger combo 佈局

## Goal

將 Profile Save modal（`#ppsOverlay`）入面嘅 preset picker 同 danger combo 警示由 modal 頂部 pipeline-level 位置，搬入 ASR section 同 MT section 入面各自獨立顯示。一句講：**preset / warning 由 pipeline-scoped 改為 engine-scoped**。

## Why

v3.15 MVP 將 5 個 preset 同 5 個 danger combo 全部擺喺 modal 最頂，bundle ASR + MT 一齊揀。用戶 feedback：呢個唔 match 心智模型 — 配置 ASR 嘅嘢應該住喺 ASR 區、配置 MT 嘅嘢應該住喺 MT 區。

實際效果：

- **混搭可能**：用戶可以挑「accuracy ASR」+「fast-draft MT」，而依家嘅 bundled preset 強制連 ASR + MT 一齊覆蓋。
- **就近 fix**：danger warning 出現喺對應 engine section 入面，用戶 scroll 落 ASR section 就見到 ASR 警告 + 對應控件，唔需要喺頂部警告同下面 form 之間跳。
- **未來新 engine 易加**：將來新增 Qwen3-ASR / FLG-ASR / 新 MT engine，加 preset 入對應 dict 就得，唔需要諗 cross-engine bundling 邏輯。

## Architecture

純 frontend refactor，single file：[frontend/index.html](frontend/index.html)。Backend / API contract / Profile JSON schema 完全唔郁。

### Data 結構（取代現有單一 `PROFILE_PRESETS` + `DANGER_COMBOS`）

```js
// ASR-only presets — 淨係 mutate asr.* 欄位
const ASR_PRESETS = {
  accuracy: {
    label: 'Accuracy',
    description: 'large-v3 + word_timestamps，無 cascade',
    config: { model_size: 'large-v3', condition_on_previous_text: false, word_timestamps: true },
  },
  speed: {
    label: 'Speed',
    description: 'small model + VAD filter，快但糙',
    config: { model_size: 'small', condition_on_previous_text: false, word_timestamps: false },
  },
  debug: {
    label: 'Debug',
    description: '排查 hallucination，含 initial_prompt 樣本',
    config: { model_size: 'large-v3', condition_on_previous_text: false, word_timestamps: true, initial_prompt: '以下係香港新聞，繁體中文。' },
  },
  custom: { label: 'Custom', description: '保留現有 ASR 設定' },
};

// MT-only presets — 淨係 mutate translation.* 欄位
const MT_PRESETS = {
  'broadcast-quality': {
    label: 'Broadcast Quality',
    description: '逐段對齊，慢但準',
    config: { batch_size: 1, temperature: 0.1, parallel_batches: 1, translation_passes: 2, alignment_mode: 'llm-markers' },
  },
  'fast-draft': {
    label: 'Fast Draft',
    description: '速度優先 preview',
    config: { batch_size: 10, temperature: 0.15, parallel_batches: 4, translation_passes: 1, alignment_mode: '' },
  },
  'literal-ref': {
    label: 'Literal Reference',
    description: '逐字翻譯，溫度 0',
    config: { batch_size: 1, temperature: 0, parallel_batches: 1, translation_passes: 1, alignment_mode: 'llm-markers' },
  },
  custom: { label: 'Custom', description: '保留現有 MT 設定' },
};

// ASR-only dangers
const ASR_DANGERS = [
  {
    id: 'zh-cascade-risk',
    severity: 'high',
    check: (cfg) => cfg.asr?.condition_on_previous_text === true && (cfg.asr?.language === 'zh' || cfg.asr?.language_config_id === 'zh'),
    msg: '⚠ ZH source 上開 condition_on_previous_text：v3.8 揾到 34% segments cascade 重複。建議 false。',
  },
];

// MT-only dangers（含 cross-engine warning — 因為觸發 param 喺 MT）
const MT_DANGERS = [
  {
    id: 'parallel-disables-context',
    severity: 'critical',
    check: (cfg) => (cfg.translation?.parallel_batches || 1) > 1,
    msg: '⚠ parallel_batches > 1 強制 disable context window。建議只配 alignment_mode 空嘅 batched flow。',
  },
  {
    id: 'batch-large-passes-2',
    severity: 'high',
    check: (cfg) => (cfg.translation?.batch_size || 1) > 5 && (cfg.translation?.translation_passes || 1) === 2,
    msg: '⚠ batch>5 + passes=2：Pass 2 enrichment 喺 batched mode 行為唔一致。',
  },
  {
    id: 'batch-large-cross-bleed',
    severity: 'medium',
    check: (cfg) => (cfg.translation?.batch_size || 1) > 5 && (cfg.translation?.alignment_mode || '') === '',
    msg: '⚠ batch>5 + 冇 alignment：跨 segment 易溢出（v3.8 Italian Como bug）。',
  },
  {
    id: 'parallel-and-alignment',
    severity: 'medium',
    check: (cfg) => (cfg.translation?.parallel_batches || 1) > 1 && (cfg.translation?.alignment_mode || '') === 'llm-markers',
    msg: 'ℹ parallel disable context，但 llm-markers 需要 context。',
  },
  {
    id: 'word-timestamps-needed-for-alignment',
    severity: 'high',
    check: (cfg) => (cfg.translation?.alignment_mode || '') === 'llm-markers' && cfg.asr?.word_timestamps !== true,
    msg: '⚠ alignment_mode=llm-markers 需要 ASR section 嘅 word_timestamps=true。請去上面 ASR section 開啟。',
  },
];
```

`word-timestamps-needed-for-alignment` 係新 cross-engine warning，按 user 指示擺喺 MT section（觸發 param `alignment_mode` 喺 MT block 入面）。Warning 文字明確指返用戶去 ASR section 改。

### State 結構

```js
// 取代 _pendingPresetConfig 單一 obj
let _pendingAsrPreset = null;    // { config: {...} } | null
let _pendingMtPreset = null;     // { config: {...} } | null
```

### UI 佈局改動

**重要 codebase 觀察**：`#ppsOverlay` 係「儲存 Profile 預設」modal，本身**唔包含**可編輯嘅 ASR/MT param form（用戶只能透過揀 preset 嚟設值）。所以「ASR section」/「MT section」呢度指**獨立 labeled fieldset 容器**，唔係 collapsible form 區。

```
#ppsOverlay
├─ 預設名稱 input
├─ 描述 input
├─ Summary read-only 顯示
├─ 字幕來源 fieldset（不變）
├─ 🎙️ ASR 預設 fieldset（新增）
│  ├─ <div id="ppsAsrPresetButtons">
│  └─ <div id="ppsAsrDangerWarnings">
├─ 🌐 MT 預設 fieldset（新增）
│  ├─ <div id="ppsMtPresetButtons">
│  └─ <div id="ppsMtDangerWarnings">
└─ Save / Cancel 按鈕
```

**刪走**：[frontend/index.html:4891-4897](frontend/index.html#L4891-L4897) 嘅 `<div class="pps-preset-section" id="ppsPresetSection">`（含 `#ppsPresetButtons`）同 `<div class="pps-warning-container" id="ppsWarnings">`（注：實際 id 係 `ppsWarnings`，唔係 spec 之前寫嘅 `ppsDangerWarnings`）。

**位置**：兩個新 fieldset 擺喺現有「字幕來源預設」fieldset（[frontend/index.html:4911-4929](frontend/index.html#L4911-L4929)）下面，仍喺 `style="padding: 16px 20px;"` 嘅 inner padding wrapper 入面。

### Function 改動

| 舊 | 新 |
|---|---|
| `_renderPresetButtons()` | `_renderAsrPresetButtons()` + `_renderMtPresetButtons()` |
| `_applyPreset(key)` | `_applyAsrPreset(key)` + `_applyMtPreset(key)` |
| `_evaluateDangerCombos()` | `_evaluateAsrDangers()` + `_evaluateMtDangers()` |
| `_scheduleDangerEval()` | 一個 timer，fire 時 call 兩個 evaluator |
| `_ppsEffectiveConfig()` | 讀 `_pendingAsrPreset.config` + `_pendingMtPreset.config` 兩個 source |
| `_updatePpsSummary()` | 顯示「ASR: <preset> + MT: <preset>」兩部分，並列 |

`saveProfileAsPreset` 嘅 deep-merge 部分由：

```js
// 舊
const body = { ...base, asr: {...base.asr, ..._pendingPresetConfig.asr}, translation: {...base.translation, ..._pendingPresetConfig.translation} };
```

改為：

```js
// 新
const asrOverride = _pendingAsrPreset?.config || {};
const mtOverride = _pendingMtPreset?.config || {};
const body = { ...base, asr: {...base.asr, ...asrOverride}, translation: {...base.translation, ...mtOverride} };
```

## Data flow

1. 用戶開 Profile Save modal
2. `_openPpsModal()` call `_renderAsrPresetButtons()` + `_renderMtPresetButtons()`，render preset chip 落兩個 section
3. 用戶 click ASR preset chip → `_applyAsrPreset(key)` 設 `_pendingAsrPreset`，標 chip active，trigger danger re-eval
4. 用戶 click MT preset chip → `_applyMtPreset(key)` 同上，獨立進行
5. 用戶 manual 改任何 form field → input listener fire `_scheduleDangerEval()` → 220ms debounce 後 call `_evaluateAsrDangers()` + `_evaluateMtDangers()`，各自 render warning chip 落自己 container
6. 用戶 click「儲存」 → `saveProfileAsPreset()` deep-merge 兩個 pending preset 落 base profile → POST/PATCH

## Error handling

- 任何 preset 揀完之後再 manual 改 form field：preset chip 自動 deactivate（同 v3.15 MVP 行為一致），_pendingAsrPreset / _pendingMtPreset 清返 null，danger eval 改讀純 form value
- Cross-engine warning 觸發但 ASR section 摺埋：用戶 click warning chip 自動展開 ASR section + scroll 到 word_timestamps 欄位（nice-to-have，optional）
- 兩個 evaluator 各自 catch error 唔互相影響

## Testing

更新 `frontend/tests/test_profile_ui_guidance.spec.js`：

| 測試 | 改動 |
|---|---|
| Test 1（Broadcast Quality 套用→batch=1） | Selector 改：preset chip 由 `#ppsPresetButtons` 揾去 `#ppsMtPresetButtons` |
| Test 2（parallel_batches=4 → critical warning） | Selector 改：warning chip 由 `#ppsDangerWarnings` 揾去 `#ppsMtDangerWarnings` |
| **新 Test 3** | ASR section 揀「Accuracy」+ MT section 揀「Fast Draft」，verify 兩個 active 同時、互不覆蓋；儲存後 GET profile，verify ASR + MT 兩 block 都 contain 對應 preset 值 |
| **新 Test 4** | MT 揀 alignment_mode=llm-markers + ASR word_timestamps=false → verify `#ppsMtDangerWarnings` 出現 cross-engine warning 文字 |

Backend：唔需要新 test。Profile API schema 不變。

## Migration notes

無 data migration 需要 — preset 純 UI 概念，唔 persist 入 Profile JSON。已存在嘅 profile 開 modal 時 `_pendingAsrPreset` + `_pendingMtPreset` 都係 null，所有 chip default inactive，form 值直接 show profile 現值。

## Scope guardrails

**唔做**：
- backend engine schema 加 `presets` field（Approach 3，over-engineering for current scope）
- 保留 modal 頂部 bundled preset 做「一鍵」（user 拒絕）
- 改 Profile JSON schema
- 加新 ASR / MT field
- 改其他 modal（Glossary / Font）

**做嘅範圍**：`frontend/index.html` 大約 200 行 JS + 4 個 div container + selector update。
