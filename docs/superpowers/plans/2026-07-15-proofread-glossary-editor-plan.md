# 校對頁詞彙表面板 — 搜尋 + 條目編輯 modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 校對頁面詞彙表面板加返（1）條目搜尋（原文/譯文/近音）（2）撳 ✎ / +新增 開一個共用彈出編輯器，可改原文/譯文 + 近音寫法（`source_variants`）+ 別名（`target_aliases`）—— 對齊 Glossary.html Plan B 已有嘅能力。

**Architecture:** 純前端，零後端改動（`PATCH`/`POST /entries` 已收 `source_variants`+`target_aliases`）。全部喺 `frontend/proofread.html`：新增一個 `#geOverlay` 彈出編輯器（編輯+新增共用），改寫 `renderGlossaryTable`（搜尋框 + filter + badge + ✎ 路由到 modal），移走窄面板嘅 cramped inline 編輯邏輯。

**Tech Stack:** Vanilla JS（無 build step，classic script 共享 page globals）、Playwright（E2E）。

**Spec:** [docs/superpowers/specs/2026-07-15-proofread-glossary-editor-design.md](../specs/2026-07-15-proofread-glossary-editor-design.md)

## Global Constraints

- **零後端改動**、無新 endpoint。只改 `frontend/proofread.html`。
- **XSS**：所有插值（source / target / 每個 variant / alias / 詞彙表名 / 搜尋字串）一律過 `escapeHtml`；chip × 移除掣用 `data-*`（整數 idx + kind）+ event delegation，**唔用 inline onclick 帶字串值**（Plan B review 揪過嘅 class）。
- **共用 page globals**（proofread.html script 已有）：`API_BASE`、`fileId`、`glossaryId`、`glossaryEntries`、`escapeHtml`、`showToast`、`loadGlossaryEntries`。
- **chip 批次保存**：modal 內 chip 改動只改本地 array，**唔逐個 PATCH**；一次過喺「儲存」送 `{source, target, source_variants, target_aliases}`（比 Glossary.html 逐 chip PATCH 更簡單、無 race）。
- **authz**：共享表非管理員 → 後端回 `{"error":"forbidden"}` 403，儲存捕捉 → toast「你冇權改共享詞彙表（需管理員）」。
- **前端無 build**：改完 hard-refresh 即生效。驗證用 static-verify（grep 接線 + escapeHtml）+ Task 3 Playwright E2E（跑 :5011）。
- **測試 server**：branch code 已行喺 `http://127.0.0.1:5011`（admin `Reno` / `Reno12345`）。E2E 用丟棄式測試詞彙表寫入，唔郁真賽馬表。

---

### Task 1: 條目編輯 modal（DOM + CSS + JS）+ wire +新增

**Files:**
- Modify: `frontend/proofread.html`（modal DOM 插喺 `#grOverlay` modal 之後 ~3912；CSS 加喺 `.gr-*` 附近；JS 加喺 glossary 面板函數區 ~1954；`+新增` 掣 :1073 + :1079）

**Interfaces:**
- Consumes: `glossaryId`, `glossaryEntries`, `loadGlossaryEntries(id)`, `escapeHtml`, `showToast`, `API_BASE`.
- Produces:
  - `openEntryModal(eid: string|null)` — `eid` 有 → 編輯（預填）；`null` → 新增（空白）。全域（onclick 用）。
  - module state：`_geEditId`, `_geVariants: string[]`, `_geAliases: string[]`。

- [ ] **Step 1: 加 modal DOM**（插喺 `#grOverlay` 嘅 `</div>` 之後，約 proofread.html:3912）

```html
<!-- 詞彙表條目編輯 modal (output_lang; 編輯 + 新增共用) -->
<div class="ge-overlay" id="geOverlay">
  <div class="ge-modal">
    <div class="ge-header">
      <span id="geTitle">編輯詞條</span>
      <button class="ge-close" id="geCloseBtn" aria-label="關閉">&times;</button>
    </div>
    <div class="ge-body">
      <label class="ge-label">原文</label>
      <input class="ge-input" id="geSource" placeholder="原文">
      <label class="ge-label">譯文</label>
      <input class="ge-input" id="geTarget" placeholder="譯文">
      <label class="ge-label">近音寫法（原文別名）</label>
      <div class="ge-chips" id="geVariants"></div>
      <label class="ge-label">別名（譯文）</label>
      <div class="ge-chips" id="geAliases"></div>
    </div>
    <div class="ge-footer">
      <button class="btn btn-ghost" id="geCancelBtn">取消</button>
      <button class="btn btn-primary" id="geSaveBtn">儲存</button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: 加 CSS**（喺 `.gr-*` / `.ae-*` overlay CSS 附近；用檔案現有 CSS 變數）

```css
.ge-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.55);
  z-index: 60; align-items: center; justify-content: center; }
.ge-overlay.open { display: flex; }
.ge-modal { width: 360px; max-width: 92vw; max-height: 86vh; overflow: auto;
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  display: flex; flex-direction: column; }
.ge-header { display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; border-bottom: 1px solid var(--border); font-weight: 700; }
.ge-close { background: none; border: none; color: var(--text-dim); font-size: 20px; cursor: pointer; }
.ge-body { padding: 12px 14px; display: flex; flex-direction: column; gap: 4px; }
.ge-label { font-size: 11px; color: var(--text-dim); margin-top: 8px; }
.ge-input { width: 100%; box-sizing: border-box; background: var(--surface-2);
  border: 1px solid var(--border); border-radius: 4px; color: var(--text);
  font-size: 13px; padding: 5px 8px; }
.ge-chips { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.ge-chip { display: inline-flex; align-items: center; gap: 3px; background: var(--surface-2);
  border: 1px solid var(--border); border-radius: 12px; padding: 2px 8px; font-size: 12px; }
.ge-chip button { background: none; border: none; color: var(--text-dim); cursor: pointer;
  font-size: 13px; line-height: 1; padding: 0; }
.ge-chip-add { background: none; border: 1px dashed var(--border); border-radius: 12px;
  color: var(--accent); cursor: pointer; font-size: 12px; padding: 2px 8px; }
.ge-footer { display: flex; justify-content: flex-end; gap: 8px;
  padding: 10px 14px; border-top: 1px solid var(--border); }
.gl-td-alt { font-size: 10px; color: var(--text-dim); margin-left: 4px; }
```

- [ ] **Step 3: 加 JS**（喺 `addGlossaryEntry` 附近，約 proofread.html:1954，之後 Task 2 會刪走舊 inline 函數）

```javascript
  // ── 詞彙表條目編輯 modal（編輯 + 新增共用；chip 批次保存）─────
  let _geEditId = null;
  let _geVariants = [];
  let _geAliases = [];

  function openEntryModal(eid) {
    if (!glossaryId) { showToast('請先點選詞彙表名稱', 'error'); return; }
    _geEditId = eid || null;
    const entry = eid ? glossaryEntries.find(e => e.id === eid) : null;
    document.getElementById('geTitle').textContent = eid ? '編輯詞條' : '新增詞條';
    document.getElementById('geSource').value = entry ? (entry.source || '') : '';
    document.getElementById('geTarget').value = entry ? (entry.target || '') : '';
    _geVariants = entry && Array.isArray(entry.source_variants) ? entry.source_variants.slice() : [];
    _geAliases = entry && Array.isArray(entry.target_aliases) ? entry.target_aliases.slice() : [];
    _geRenderChips();
    document.getElementById('geOverlay').classList.add('open');
    document.getElementById('geSource').focus();
  }
  window.openEntryModal = openEntryModal;

  function _geRenderChips() {
    document.getElementById('geVariants').innerHTML =
      _geVariants.map((v, i) => `<span class="ge-chip">${escapeHtml(v)}<button data-kind="v" data-idx="${i}" title="移除">×</button></span>`).join('')
      + `<button class="ge-chip-add" data-kind="v" data-add="1">+ 加入</button>`;
    document.getElementById('geAliases').innerHTML =
      _geAliases.map((a, i) => `<span class="ge-chip">${escapeHtml(a)}<button data-kind="a" data-idx="${i}" title="移除">×</button></span>`).join('')
      + `<button class="ge-chip-add" data-kind="a" data-add="1">+ 加入</button>`;
  }

  function _geChipClick(e) {
    const btn = e.target.closest('button');
    if (!btn) return;
    const kind = btn.dataset.kind;
    const arr = kind === 'v' ? _geVariants : _geAliases;
    if (btn.dataset.add) {
      const v = prompt(kind === 'v' ? '加入近音寫法（原文聽錯/拼錯形式）：' : '加入別名（譯文寫法）：');
      if (v && v.trim() && !arr.includes(v.trim())) arr.push(v.trim());
    } else if (btn.dataset.idx != null) {
      arr.splice(parseInt(btn.dataset.idx, 10), 1);
    }
    _geRenderChips();
  }

  async function _geSave() {
    const source = document.getElementById('geSource').value.trim();
    const target = document.getElementById('geTarget').value.trim();
    if (!source || !target) { showToast('原文同譯文不能為空', 'error'); return; }
    const saveBtn = document.getElementById('geSaveBtn');
    saveBtn.disabled = true;
    try {
      const url = _geEditId
        ? `${API_BASE}/api/glossaries/${glossaryId}/entries/${_geEditId}`
        : `${API_BASE}/api/glossaries/${glossaryId}/entries`;
      const r = await fetch(url, {
        method: _geEditId ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ source, target,
          source_variants: _geVariants, target_aliases: _geAliases }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.error === 'forbidden'
        ? '你冇權改共享詞彙表（需管理員）' : (body.error || `HTTP ${r.status}`));
      document.getElementById('geOverlay').classList.remove('open');
      await loadGlossaryEntries(glossaryId);   // 重載 + re-render（保留搜尋 filter）
      showToast('已儲存到詞彙表', 'success');
    } catch (e) {
      showToast(`儲存失敗: ${e.message}`, 'error');
    } finally {
      saveBtn.disabled = false;
    }
  }

  function _geClose() { document.getElementById('geOverlay').classList.remove('open'); }

  // 一次性 wire（page load）
  (function _geWire() {
    const ov = document.getElementById('geOverlay');
    if (!ov) return;
    document.getElementById('geCloseBtn').addEventListener('click', _geClose);
    document.getElementById('geCancelBtn').addEventListener('click', _geClose);
    document.getElementById('geSaveBtn').addEventListener('click', _geSave);
    document.getElementById('geVariants').addEventListener('click', _geChipClick);
    document.getElementById('geAliases').addEventListener('click', _geChipClick);
    ov.addEventListener('click', e => { if (e.target === ov) _geClose(); });
    ['geSource', 'geTarget'].forEach(id => document.getElementById(id).addEventListener('keydown', e => {
      if (e.key === 'Enter') _geSave();
      else if (e.key === 'Escape') _geClose();
    }));
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && ov.classList.contains('open')) _geClose();
    });
  })();
```

- [ ] **Step 4: wire 「+新增」掣到 modal**

`frontend/proofread.html:1073` 同 `:1079` 兩個 `+新增` 掣，`onclick="addGlossaryEntry()"` → `onclick="openEntryModal(null)"`。

- [ ] **Step 5: static-verify + import smoke**

Run:
```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend" && \
grep -c "geOverlay\|openEntryModal\|_geSave\|_geChipClick" proofread.html && \
grep -n 'onclick="openEntryModal(null)"' proofread.html
```
Expected: modal 元素/函數 grep >0；兩個 `+新增` 掣已改。
確認每個 chip 插值都經 `escapeHtml`（睇 `_geRenderChips`），chip 掣用 `data-*` delegation（無 inline onclick 帶字串）。

- [ ] **Step 6: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(proofread): 詞彙表條目編輯 modal（原文/譯文 + 近音寫法 + 別名，編輯+新增共用）"
```

---

### Task 2: 條目表搜尋 + badge + ✎ 路由 modal + 清走舊 inline 編輯

**Files:**
- Modify: `frontend/proofread.html`（`renderGlossaryTable` :1870-1890；刪 `startEditEntry` :1892-1913 / `saveEditEntry` :1915-1937 / `addGlossaryEntry` :1954-1985 / `cancelNewEntry` :1987-1990 / `saveNewEntry` :1992-2018）

**Interfaces:**
- Consumes: `glossaryEntries`, `escapeHtml`, `openEntryModal`（Task 1）, `deleteGlossaryEntry`（保留）。
- Produces: `_glEntryQuery: string`（模組 state）；`renderGlossaryTable()` 重寫；`_glRenderRows()`。

- [ ] **Step 1: 重寫 renderGlossaryTable**（換走 :1870-1890 整個函數）

```javascript
  let _glEntryQuery = '';

  function _glEntryMatches(e, q) {
    if (!q) return true;
    const hay = [e.source || '', e.target || '',
      ...(Array.isArray(e.source_variants) ? e.source_variants : []),
      ...(Array.isArray(e.target_aliases) ? e.target_aliases : [])
    ].join(' ').toLowerCase();
    return hay.includes(q);
  }

  function _glRenderRows() {
    const tbody = document.getElementById('glEntryRows');
    const emptyEl = document.getElementById('glEntryEmpty');
    if (!tbody) return;
    const q = _glEntryQuery.trim().toLowerCase();
    const filtered = glossaryEntries.filter(e => _glEntryMatches(e, q));
    tbody.innerHTML = filtered.map(e => {
      const nv = Array.isArray(e.source_variants) ? e.source_variants.length : 0;
      const badge = nv ? `<span class="gl-td-alt">·近${nv}</span>` : '';
      return `<tr id="grow-${escapeHtml(e.id)}">
        <td>${escapeHtml(e.source)}${badge}</td>
        <td>${escapeHtml(e.target)}</td>
        <td style="text-align:center;white-space:nowrap;">
          <button class="btn btn-ghost btn-sm" onclick="openEntryModal('${escapeHtml(e.id)}')" title="編輯">✎</button>
          <button class="btn btn-ghost btn-sm" onclick="deleteGlossaryEntry('${escapeHtml(e.id)}')" title="刪除">🗑</button>
        </td>
      </tr>`;
    }).join('');
    emptyEl.innerHTML = (!filtered.length && q)
      ? '<div class="rv-b-rail-empty" style="padding:6px;">搜尋無結果</div>' : '';
  }

  function renderGlossaryTable() {
    const body = document.getElementById('glossaryBody');
    if (!glossaryEntries.length) {
      body.innerHTML = '<div class="rv-b-rail-empty">暫無條目</div>';
      return;
    }
    body.innerHTML = `
      <input class="rv-b-glossary-input" id="glEntrySearch" placeholder="🔍 搜尋原文/譯文/近音…"
             style="margin-bottom:4px;" value="${escapeHtml(_glEntryQuery)}">
      <table class="rv-b-glossary-table">
        <thead><tr><th>原文</th><th>譯文</th><th></th></tr></thead>
        <tbody id="glEntryRows"></tbody>
      </table>
      <div id="glEntryEmpty"></div>`;
    const search = document.getElementById('glEntrySearch');
    search.addEventListener('input', () => { _glEntryQuery = search.value; _glRenderRows(); });
    _glRenderRows();
  }
```

> `id="grow-..."` 保留（`deleteGlossaryEntry` 唔靠佢，但無害）。`e.id` 係 uuid（`escapeHtml` 安全）。搜尋只 re-render `#glEntryRows` tbody，輸入框保持 focus。

- [ ] **Step 2: 刪走舊 inline 編輯函數**

移除 `startEditEntry`（:1892-1913）、`saveEditEntry`（:1915-1937）、`addGlossaryEntry`（:1954-1985）、`cancelNewEntry`（:1987-1990）、`saveNewEntry`（:1992-2018）。**先 grep 確認冇其他引用**：

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend" && \
grep -n "startEditEntry\|saveEditEntry\|addGlossaryEntry\|cancelNewEntry\|saveNewEntry" proofread.html
```
Expected（刪除後）：**0 hit**（所有引用已由 Task 1 的 `openEntryModal` + Step 1 的 ✎ 取代）。若仲有 hit，係漏改嘅 onclick — 補改成 `openEntryModal`。

- [ ] **Step 3: static-verify**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend" && \
grep -c "glEntrySearch\|_glRenderRows\|gl-td-alt\|openEntryModal" proofread.html && \
grep -n "startEditEntry\|saveNewEntry" proofread.html || echo "✓ 舊 inline 函數已清"
```
Expected: 搜尋/badge/modal 接線 grep >0；舊函數 0 hit。

- [ ] **Step 4: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(proofread): 詞彙表條目搜尋 + 近音 badge + ✎ 路由 modal（清走 cramped inline 編輯）"
```

---

### Task 3: Playwright E2E + 文檔

**Files:**
- Create: `frontend/tests/test_proofread_glossary_editor.py`（Playwright；或加落 scratchpad E2E — 見 Step 1）
- Modify: `CLAUDE.md`（proofread 段補一句）

**Interfaces:**
- Consumes: 跑緊嘅 :5011（branch code，admin `Reno`/`Reno12345`）。

- [ ] **Step 1: 寫 E2E script**

```python
# frontend/tests/test_proofread_glossary_editor.py
# 跑法：backend/venv/bin/python frontend/tests/test_proofread_glossary_editor.py
# 前置：branch code 行喺 :5011。
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5011"
results = []
def rec(n, ok, d=""): results.append(ok); print(("PASS" if ok else "FAIL"), n, "—", d)

with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    ctx = br.new_context(viewport={"width": 1500, "height": 950})
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    page.goto(f"{BASE}/login.html", wait_until="domcontentloaded")
    page.fill("#loginUsername", "Reno"); page.fill("#loginPassword", "Reno12345")
    page.click("button[type=submit]"); page.wait_for_timeout(1500)

    # 丟棄式測試詞彙表 + 幾條條目
    g = ctx.request.post(f"{BASE}/api/glossaries",
        data={"name": "__ge_e2e__", "source_lang": "en", "target_lang": "zh"}).json()
    gid = g["id"]
    for s, t in [("SPEEDY SMARTIE", "伶俐驫駒 (H108)"), ("MALPENSA", "賢知友您"), ("GOLDEN SIXTY", "金鎗六十")]:
        ctx.request.post(f"{BASE}/api/glossaries/{gid}/entries", data={"source": s, "target": t})

    try:
        # 開一個 output_lang 檔嘅校對頁（細 yue 檔），揀丟棄式詞彙表落檔先
        ctx.request.patch(f"{BASE}/api/files/09e0e3679f35", data={"glossary_ids": [gid]})
        page.goto(f"{BASE}/proofread.html?file_id=09e0e3679f35", wait_until="networkidle")
        page.wait_for_selector("#glPanelList", timeout=15000)
        page.wait_for_timeout(1000)
        # 撳詞彙表名進入編輯（_glSelectForEdit）
        page.click(f'#glPanelList [data-glid="{gid}"]')
        page.wait_for_selector("#glEntrySearch", timeout=8000)
        rec("T1 搜尋框出現", page.locator("#glEntrySearch").count() == 1)
        # 搜尋 filter
        page.fill("#glEntrySearch", "malpen")
        page.wait_for_timeout(300)
        nrows = page.locator("#glEntryRows tr").count()
        rec("T2 搜尋 filter 生效", nrows == 1, f"{nrows} rows for 'malpen'")
        page.fill("#glEntrySearch", "")
        page.wait_for_timeout(300)
        rec("T3 清空搜尋還原", page.locator("#glEntryRows tr").count() == 3)
        # ✎ 開 modal，見到近音/別名欄
        page.click('#glEntryRows tr:first-child button[title="編輯"]')
        page.wait_for_selector("#geOverlay.open", timeout=5000)
        rec("T4 modal 有近音寫法欄", page.locator("#geVariants").count() == 1)
        rec("T5 modal 有別名欄", page.locator("#geAliases").count() == 1)
        # 加一個近音寫法（prompt）→ 儲存
        page.once("dialog", lambda d: d.accept("Speedy Smarty"))
        page.click('#geVariants .ge-chip-add')
        page.wait_for_selector('#geVariants .ge-chip:has-text("Speedy Smarty")', timeout=3000)
        page.click("#geSaveBtn")
        page.wait_for_selector("#geOverlay:not(.open)", timeout=5000)
        # 驗 persist
        entries = ctx.request.get(f"{BASE}/api/glossaries/{gid}").json()["entries"]
        hit = any("Speedy Smarty" in (e.get("source_variants") or []) for e in entries)
        rec("T6 近音寫法 persist", hit)
        rec("T7 表格 badge 出現",
            page.locator('#glEntryRows .gl-td-alt').count() >= 1)
        # +新增 用同一 modal（全欄位）
        page.click('button:has-text("+ 新增")')
        page.wait_for_selector("#geOverlay.open", timeout=5000)
        rec("T8 新增用同一 modal（有近音欄）", page.locator("#geVariants").count() == 1)
        page.click("#geCancelBtn")
        rec("no uncaught JS errors", len(errs) == 0, str(errs[:2]))
    finally:
        ctx.request.delete(f"{BASE}/api/glossaries/{gid}")
        # 還原檔案 glossary_ids（唔好留低測試表綁喺真檔）
        ctx.request.patch(f"{BASE}/api/files/09e0e3679f35", data={"glossary_ids": []})
    br.close()

npass = sum(1 for ok in results if ok)
print(f"\n==== {npass}/{len(results)} PASS ====")
sys.exit(0 if npass == len(results) else 1)
```

- [ ] **Step 2: 跑 E2E**

Run: `cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai" && backend/venv/bin/python frontend/tests/test_proofread_glossary_editor.py`
Expected: `==== N/N PASS ====`（全綠）。若某項 FAIL → 睇 selector / 時序，修 Task 1/2。

> 注意：測試會暫時把丟棄式詞彙表綁去 `09e0e3679f35`，跑完 finally 還原 `glossary_ids: []`。若該檔原本有 glossary_ids，改成還原成原值（測試開頭先 GET 記低）。

- [ ] **Step 3: CLAUDE.md 補一句**

喺 proofread「詞彙表」相關段落補：

```markdown
- **校對頁詞彙表面板**（output_lang）而家可以**搜尋條目**（原文/譯文/近音）+ 撳 ✎/+新增 開**條目編輯 modal**（原文/譯文 + 近音寫法 `source_variants` + 別名 `target_aliases`，編輯+新增共用，chip 批次保存）+ 每行「·近N」badge —— 對齊 Glossary.html 能力。純前端（`proofread.html`），後端 PATCH/POST entries 已收該欄位。
```

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/test_proofread_glossary_editor.py CLAUDE.md
git commit -m "test(proofread): 詞彙表編輯器 Playwright E2E + docs"
```

---

## Self-Review

**Spec coverage：**
- §2.1 搜尋（原文/譯文/近音）→ Task 2 `_glEntryMatches` + 搜尋框 ✅
- §2.2 編輯 modal（編輯+新增共用、四欄、prompt chip、Enter/Esc、批次保存 PATCH/POST）→ Task 1 ✅
- §2.3 每行 badge → Task 2 `gl-td-alt` ✅
- §3 取代舊 inline → Task 2 Step 2 刪除 ✅
- §4 邊界（403/空欄/出錯唔關）→ Task 1 `_geSave` ✅
- §5 XSS（escapeHtml + data-* delegation）→ Task 1 `_geRenderChips` / Task 2 rows ✅
- §6 測試（Playwright + 丟棄式表）→ Task 3 ✅
- §7 只改 proofread.html → Task 1/2；Task 3 加 E2E + CLAUDE.md ✅

**Placeholder scan：** 無 TBD。每步有完整 code。Task 3 Step 2 「還原成原值」係對齊實際指示（若檔案原本有 glossary_ids）— 已標明。

**Type consistency：** `openEntryModal(eid|null)` Task 1 定義、Task 2 ✎ + Task 1 +新增 消費；`_geVariants`/`_geAliases` string[]；save body `{source,target,source_variants,target_aliases}` 同後端 `update_entry`/`add_entry` 欄位一致；`_glEntryQuery` / `_glRenderRows` Task 2 內自洽；chip `data-kind`（'v'/'a'）+ `data-idx` / `data-add` 喺 `_geRenderChips` 產生、`_geChipClick` 消費，一致。

---

## Execution Handoff

Plan 完成。Task 1-2 static-verify + Task 3 E2E 全綠 = 完成。
