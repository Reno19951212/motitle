# Pipeline Strip 精簡 + 步驟 popover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Topbar pipeline strip 永遠 compact（preset 選擇器 + 「步驟」toggle）；完整 steps 搬入闊度唔受限嘅 popover，消除 MacBook 14" 上 steps 壓縮重疊嘅 garble。

**Architecture:** 純前端（`frontend/index.html`）。兩個 renderer（`renderPipelineStrip` Profile / `renderPipelineStripV6`）將「sep + steps」由 inline 包入 `.pipeline-steps-popover`，前面加 toggle 按鈕；steps 內部 markup + 互動完全不變。CSS 加 popover/toggle/compact，JS 加 toggle + outside-click。Backend 零改。

**Tech Stack:** Vanilla HTML/CSS/JS、Playwright。後端喺 :5001。

**Spec:** [docs/superpowers/specs/2026-05-30-pipeline-strip-popover-design.md](../specs/2026-05-30-pipeline-strip-popover-design.md)

---

## File Structure
| 檔案 | 動作 |
|---|---|
| `frontend/index.html` | **Modify** — CSS（popover/toggle/compact）+ `renderPipelineStripV6` + `renderPipelineStrip` wrap + `togglePipelineSteps` JS + outside-click |
| `frontend/tests/test_pipeline_strip_popover.spec.js` | **Create** — Playwright 兩個 mode |

---

## Task 1: CSS + toggle JS

**Files:** Modify `frontend/index.html`

- [ ] **Step 1: 加 CSS**

喺 `.pipeline-strip { … }` rule（約 line 251）附近加（緊接 `.pipeline-strip .step { position: relative; }` 之後）：

```css
    .pipeline-strip { position: relative; }
    .pipeline-strip .pipeline-preset .pp-v {
      max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .pipeline-steps-toggle {
      display: inline-flex; align-items: center; gap: 4px;
      background: none; border: 0; cursor: pointer;
      padding: 6px 10px; border-radius: 8px; color: var(--text-mid);
    }
    .pipeline-steps-toggle:hover { background: var(--surface-3); color: var(--text); }
    .pipeline-steps-toggle .k {
      font-weight: 700; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
    }
    .pipeline-steps-popover {
      display: none;
      position: absolute; top: 100%; left: 0; margin-top: 6px;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; box-shadow: 0 16px 40px rgba(0,0,0,0.55);
      padding: 4px 6px; z-index: 90;
      align-items: center; gap: 2px;
      width: max-content; max-width: 90vw; overflow: visible;
    }
    .pipeline-steps-popover.open { display: flex; }
```

- [ ] **Step 2: 加 toggle JS + outside-click**

喺 `renderPipelineStrip` function 之前（或附近 module scope）加：

```javascript
    function togglePipelineSteps(btn) {
      const pop = btn.parentElement.querySelector('.pipeline-steps-popover');
      if (!pop) return;
      pop.classList.toggle('open');
    }
    // 撳 popover / toggle 以外收埋
    document.addEventListener('click', (e) => {
      document.querySelectorAll('.pipeline-steps-popover.open').forEach(pop => {
        const wrap = pop.parentElement;  // .pipeline-strip
        const toggle = wrap.querySelector('.pipeline-steps-toggle');
        if (!pop.contains(e.target) && !(toggle && toggle.contains(e.target))) {
          pop.classList.remove('open');
        }
      });
    });
```

- [ ] **Step 3: 確認語法（開頁面無 console error）**

開 `http://localhost:5001/`（已登入），開 DevTools console 確認無 JS error。（或 Playwright 喺 Task 3 一齊驗。）

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/index.html
git commit -m "feat(ui): pipeline-strip popover CSS + toggle scaffolding"
```

---

## Task 2: 兩個 renderer wrap steps 入 popover + 加 toggle

**Files:** Modify `frontend/index.html`（`renderPipelineStripV6` ~2381-2410；`renderPipelineStrip` Profile 嘅 `el.innerHTML`）

- [ ] **Step 1: 改 `renderPipelineStripV6` 嘅 `el.innerHTML`**

現有 template（約 line 2381-2410）結構：`<div class="pipeline-preset-wrap">…</div>` + `<span class="sep"></span>` + steps（vad/qwen3-ctx/output/refiner + arrows）。

改動：將 `<span class="sep"></span>` 換成 toggle 按鈕，並將其後所有 steps 包入 `.pipeline-steps-popover`：

```javascript
      el.innerHTML = `
        <div class="pipeline-preset-wrap">
          ... (preset button + presetMenuHtml — 完全不變) ...
        </div>
        <button class="pipeline-steps-toggle" onclick="togglePipelineSteps(this)" title="顯示 / 隱藏 pipeline 步驟">
          <span class="k">步驟</span>
          <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6l4 4 4-4"/></svg>
        </button>
        <div class="pipeline-steps-popover">
          <div class="step" data-step="vad" tabindex="0"> ... 不變 ... </div>
          <span class="arrow">→</span>
          <div class="step" data-step="qwen3-ctx" ... onclick="openPromptPanelInline('qwen3_context')" ...> ... 不變 ... </div>
          <span class="arrow">→</span>
          <div class="step" data-step="output" ...> ... 不變 ... </div>
          <span class="arrow">→</span>
          <div class="step" data-step="refiner" ... onclick="openPromptPanelInline('refiner_prompt')" ...> ... 不變 ... </div>
        </div>`;
```
即：(a) 刪 `<span class="sep"></span>`；(b) 喺 preset-wrap 後加 toggle button；(c) 用 `<div class="pipeline-steps-popover">…</div>` 包住原本 4 個 step + 3 個 arrow（**內容逐字保留**）。

- [ ] **Step 2: 改 `renderPipelineStrip`（Profile）嘅 `el.innerHTML`**

搵到 Profile 分支嘅 `el.innerHTML = \`...\``（喺 line ~2513 之後，preset-wrap + sep + ASR/MT/輸出/術語 steps）。套用**同樣** transformation：
- preset-wrap 不變。
- 刪 preset-wrap 後嘅 `<span class="sep"></span>`。
- 加 `<button class="pipeline-steps-toggle" onclick="togglePipelineSteps(this)"><span class="k">步驟</span><svg.../></button>`（同上）。
- 將其後所有 ASR/MT/輸出/術語 steps + arrows（連各自 hover step-menu markup）**逐字**包入 `<div class="pipeline-steps-popover"> … </div>`。

- [ ] **Step 3: 確認兩個 mode 無語法錯 + render 正常**

開 `http://localhost:5001/`，切 Profile / V6（preset 選擇器），確認 topbar 只見 preset + 「步驟 ▾」，撳「步驟」彈出 popover 見到完整 steps。Console 無 error。

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/index.html
git commit -m "feat(ui): move pipeline steps into popover (both Profile + V6 renderers)"
```

---

## Task 3: Playwright 驗證（兩個 mode @ 1512×982）

**Files:** Create `frontend/tests/test_pipeline_strip_popover.spec.js`

- [ ] **Step 1: 寫測試**

建立 `frontend/tests/test_pipeline_strip_popover.spec.js`：

```javascript
const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'AdminPass1!';
const V6_PIPE = '4696bbaa-b988-49bd-859c-e742cb365634';

test.use({ storageState: undefined });

test.describe('pipeline strip popover', () => {
  test.beforeEach(async ({ page }) => {
    const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
    if (!r.ok()) throw new Error('login ' + r.status());
    await page.setViewportSize({ width: 1512, height: 982 });
  });

  async function gotoMode(page, kind, id) {
    await page.request.post(BASE + '/api/active', { data: { kind, id } });
    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
  }

  for (const [label, kind, id] of [['profile', 'profile', 'dev-default'], ['v6', 'pipeline_v6', V6_PIPE]]) {
    test(`${label}: strip compact, popover hides then expands cleanly`, async ({ page }) => {
      await gotoMode(page, kind, id);

      // strip never overflows
      const overflow = await page.evaluate(() => {
        const s = document.querySelector('.pipeline-strip');
        return { scrollW: s.scrollWidth, clientW: s.clientWidth };
      });
      expect(overflow.scrollW).toBeLessThanOrEqual(overflow.clientW + 2);

      // popover hidden by default
      await expect(page.locator('.pipeline-steps-popover')).toBeHidden();

      // open it
      await page.locator('.pipeline-steps-toggle').click();
      await expect(page.locator('.pipeline-steps-popover')).toBeVisible();

      // steps inside not overlapping: each .step .v not clipped (scrollW<=clientW+2)
      const stepOk = await page.evaluate(() => {
        const vs = [...document.querySelectorAll('.pipeline-steps-popover .step .v')];
        return vs.every(v => v.scrollWidth <= v.clientWidth + 2);
      });
      expect(stepOk).toBe(true);

      // adjacent steps don't overlap horizontally
      const noOverlap = await page.evaluate(() => {
        const steps = [...document.querySelectorAll('.pipeline-steps-popover .step')];
        for (let i = 1; i < steps.length; i++) {
          const a = steps[i - 1].getBoundingClientRect();
          const b = steps[i].getBoundingClientRect();
          if (b.left < a.right - 2) return false;
        }
        return true;
      });
      expect(noOverlap).toBe(true);

      // click outside closes
      await page.mouse.click(5, 400);
      await expect(page.locator('.pipeline-steps-popover')).toBeHidden();
    });
  }
});
```

- [ ] **Step 2: 跑（一個 mode 一次，避 login rate limit）**

```bash
cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_pipeline_strip_popover.spec.js --reporter=line
```
Expected: 2 passed。若 `.pipeline-strip` scrollWidth 仍 > clientWidth，表示 toggle/preset 本身都逼爆 — 檢查 preset `.pp-v` cap 有冇生效。若 login 429，等 60s 再跑。

- [ ] **Step 3: 截圖人手確認（Opus 判讀）**

跑一個小 node 截圖（reuse `frontend/diag_topbar.mjs` pattern，撳開 popover 後截 topbar + popover），controller 肉眼確認兩個 mode：strip compact、popover 內 steps 清晰唔重疊。

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/tests/test_pipeline_strip_popover.spec.js
git commit -m "test(ui): pipeline-strip popover — both modes compact + clean expand"
```

---

## Task 4: 清理 + 文檔

- [ ] **Step 1: 刪診斷 artifact**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
rm -f diag_topbar.mjs diag_topbar_profile.png diag_topbar_v6.png
```

- [ ] **Step 2: CLAUDE.md 加 entry**（「Completed Features」最上）

```markdown
### 主介面 Pipeline Strip 顯示修復 — 步驟 popover（2026-05-30）
- **問題**：MacBook 14"（1512px）topbar pipeline strip 喺 Profile + V6 兩個 mode 嘅 steps 被壓縮重疊成 garble（search+health-cluster+userChip+preset 食晒寬度，strip overflowing）。
- **修復**：strip 改為永遠 compact（preset 選擇器 + 「步驟 ▾」toggle）；完整 steps 搬入 `.pipeline-steps-popover`（`width:max-content; overflow:visible`，唔受 topbar grid 限制）。撳 toggle 彈出，steps 有自然全寬唔再重疊；每個 step 互動（preset 切換 / V6 qwen3·refiner inline panel / Profile ASR·MT 選擇）100% 保留。純前端（`index.html` CSS + 兩個 renderer + toggle JS）。
- **測試**：Playwright `test_pipeline_strip_popover.spec.js` 兩個 mode @1512×982（strip 唔 overflow、popover 開合、steps 唔重疊）。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-pipeline-strip-popover-design.md) / [plan](docs/superpowers/plans/2026-05-30-pipeline-strip-popover-plan.md)。
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add CLAUDE.md && git commit -m "docs: record pipeline-strip popover fix"
```

---

## 驗收標準（對應 spec §8）
1. ✅ 兩個 mode @1512 strip 唔 overflow、無 garble（Task 3 Playwright + 截圖）。
2. ✅ popover 彈出 steps 完整唔重疊（Task 3）。
3. ✅ 互動保留（preset 切換 / V6 inline panel / Profile 選擇 — Task 2 Step 3 + Task 3）。
4. ✅ 撳出面收埋；mobile 不變。

## Self-Review notes
- **Spec coverage**：§4.1 transformation→Task 2；§4.2 CSS→Task 1 Step 1；§4.3 toggle JS→Task 1 Step 2；§7 測試→Task 3；§4.4 行為→Task 2 Step 3 + Task 3。全覆蓋。
- **Consistency**：class 名 `.pipeline-steps-toggle` / `.pipeline-steps-popover` / fn `togglePipelineSteps` 喺 CSS / JS / 兩個 renderer / tests 一致。
- **No placeholders**：CSS / JS / test 全 code；renderer wrap 因 steps markup 龐大故描述 transformation（內容逐字保留）+ 指明 anchor，非 placeholder。
