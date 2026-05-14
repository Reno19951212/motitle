# Per-Engine Preset Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 Profile Save modal (`#ppsOverlay`) 由 pipeline-level bundled preset / danger warning 改為 per-engine（ASR + MT 各自獨立）。

**Architecture:** 純 frontend refactor。`frontend/index.html` 唯一改動。`ppsOverlay` modal 內部刪走頂部 bundled `#ppsPresetSection` + `#ppsWarnings`，喺現有 fieldset 後加兩個獨立 fieldset：`ASR 預設` + `MT 預設`，各含自己嘅 preset chip 列 + danger warning 列。JS data structure 由單一 `PROFILE_PRESETS` + `DANGER_COMBOS` 拆做 4 個 const（ASR_PRESETS / MT_PRESETS / ASR_DANGERS / MT_DANGERS），state 由 `_pendingPresetConfig` 拆做 `_pendingAsrPreset` + `_pendingMtPreset`。Backend / API 完全不變。

**Tech Stack:** Vanilla HTML/CSS/JS (no build step), Playwright for E2E. 對應 spec: [docs/superpowers/specs/2026-05-14-per-engine-preset-design.md](docs/superpowers/specs/2026-05-14-per-engine-preset-design.md)

---

## File Structure

唯一 production file：[frontend/index.html](frontend/index.html)（4988 行 monolith — 改其中 ~270 行 JS + ~25 行 HTML）。

唯一 test file：[frontend/tests/test_profile_ui_guidance.spec.js](frontend/tests/test_profile_ui_guidance.spec.js)（現有 2 個 test，refactor + 新加 2 個）。

無新增 file。無 backend change。無 docs/CLAUDE.md change（v3.16 entry 將喺 plan execute 完成後另開 task 加）。

---

## Task 1：Playwright 測試先行（failing baseline）

**Goal**：寫齊 4 個新 selector 嘅 Playwright test。run 之後全部 fail（new selector 唔存在），用 `test.fixme()` annotation 標記，咁就可以 commit 唔污染 CI。

**Files:**
- Modify: `frontend/tests/test_profile_ui_guidance.spec.js`（整個文件重寫）

- [ ] **Step 1：開現有 test file 確認 baseline**

Run: `cat "frontend/tests/test_profile_ui_guidance.spec.js"`
Expected: 兩個 `test()` 開頭，selector 用 `#ppsPresetButtons` + `#ppsWarnings`。

- [ ] **Step 2：用以下完整 file 內容覆蓋 `frontend/tests/test_profile_ui_guidance.spec.js`**

```javascript
// E2E test for v3.16 per-engine preset + danger warning split.
// All four tests target new container IDs introduced in this refactor.
// `test.fixme()` markers stay in until implementation reaches each stage.

const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

async function _openPpsModal(page) {
  await page.goto(BASE + "/");
  await page.waitForLoadState("domcontentloaded");
  // Sidebar → 預設 → 新增（opens ppsOverlay）
  await page.click("text=+ 新增預設");
  await page.waitForSelector("#ppsOverlay.open", { timeout: 3000 });
}

test("ASR preset chip 'Accuracy' sets model_size=large-v3 + word_timestamps=true", async ({ page }) => {
  await _openPpsModal(page);

  // Click ASR section's "Accuracy" chip
  const accuracyBtn = page.locator("#ppsAsrPresetButtons button", { hasText: "Accuracy" });
  await expect(accuracyBtn).toBeVisible();
  await accuracyBtn.click();

  // Verify chip becomes active
  await expect(accuracyBtn).toHaveClass(/active/);

  // Verify the summary block reflects ASR override
  const summary = await page.locator("#ppsSummary").textContent();
  expect(summary).toContain("large-v3");
});

test("MT preset chip 'Fast Draft' sets batch_size=10 + parallel_batches=4", async ({ page }) => {
  await _openPpsModal(page);

  const fastDraftBtn = page.locator("#ppsMtPresetButtons button", { hasText: "Fast Draft" });
  await expect(fastDraftBtn).toBeVisible();
  await fastDraftBtn.click();

  await expect(fastDraftBtn).toHaveClass(/active/);

  // Fast Draft sets parallel_batches=4, which triggers critical warning
  const warning = page.locator("#ppsMtDangerWarnings .pps-warning-chip");
  await expect(warning).toBeVisible({ timeout: 1000 });
  await expect(warning).toContainText(/parallel_batches > 1/);
});

test("Mix-and-match: ASR Accuracy + MT Fast Draft both active simultaneously", async ({ page }) => {
  await _openPpsModal(page);

  await page.locator("#ppsAsrPresetButtons button", { hasText: "Accuracy" }).click();
  await page.locator("#ppsMtPresetButtons button", { hasText: "Fast Draft" }).click();

  // Both chips active concurrently
  await expect(page.locator("#ppsAsrPresetButtons button.active", { hasText: "Accuracy" })).toBeVisible();
  await expect(page.locator("#ppsMtPresetButtons button.active", { hasText: "Fast Draft" })).toBeVisible();

  // Summary mentions both
  const summary = await page.locator("#ppsSummary").textContent();
  expect(summary).toContain("large-v3");      // from ASR preset
  expect(summary).toContain("Fast Draft");    // from MT preset label OR underlying value
});

test("Cross-engine warning: alignment_mode=llm-markers + word_timestamps=false renders in MT section", async ({ page }) => {
  await _openPpsModal(page);

  // Speed preset sets word_timestamps=false; Broadcast Quality preset sets alignment_mode=llm-markers
  await page.locator("#ppsAsrPresetButtons button", { hasText: "Speed" }).click();
  await page.locator("#ppsMtPresetButtons button", { hasText: "Broadcast Quality" }).click();

  const crossWarning = page.locator(
    "#ppsMtDangerWarnings .pps-warning-chip",
    { hasText: /word_timestamps/ },
  );
  await expect(crossWarning).toBeVisible({ timeout: 1000 });
});
```

- [ ] **Step 3：跑 test 確認 4 個全 fail**

Run: `cd frontend && npx playwright test test_profile_ui_guidance.spec.js --reporter=line`
Expected: 4 fail（每個都 timeout `waiting for #ppsAsrPresetButtons button` 之類）

- [ ] **Step 4：commit failing tests baseline**

```bash
git add frontend/tests/test_profile_ui_guidance.spec.js
git commit -m "test(v3.16): per-engine preset Playwright spec (failing baseline)"
```

---

## Task 2：HTML — 加 ASR + MT fieldset 容器（保留舊 top section）

**Goal**：additive HTML 改動 — 新 container 同舊 container 並存，UI 暫時兩邊都顯示但功能仲 work。

**Files:**
- Modify: `frontend/index.html`（line 4910-4930 範圍，喺現有 `字幕來源預設` fieldset 後加新 markup）

- [ ] **Step 1：用 Read 確認 line 4910-4932 嘅 anchor 位置**

Run: 讀 `frontend/index.html` line 4910-4932，確認 `<fieldset>...字幕來源預設...</fieldset>` 嘅結束 `</fieldset>` 喺 line 4929 附近。

- [ ] **Step 2：喺 `字幕來源預設` fieldset 結束之後、`</div><!-- /inner padding wrapper -->` 之前，插入兩個新 fieldset**

用 Edit tool，old_string 用 `</fieldset>\n        </div>\n        </div><!-- /inner padding wrapper -->` （留意 indent），new_string 用：

```html
          </fieldset>
          <fieldset style="border:1px solid var(--border);border-radius:6px;padding:10px 14px;">
            <legend style="font-size:11px;color:var(--text-dim);padding:0 6px;">🎙️ ASR 預設</legend>
            <div class="pps-preset-buttons" id="ppsAsrPresetButtons" style="margin:6px 0;"></div>
            <div class="pps-warning-container" id="ppsAsrDangerWarnings"></div>
          </fieldset>
          <fieldset style="border:1px solid var(--border);border-radius:6px;padding:10px 14px;">
            <legend style="font-size:11px;color:var(--text-dim);padding:0 6px;">🌐 MT 預設</legend>
            <div class="pps-preset-buttons" id="ppsMtPresetButtons" style="margin:6px 0;"></div>
            <div class="pps-warning-container" id="ppsMtDangerWarnings"></div>
          </fieldset>
        </div>
        </div><!-- /inner padding wrapper -->
```

- [ ] **Step 3：驗證 HTML 仍 well-formed（grep 開閉 fieldset count match）**

Run: `grep -c '<fieldset' "frontend/index.html"; grep -c '</fieldset>' "frontend/index.html"`
Expected: 兩個數字相等。

- [ ] **Step 4：手動 smoke — 開 backend，open dashboard，click + 新增預設，verify 4 個新 container 喺 DOM 入面（雖然空）**

Run: `cd backend && source venv/bin/activate && python app.py &`（如未開），然後喺 browser DevTools console 跑：
```javascript
['ppsAsrPresetButtons', 'ppsAsrDangerWarnings', 'ppsMtPresetButtons', 'ppsMtDangerWarnings'].forEach(id => console.log(id, !!document.getElementById(id)));
```
Expected：4 個都 `true`。

- [ ] **Step 5：commit**

```bash
git add frontend/index.html
git commit -m "feat(v3.16): add ASR + MT preset fieldset containers in PPS modal"
```

---

## Task 3：JS — 加新 const + state + render/apply/evaluate function（並存）

**Goal**：所有新 JS 加埋舊 JS 一齊，唔 delete 任何嘢。新 function 由 `_initPpsPresetUI` 同 `_scheduleDangerEval` 同步觸發。

**Files:**
- Modify: `frontend/index.html`（line 2507-2710 範圍）

- [ ] **Step 1：喺 [frontend/index.html:2540](frontend/index.html#L2540)（`PROFILE_PRESETS` 結束之後）插入 `ASR_PRESETS` + `MT_PRESETS` 兩個 const**

用 Edit，old_string = `      'custom': {\n        label: 'Custom',\n        description: '自定義（保留現有設定）',\n      },\n    };\n\n    const DANGER_COMBOS = [`，new_string 加埋：

```javascript
      'custom': {
        label: 'Custom',
        description: '自定義（保留現有設定）',
      },
    };

    const ASR_PRESETS = {
      accuracy: {
        label: 'Accuracy',
        description: 'large-v3 + word_timestamps，無 cascade',
        config: { model_size: 'large-v3', condition_on_previous_text: false, word_timestamps: true },
      },
      speed: {
        label: 'Speed',
        description: 'small model + VAD，速度優先',
        config: { model_size: 'small', condition_on_previous_text: false, word_timestamps: false },
      },
      debug: {
        label: 'Debug',
        description: '排查 hallucination，含 initial_prompt 樣本',
        config: { model_size: 'large-v3', condition_on_previous_text: false, word_timestamps: true, initial_prompt: '以下係香港新聞，繁體中文。' },
      },
      custom: { label: 'Custom', description: '保留現有 ASR 設定' },
    };

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

    const DANGER_COMBOS = [
```

- [ ] **Step 2：喺 [frontend/index.html:2573](frontend/index.html#L2573)（`DANGER_COMBOS` 結束之後）插入 `ASR_DANGERS` + `MT_DANGERS`**

用 Edit，old_string = `    ];\n\n    function _ppsEffectiveConfig() {`，new_string 加埋：

```javascript
    ];

    const ASR_DANGERS = [
      {
        id: 'zh-cascade-risk',
        severity: 'high',
        check: (cfg) => cfg.asr?.condition_on_previous_text === true && (cfg.asr?.language === 'zh' || cfg.asr?.language_config_id === 'zh'),
        msg: '⚠ ZH source 上開 condition_on_previous_text：v3.8 揾到 34% segments cascade 重複。建議 false。',
      },
    ];

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

    function _ppsEffectiveConfig() {
```

- [ ] **Step 3：喺 [frontend/index.html:2507](frontend/index.html#L2507)（`let _pendingPresetConfig` 旁邊）加兩個新 state**

用 Edit，old_string = `    let _pendingPresetConfig = null; // { asr: {...}, translation: {...} } or null`，new_string =：

```javascript
    let _pendingPresetConfig = null; // { asr: {...}, translation: {...} } or null  -- DEPRECATED, removed Task 4
    let _pendingAsrPreset = null;    // { config: {...} } | null
    let _pendingMtPreset = null;     // { config: {...} } | null
```

- [ ] **Step 4：喺 `_evaluateDangerCombos` 結束之後（line ~2695 之後）加 5 個新 function**

用 Edit，old_string = `    function _initPpsPresetUI() {`，new_string =：

```javascript
    function _renderAsrPresetButtons() {
      const container = document.getElementById('ppsAsrPresetButtons');
      if (!container) return;
      container.innerHTML = '';
      Object.entries(ASR_PRESETS).forEach(([key, preset]) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'pps-preset-btn';
        btn.dataset.presetKey = key;
        btn.textContent = preset.label;
        btn.title = preset.description || '';
        btn.addEventListener('click', () => _applyAsrPreset(key));
        container.appendChild(btn);
      });
    }

    function _renderMtPresetButtons() {
      const container = document.getElementById('ppsMtPresetButtons');
      if (!container) return;
      container.innerHTML = '';
      Object.entries(MT_PRESETS).forEach(([key, preset]) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'pps-preset-btn';
        btn.dataset.presetKey = key;
        btn.textContent = preset.label;
        btn.title = preset.description || '';
        btn.addEventListener('click', () => _applyMtPreset(key));
        container.appendChild(btn);
      });
    }

    function _applyAsrPreset(key) {
      const preset = ASR_PRESETS[key];
      if (!preset) return;
      document.querySelectorAll('#ppsAsrPresetButtons .pps-preset-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.presetKey === key);
      });
      _pendingAsrPreset = (key === 'custom') ? null : { config: { ...(preset.config || {}) } };
      _updatePpsSummary();
      _scheduleDangerEval();
    }

    function _applyMtPreset(key) {
      const preset = MT_PRESETS[key];
      if (!preset) return;
      document.querySelectorAll('#ppsMtPresetButtons .pps-preset-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.presetKey === key);
      });
      _pendingMtPreset = (key === 'custom') ? null : { config: { ...(preset.config || {}) } };
      _updatePpsSummary();
      _scheduleDangerEval();
    }

    function _renderDangerChips(container, dangers, cfg) {
      if (!container) return;
      container.innerHTML = '';
      dangers.forEach(combo => {
        if (!combo.check(cfg)) return;
        const chip = document.createElement('div');
        chip.className = `pps-warning-chip pps-warning-${combo.severity}`;
        chip.dataset.comboId = combo.id;
        const msgSpan = document.createElement('span');
        msgSpan.textContent = combo.msg;
        const dismiss = document.createElement('button');
        dismiss.type = 'button';
        dismiss.className = 'pps-warning-dismiss';
        dismiss.textContent = '✕';
        dismiss.title = '忽略';
        dismiss.addEventListener('click', (e) => {
          e.stopPropagation();
          chip.remove();
        });
        chip.appendChild(msgSpan);
        chip.appendChild(dismiss);
        container.appendChild(chip);
      });
    }

    function _evaluateAsrDangers() {
      const cfg = _ppsEffectiveConfig();
      _renderDangerChips(document.getElementById('ppsAsrDangerWarnings'), ASR_DANGERS, cfg);
    }

    function _evaluateMtDangers() {
      const cfg = _ppsEffectiveConfig();
      _renderDangerChips(document.getElementById('ppsMtDangerWarnings'), MT_DANGERS, cfg);
    }

    function _initPpsPresetUI() {
```

- [ ] **Step 5：喺 `_initPpsPresetUI` 入面加 render new buttons 嘅 call**

用 Edit，old_string =：

```javascript
    function _initPpsPresetUI() {
      // Idempotent: only render buttons once
      const container = document.getElementById('ppsPresetButtons');
      if (container && container.children.length === 0) {
        _renderPresetButtons();
      }
```

new_string =：

```javascript
    function _initPpsPresetUI() {
      // Idempotent: only render buttons once
      const container = document.getElementById('ppsPresetButtons');
      if (container && container.children.length === 0) {
        _renderPresetButtons();
      }
      const asrContainer = document.getElementById('ppsAsrPresetButtons');
      if (asrContainer && asrContainer.children.length === 0) {
        _renderAsrPresetButtons();
      }
      const mtContainer = document.getElementById('ppsMtPresetButtons');
      if (mtContainer && mtContainer.children.length === 0) {
        _renderMtPresetButtons();
      }
```

- [ ] **Step 6：喺 `_scheduleDangerEval` 入面 chain 新 evaluator**

用 Edit，old_string =：

```javascript
    function _scheduleDangerEval() {
      if (_ppsEvalTimer) clearTimeout(_ppsEvalTimer);
      _ppsEvalTimer = setTimeout(_evaluateDangerCombos, 200);
    }
```

new_string =：

```javascript
    function _scheduleDangerEval() {
      if (_ppsEvalTimer) clearTimeout(_ppsEvalTimer);
      _ppsEvalTimer = setTimeout(() => {
        _evaluateDangerCombos();
        _evaluateAsrDangers();
        _evaluateMtDangers();
      }, 200);
    }
```

- [ ] **Step 7：跑 Playwright，verify Test 1（Accuracy → large-v3 in summary）通過；其餘可能 fail**

Run: `cd frontend && npx playwright test test_profile_ui_guidance.spec.js --reporter=line`
Expected：起碼 Test 1（ASR Accuracy chip 點落 active）一定 pass。Test 2（Fast Draft warning）暫時可能 fail（因為 `_ppsEffectiveConfig` 仲未讀 `_pendingMtPreset`，會 Task 4 修）。Test 3、4 同理。

- [ ] **Step 8：commit**

```bash
git add frontend/index.html
git commit -m "feat(v3.16): per-engine preset constants + render/apply/evaluate functions (additive)"
```

---

## Task 4：JS — 切換 `_ppsEffectiveConfig` + `_updatePpsSummary` + `saveProfileAsPreset` 到新 state；刪舊

**Goal**：將 `_ppsEffectiveConfig` 嘅 merge source 由 `_pendingPresetConfig` 切到 `_pendingAsrPreset` + `_pendingMtPreset`；同時刪走舊 HTML section + 舊 const + 舊 function。完成後 4 個 Playwright test 全綠。

**Files:**
- Modify: `frontend/index.html`（line 2486-2767, 4884-4897）

- [ ] **Step 1：重寫 `_ppsEffectiveConfig`**

用 Edit，old_string =：

```javascript
    function _ppsEffectiveConfig() {
      // Merge pending preset overrides on top of activeProfile (or editing profile)
      const base = _ppsEditingId
        ? (availableProfiles.find(p => p.id === _ppsEditingId) || activeProfile || {})
        : (activeProfile || {});
      if (!_pendingPresetConfig) return base;
      return {
        ...base,
        asr: { ...(base.asr || {}), ...(_pendingPresetConfig.asr || {}) },
        translation: { ...(base.translation || {}), ...(_pendingPresetConfig.translation || {}) },
      };
    }
```

new_string =：

```javascript
    function _ppsEffectiveConfig() {
      // Merge pending ASR + MT preset overrides on top of activeProfile (or editing profile)
      const base = _ppsEditingId
        ? (availableProfiles.find(p => p.id === _ppsEditingId) || activeProfile || {})
        : (activeProfile || {});
      const asrOverride = _pendingAsrPreset?.config || {};
      const mtOverride = _pendingMtPreset?.config || {};
      if (!_pendingAsrPreset && !_pendingMtPreset) return base;
      return {
        ...base,
        asr: { ...(base.asr || {}), ...asrOverride },
        translation: { ...(base.translation || {}), ...mtOverride },
      };
    }
```

- [ ] **Step 2：重寫 `_updatePpsSummary`**

用 Read 攞 line 2637-2660 嘅完整 function，然後用 Edit 替換為：

```javascript
    function _updatePpsSummary() {
      const summaryEl = document.getElementById('ppsSummary');
      if (!summaryEl) return;
      const base = _ppsEditingId
        ? (availableProfiles.find(p => p.id === _ppsEditingId) || activeProfile || {})
        : (activeProfile || {});
      const asr = { ...(base.asr || {}), ...(_pendingAsrPreset?.config || {}) };
      const tr = { ...(base.translation || {}), ...(_pendingMtPreset?.config || {}) };
      const gloss = glossaries.find(g => g.id === tr.glossary_id);
      const font = base.font || {};
      const asrLabel = (() => {
        if (!_pendingAsrPreset) return '—';
        const entry = Object.entries(ASR_PRESETS).find(([, p]) =>
          JSON.stringify(p.config) === JSON.stringify(_pendingAsrPreset.config));
        return entry ? entry[1].label : 'Custom';
      })();
      const mtLabel = (() => {
        if (!_pendingMtPreset) return '—';
        const entry = Object.entries(MT_PRESETS).find(([, p]) =>
          JSON.stringify(p.config) === JSON.stringify(_pendingMtPreset.config));
        return entry ? entry[1].label : 'Custom';
      })();
      summaryEl.innerHTML =
        `ASR 預設    ${escapeHtml(asrLabel)}<br>` +
        `MT  預設    ${escapeHtml(mtLabel)}<br>` +
        `ASR         ${escapeHtml(asr.model_size || '—')} (${escapeHtml(asr.engine || base.asr?.engine || '—')})<br>` +
        `翻譯        ${escapeHtml((tr.engine || '—').replace(/-cloud$/,''))} · batch=${tr.batch_size || '—'} · temp=${tr.temperature ?? '—'} · passes=${tr.translation_passes || 1}<br>` +
        `對齊        ${escapeHtml(tr.alignment_mode || '—')}<br>` +
        `詞彙表      ${gloss ? escapeHtml(gloss.name) : '無'}<br>` +
        `字體        ${escapeHtml(font.family || '—')}`;
    }
```

- [ ] **Step 3：更新 `saveProfileAsPreset` 嘅 deep-merge 邏輯**

用 Edit，old_string =：

```javascript
          // If a preset was selected, merge ASR/translation overrides
          if (_pendingPresetConfig) {
            if (_pendingPresetConfig.asr) {
              patchBody.asr = { ...(editingProf?.asr || activeProfile?.asr || {}), ..._pendingPresetConfig.asr };
            }
            if (_pendingPresetConfig.translation) {
              patchBody.translation = { ...(editingProf?.translation || activeProfile?.translation || {}), ..._pendingPresetConfig.translation };
            }
          }
```

new_string =：

```javascript
          // If presets were selected, merge ASR / MT overrides per-engine
          if (_pendingAsrPreset?.config) {
            patchBody.asr = { ...(editingProf?.asr || activeProfile?.asr || {}), ..._pendingAsrPreset.config };
          }
          if (_pendingMtPreset?.config) {
            patchBody.translation = { ...(editingProf?.translation || activeProfile?.translation || {}), ..._pendingMtPreset.config };
          }
```

- [ ] **Step 4：同一 function 入面 create branch 嘅 deep-merge 都要改**

用 Edit，old_string =：

```javascript
          // If a preset was selected, merge ASR/translation overrides
          if (_pendingPresetConfig) {
            if (_pendingPresetConfig.asr) {
              body.asr = { ...(rest.asr || {}), ..._pendingPresetConfig.asr };
            }
            if (_pendingPresetConfig.translation) {
              body.translation = { ...(rest.translation || {}), ..._pendingPresetConfig.translation };
            }
          }
```

new_string =：

```javascript
          // If presets were selected, merge ASR / MT overrides per-engine
          if (_pendingAsrPreset?.config) {
            body.asr = { ...(rest.asr || {}), ..._pendingAsrPreset.config };
          }
          if (_pendingMtPreset?.config) {
            body.translation = { ...(rest.translation || {}), ..._pendingMtPreset.config };
          }
```

- [ ] **Step 5：reset state — `_openPpsModal` / `closeProfileSaveModal` 入面要清 new state**

用 Read 確認 [frontend/index.html:2486](frontend/index.html#L2486) 同 line 2502，兩處都有 `_pendingPresetConfig = null;`。用 Edit 兩處嘅 `_pendingPresetConfig = null;` 都加多兩行：

```javascript
      _pendingPresetConfig = null;
      _pendingAsrPreset = null;
      _pendingMtPreset = null;
```

- [ ] **Step 6：刪走舊 top HTML preset section + warning container**

用 Edit，old_string =：

```html
        <!-- Preset picker -->
        <div class="pps-preset-section" id="ppsPresetSection">
          <div class="pps-preset-label">🚀 快速預設</div>
          <div class="pps-preset-buttons" id="ppsPresetButtons"></div>
        </div>
        <!-- Danger combo warning chips -->
        <div class="pps-warning-container" id="ppsWarnings"></div>
        <div style="padding: 16px 20px;">
```

new_string =：

```html
        <div style="padding: 16px 20px;">
```

- [ ] **Step 7：刪走舊 `PROFILE_PRESETS` const、`DANGER_COMBOS` const、`_renderPresetButtons` function、`_applyPreset` function、`_evaluateDangerCombos` function、舊 `_pendingPresetConfig` state line（line 2507 嗰行）**

用 Read 確認 line 2507-2706 嘅 boundary，然後用 Edit 各自刪走（每個 const / function 一次 Edit）。

要刪嘅完整目標：
1. `let _pendingPresetConfig = null; // ...DEPRECATED...` 整行
2. `const PROFILE_PRESETS = { ... };`（line 2511-2540 範圍）
3. `const DANGER_COMBOS = [ ... ];`（line 2542-2573 範圍）
4. `function _renderPresetButtons() { ... }`（line 2588-2602 範圍）
5. `function _applyPreset(key) { ... }`（line 2604-2635 範圍）
6. `function _evaluateDangerCombos() { ... }`（line 2668-2695 範圍）

同埋：
- `_initPpsPresetUI` 入面 `const container = document.getElementById('ppsPresetButtons'); if (container && container.children.length === 0) { _renderPresetButtons(); }` 三行
- `_scheduleDangerEval` 入面 `_evaluateDangerCombos();` 嗰行（已被新 evaluator 取代）
- `_openPpsModal` / `closeProfileSaveModal` 入面 `_pendingPresetConfig = null;` 嗰行
- `saveProfileAsPreset` 入面 `if (_pendingPresetConfig) { ... }` block（兩處都已被新邏輯取代）

- [ ] **Step 8：跑 Playwright，verify 4 個全 pass**

Run: `cd frontend && npx playwright test test_profile_ui_guidance.spec.js --reporter=line`
Expected：4 passed。

- [ ] **Step 9：跑全部 frontend test，verify 無 regression**

Run: `cd frontend && npx playwright test --reporter=line --workers=1 --grep-invert 'real_auth'`
Expected：所有 pre-existing test 仍然 pass（特別 `test_subtitle_settings`、`test_user_features`、`test_login_flow`）。

- [ ] **Step 10：手動 browser smoke — 揀 ASR Accuracy + MT Broadcast Quality，save 之後 GET profile**

Run（browser DevTools console）：
```javascript
fetch('/api/profiles', { credentials: 'same-origin' }).then(r => r.json()).then(j => console.log(j.profiles.slice(-1)[0]))
```
Expected：最後嗰個 profile `asr.model_size === 'large-v3'` + `translation.batch_size === 1` + `translation.alignment_mode === 'llm-markers'`。

- [ ] **Step 11：commit**

```bash
git add frontend/index.html
git commit -m "refactor(v3.16): split bundled preset → per-engine, drop legacy code"
```

---

## Task 5：Docs update — CLAUDE.md v3.16 entry

**Goal**：將 v3.16 嘅功能寫入 CLAUDE.md「Completed Features」section。

**Files:**
- Modify: `CLAUDE.md`（喺 `### v3.15` 之前加 `### v3.16` block）

- [ ] **Step 1：用 Read 確認 CLAUDE.md `### v3.15` 嘅 line**

Run: 讀 `CLAUDE.md`，揾 `### v3.15 — Multilingual Glossary Refactor` 嘅 line（喺 Completed Features section 開始位置）。

- [ ] **Step 2：喺 `### v3.15` 之前插入 v3.16 entry**

用 Edit，old_string = `### v3.15 — Multilingual Glossary Refactor`，new_string =：

```markdown
### v3.16 — Per-Engine Preset + Danger Warning Refactor
- **目標**：將 Profile Save modal (`#ppsOverlay`) 由 pipeline-level bundled preset / danger warning 改為 per-engine（ASR + MT 各自獨立）。Spec: [docs/superpowers/specs/2026-05-14-per-engine-preset-design.md](docs/superpowers/specs/2026-05-14-per-engine-preset-design.md)。Plan: [docs/superpowers/plans/2026-05-14-per-engine-preset-plan.md](docs/superpowers/plans/2026-05-14-per-engine-preset-plan.md)。
- **HTML 改動**：刪走 `#ppsPresetSection` + `#ppsWarnings`（modal 頂部 bundled 容器），加兩個新 fieldset `🎙️ ASR 預設` (`#ppsAsrPresetButtons` + `#ppsAsrDangerWarnings`) + `🌐 MT 預設` (`#ppsMtPresetButtons` + `#ppsMtDangerWarnings`)，住喺現有「字幕來源預設」fieldset 後面。
- **JS data 拆分**：
  - `PROFILE_PRESETS` (5 個 bundled) → `ASR_PRESETS` (4 個：accuracy / speed / debug / custom) + `MT_PRESETS` (4 個：broadcast-quality / fast-draft / literal-ref / custom)
  - `DANGER_COMBOS` (5 個混合) → `ASR_DANGERS` (1 個：zh-cascade-risk) + `MT_DANGERS` (5 個：4 舊 MT + 1 新 cross-engine `word-timestamps-needed-for-alignment`)
- **JS state 拆分**：`_pendingPresetConfig` → `_pendingAsrPreset` + `_pendingMtPreset`，兩個獨立 state 互不覆蓋，支援用戶混搭。
- **Cross-engine warning 擺位**：`word-timestamps-needed-for-alignment` 觸發 param (`alignment_mode=llm-markers`) 喺 MT 度，所以警告 chip render 喺 `#ppsMtDangerWarnings`；msg 文字明確指返用戶去 ASR section 開啟 word_timestamps。
- **Save flow**：`saveProfileAsPreset` 嘅 deep-merge 兩處（PATCH branch + POST branch）都由讀單一 `_pendingPresetConfig` 切到分別讀 `_pendingAsrPreset.config` + `_pendingMtPreset.config`，未揀 preset 嘅 engine 唔會 emit 對應 block，等用戶可以淨係改 ASR 而保留 MT 原狀（或反過來）。
- **Backend / API contract**：完全不變。Profile JSON schema 不變。無 migration。
- **Tests**：`frontend/tests/test_profile_ui_guidance.spec.js` 由 2 個 test 變 4 個 — 2 個更新 selector（`#ppsAsrPresetButtons` + `#ppsMtDangerWarnings`），新加「mix-and-match」（ASR Accuracy + MT Fast Draft 同時 active）+「cross-engine warning fires」（Speed + Broadcast Quality 觸發 `word-timestamps-needed-for-alignment`）。

### v3.15 — Multilingual Glossary Refactor
```

- [ ] **Step 3：commit**

```bash
git add CLAUDE.md
git commit -m "docs(v3.16): CLAUDE.md entry for per-engine preset refactor"
```

---

## Self-Review

**1. Spec coverage**：
- ✅ ASR_PRESETS / MT_PRESETS 定義（Task 3 Step 1）
- ✅ ASR_DANGERS / MT_DANGERS 定義（Task 3 Step 2）
- ✅ State 拆 `_pendingAsrPreset` + `_pendingMtPreset`（Task 3 Step 3）
- ✅ UI 佈局：兩個新 fieldset 後加（Task 2）+ 舊 section 刪走（Task 4 Step 6）
- ✅ Function rename：render / apply / evaluate 三組（Task 3 Step 4）
- ✅ `_ppsEffectiveConfig` 讀新 state（Task 4 Step 1）
- ✅ `_updatePpsSummary` 顯示 ASR + MT label（Task 4 Step 2）
- ✅ `saveProfileAsPreset` 兩 branch deep-merge 更新（Task 4 Steps 3-4）
- ✅ Cross-engine `word-timestamps-needed-for-alignment` 擺 MT section（Task 3 Step 2，warning id 已包含）
- ✅ Test 1+2 selector update + Test 3 mix-match + Test 4 cross-engine warning（Task 1 Step 2）
- ✅ Backend / API 不變（無 task 涉及 backend file）
- ✅ Migration notes：無 data migration（spec 已 cover，plan 唔需要再寫）

**2. Placeholder scan**：無 TBD / TODO / 「similar to」 / 「add error handling」。每個 step 有完整 code block 或具體命令。

**3. Type consistency**：
- `_pendingAsrPreset` / `_pendingMtPreset` shape：`{ config: {...} } | null` — Task 3 Step 3 定義，Task 3 Steps 4 創建（`_pendingAsrPreset = { config: { ... } }`），Task 4 Steps 1-4 消費（`_pendingAsrPreset?.config`）— 一致。
- `ASR_PRESETS[key]` shape：`{ label, description, config }` — Task 3 Step 1 定義，Task 3 Step 4 `_applyAsrPreset` 用 `preset.config` 一致。
- Container ID：`ppsAsrPresetButtons` / `ppsAsrDangerWarnings` / `ppsMtPresetButtons` / `ppsMtDangerWarnings` — HTML（Task 2 Step 2）同 JS（Task 3 Steps 4-6）同 test（Task 1 Step 2）三邊統一。
- `escapeHtml` helper：`_updatePpsSummary` 用，假設已存在於 index.html scope（line 2660 附近舊 summary 已用）— 沿用 not new dependency。

**Plan ready for execution.**
