# 校對頁尋找與取代（⌘F Find & Replace Popup）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `⌘F` 浮動「尋找與取代」視窗（680px、清單式逐句 取代/取代並批核/略過），成套取代舊 find bar。

**Architecture:** 後端只加一個可選 `keep_status` 參數落現有 `PATCH /translations/<idx>`（唔傳 = 照舊 auto-approve）。前端全部新 code 入獨立 module `frontend/js/find-replace.js`（classic script，讀 proofread.html 嘅 global `segs`/`setCursor` 等），proofread.html 剷舊 bar＋接新 module。

**Tech Stack:** Flask、vanilla JS、pytest、Playwright。

**Spec:** `docs/superpowers/specs/2026-06-11-proofread-find-replace-design.md`（已批准；視覺基準 = brainstorm mockup `popup-v2.html`）

**事實基準（已讀 code 確認）：**
- PATCH handler `api_update_translation`：app.py:3534-3648 — role 解析（output_lang first/second → `{lang}_text`+by_lang；legacy None → zh_text）、`updated = {**translations[idx], write_field: new_text, "status": "approved", "flags": [], "baseline_target": new_text, "applied_terms": []}`、by_lang dual-write（`"status": "approved"`）、aligned_bilingual string sync、回 `{"translation": _normalize_translation_for_api(...)}`
- 舊 find bar 三嚿要剷：CSS `.find-bar*`+`mark.fb-match*`（proofread.html:527-549）、markup `#findBar`（899-932）、JS `// Find & Replace` 區塊（3596 起：`fbMatches`/`fbCurMatch`/`openFindBar`/`closeFindBar`/`fbGetField`/`fbSearch`/`fbNav`/`fbReplaceCurrent`/`fbReplaceAll`）＋ `renderSegList` wrapper 嘅 fb highlight 部分（3749-3781）
- keydown 接線（3791-3800）：`⌘F → openFindBar()`、`Escape → findBar` — 兩個 check 都喺 `if (inInput) return;` 之前（popup input 內都會收到）
- `renderSegList()` 係 wrapper：`_renderSegListBase()` + fb highlight；**全頁多處 call `renderSegList`，wrapper 函數本身要保留**
- segs[] row：`{id, idx, in, out, tsIn, tsOut, duration, approved, flags, edited, en, zh, _hasSecond, ...}`；`en`=第一語言/原文欄、`zh`=第二語言/譯文欄；PATCH 要用 `segs[i].idx`（registry idx）
- 全局可用：`segs`(let)、`cursorIdx`、`fileInfo`、`fileId`、`API_BASE`、`setCursor(i, alsoSeek)`、`renderSegList`、`renderDetail`、`showToast(msg, kind)`、`escapeHtml`、`_outputLangLabel(role)`（output_lang 語言labels）
- script includes：proofread.html:1150-1153（`js/video-fullscreen.js` 之後加新 script tag）
- 測試：`cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_find_replace_patch.py -v`（單獨跑 — full suite 有 order 污染）；route-test seed/client pattern 抄 `tests/test_segment_timing.py`

---

### Task 1: 後端 `keep_status` 參數（TDD）

**Files:**
- Modify: `backend/app.py:3534-3648`（`api_update_translation`）
- Test: `backend/tests/test_find_replace_patch.py`（新檔）

- [ ] **Step 1: 寫 failing tests**

```python
# backend/tests/test_find_replace_patch.py
"""PATCH /translations/<idx> keep_status 參數 — find-replace 嘅「取代（保持狀態）」用。"""
import pytest

pytest.importorskip("flask")
import app as appmod


@pytest.fixture
def client(tmp_path, monkeypatch):
    from profiles import ProfileManager
    monkeypatch.setattr("app._profile_manager", ProfileManager(tmp_path))
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    appmod.app.config["TESTING"] = True
    appmod.app.config["R5_AUTH_BYPASS"] = True
    appmod.app.config["LOGIN_DISABLED"] = True
    with appmod.app.test_client() as c:
        yield c
    appmod.app.config.pop("R5_AUTH_BYPASS", None)
    appmod.app.config.pop("LOGIN_DISABLED", None)


def _seed(fid="f-fr", statuses=("pending", "approved")):
    trans = []
    for i, st in enumerate(statuses):
        trans.append({
            "idx": i, "start": float(i), "end": float(i + 1), "status": st,
            "flags": ["[LONG]"],
            "by_lang": {"yue": {"text": f"粵{i}", "status": st, "flags": []},
                        "en": {"text": f"EN{i}", "status": st, "flags": []}},
            "yue_text": f"粵{i}", "en_text": f"EN{i}", "glossary_changes": [],
        })
    with appmod._registry_lock:
        appmod._file_registry[fid] = {
            "id": fid, "user_id": "u1", "status": "done",
            "active_kind": "output_lang", "output_languages": ["yue", "en"],
            "translations": trans,
            "aligned_bilingual": [{"start": float(i), "end": float(i + 1),
                                   "by_lang": {"yue": f"粵{i}", "en": f"EN{i}"}}
                                  for i in range(len(statuses))],
        }
    return fid


def test_keep_status_preserves_pending(client):
    fid = _seed("f-fr-p")
    r = client.patch(f"/api/files/{fid}/translations/0",
                     json={"text": "新粵0", "role": "first", "keep_status": True})
    assert r.status_code == 200, r.get_data(as_text=True)
    with appmod._registry_lock:
        row = appmod._file_registry[fid]["translations"][0]
        assert row["status"] == "pending"                       # 狀態保持
        assert row["yue_text"] == "新粵0"                        # 文字有改
        assert row["by_lang"]["yue"]["text"] == "新粵0"
        assert row["by_lang"]["yue"]["status"] == "pending"      # by_lang 狀態都保持
        assert row["baseline_target"] == "新粵0"                 # baseline 照更新（防 glossary 還原）
        assert row["flags"] == []                                # flags 照清（文字已改）
        assert appmod._file_registry[fid]["aligned_bilingual"][0]["by_lang"]["yue"] == "新粵0"


def test_keep_status_preserves_approved(client):
    fid = _seed("f-fr-a")
    r = client.patch(f"/api/files/{fid}/translations/1",
                     json={"text": "新粵1", "role": "first", "keep_status": True})
    assert r.status_code == 200
    with appmod._registry_lock:
        row = appmod._file_registry[fid]["translations"][1]
        assert row["status"] == "approved"
        assert row["by_lang"]["yue"]["status"] == "approved"


def test_keep_status_second_role(client):
    fid = _seed("f-fr-s")
    r = client.patch(f"/api/files/{fid}/translations/0",
                     json={"text": "NewEN0", "role": "second", "keep_status": True})
    assert r.status_code == 200
    with appmod._registry_lock:
        row = appmod._file_registry[fid]["translations"][0]
        assert row["status"] == "pending"
        assert row["en_text"] == "NewEN0"
        assert row["by_lang"]["en"]["text"] == "NewEN0"
        assert row["by_lang"]["en"]["status"] == "pending"
        assert appmod._file_registry[fid]["aligned_bilingual"][0]["by_lang"]["en"] == "NewEN0"


def test_default_still_auto_approves(client):
    # regression — 唔傳 keep_status 必須照舊 auto-approve
    fid = _seed("f-fr-d")
    r = client.patch(f"/api/files/{fid}/translations/0",
                     json={"text": "改0", "role": "first"})
    assert r.status_code == 200
    with appmod._registry_lock:
        row = appmod._file_registry[fid]["translations"][0]
        assert row["status"] == "approved"
        assert row["by_lang"]["yue"]["status"] == "approved"
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_find_replace_patch.py -v`
Expected: `test_keep_status_*` 3 個 FAIL（status 變咗 approved）；`test_default_still_auto_approves` PASS

- [ ] **Step 3: 改 handler** — app.py `api_update_translation`，兩處：

(a) `role = data.get("role")` 嗰行（~3554）之後加：
```python
        # find-replace「取代（保持狀態）」— True 時唔 auto-approve（row + by_lang 狀態都唔郁）。
        # 唔傳 = False = 照舊 auto-approve（現有 callers 零影響）。
        keep_status = bool(data.get("keep_status"))
```

(b) `updated = {...}` block（~3616）改 `"status"` 一行：
```python
        updated = {
            **translations[idx],
            write_field: new_text,
            "status": translations[idx].get("status", "pending") if keep_status else "approved",
            "flags": [],
            # Manual edit becomes the new baseline; any prior glossary-apply
            # history is wiped so future glossary deletions don't revert past
            # the user's explicit edit.
            "baseline_target": new_text,
            "applied_terms": [],
        }
```

(c) by_lang dual-write block（~3632）改 status：
```python
        if do_by_lang_write:
            by_lang = dict(updated.get("by_lang") or {})
            if by_lang_key and by_lang_key in by_lang:
                _bl_st = (by_lang[by_lang_key].get("status", "pending")
                          if keep_status else "approved")
                by_lang[by_lang_key] = {**by_lang[by_lang_key], "text": new_text, "status": _bl_st}
                updated["by_lang"] = by_lang
```

- [ ] **Step 4: 跑測試確認 pass + regression**

Run: `cd backend && "…venv…/python" -m pytest tests/test_find_replace_patch.py tests/test_ai_edit.py -v` → 全 PASS
Run: `cd backend && FLASK_SECRET_KEY=test "…venv…/python" -c "import app; print('ok')"` → ok

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_find_replace_patch.py
git commit -m "feat(find-replace): PATCH translations 加 keep_status — 取代唔郁批核狀態"
```

---

### Task 2: 新 module `frontend/js/find-replace.js`

**Files:**
- Create: `frontend/js/find-replace.js`

- [ ] **Step 1: 寫成個 module**（完整內容如下；CSS 由 module 注入，self-contained）：

```javascript
/* ============================================================
   MoTitle — 校對頁尋找與取代 popup (FindReplace)

   ⌘F 非阻擋浮動視窗（可拖動）：即時搜 segs[] 全部語言欄 →
   match 清單（撳行跳段）→ 每行 取代（keep_status，狀態保持）/
   取代並批核 / 略過（可還原）；「全部取代」批量行「取代」語義。
   Spec: docs/superpowers/specs/2026-06-11-proofread-find-replace-design.md

   依賴 proofread.html 全域（classic script 共享 global scope）：
   segs, cursorIdx, fileInfo, fileId, API_BASE, setCursor,
   renderSegList, renderDetail, showToast, escapeHtml, _outputLangLabel
   ============================================================ */
(function () {
  'use strict';

  let built = false;
  let open = false;
  let query = '';            // 關閉後保留，⌘F 重開恢復
  let replaceText = '';
  let onlyPending = false;
  let matches = [];          // [{idx, col:'first'|'second', count, after?}]
  let states = new Map();    // `${idx}:${col}` -> 'replaced'|'replaced_approved'|'skipped'
  let debounceT = null;
  let chain = Promise.resolve();   // PATCH 串行（防亂序 reconcile）
  let drag = null;                 // {dx, dy}

  const CSS = `
  .fr-pop { position:fixed; top:64px; left:50%; transform:translateX(-50%); width:680px; max-width:94vw;
    background:var(--surface, #16161f); border:1px solid var(--border-strong, #3c3c58); border-radius:14px;
    box-shadow:0 24px 70px rgba(0,0,0,.65); color:var(--text, #dcdce6); font-size:13px;
    display:flex; flex-direction:column; max-height:560px; z-index:2600; }
  .fr-pop[hidden] { display:none; }
  .fr-head { display:flex; align-items:center; gap:10px; padding:12px 16px;
    border-bottom:1px solid var(--border, #26263a); cursor:grab; user-select:none; }
  .fr-head .t { font-weight:700; font-size:13.5px; }
  .fr-head .drag { color:var(--text-dim, #4a4a62); font-size:13px; letter-spacing:2px; }
  .fr-head .x { margin-left:auto; color:var(--text-mid, #8a8aa0); border:1px solid var(--border, #30304a);
    border-radius:6px; width:24px; height:24px; display:grid; place-items:center; cursor:pointer; background:none; font-size:12px; }
  .fr-head .x:hover { color:#fff; border-color:var(--accent, #6c63ff); }
  .fr-inputs { padding:12px 16px 4px; display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .fr-field { display:flex; flex-direction:column; gap:5px; }
  .fr-field label { font-size:10.5px; color:var(--text-dim, #7a7a92); letter-spacing:.5px; }
  .fr-inwrap { display:flex; align-items:center; background:var(--bg, #0d0d14);
    border:1px solid var(--border-strong, #3a3a55); border-radius:8px; padding:0 10px; }
  .fr-inwrap:focus-within { border-color:var(--accent, #6c63ff); }
  .fr-inwrap .ic { color:var(--text-dim, #5a5a75); font-size:12px; margin-right:7px; }
  .fr-inwrap input { flex:1; background:none; border:none; outline:none; color:var(--text, #f0f0f6);
    font-size:14px; padding:9px 0; min-width:0; font-family:inherit; }
  .fr-inwrap .cnt { font-size:11px; color:var(--accent-2, #8f88ff); white-space:nowrap; font-weight:600; }
  .fr-opts { display:flex; align-items:center; gap:16px; padding:8px 16px 10px; font-size:11.5px;
    color:var(--text-mid, #9a9ab2); }
  .fr-opts label { display:flex; gap:6px; align-items:center; cursor:pointer; }
  .fr-opts .hint { color:var(--text-dim, #55556e); }
  .fr-opts .bulk { margin-left:auto; background:rgba(108,99,255,.12); border:1px solid rgba(108,99,255,.4);
    color:#b8b2ff; padding:6px 14px; border-radius:7px; font-size:12px; cursor:pointer; font-weight:600; font-family:inherit; }
  .fr-opts .bulk:hover { background:rgba(108,99,255,.2); }
  .fr-opts .bulk[disabled] { opacity:.4; pointer-events:none; }
  .fr-list { overflow-y:auto; flex:1; min-height:0; }
  .fr-it { display:flex; align-items:center; gap:12px; padding:11px 16px;
    border-top:1px solid var(--border, #1f1f2e); cursor:pointer; }
  .fr-it:hover { background:rgba(255,255,255,.03); }
  .fr-it .meta { min-width:86px; display:flex; flex-direction:column; gap:2px; }
  .fr-it .meta .seg { font-size:12px; font-weight:700; }
  .fr-it .meta .tc { font-size:10px; color:var(--text-dim, #6a6a85); font-family:var(--font-mono, monospace); }
  .fr-it .meta .lang { font-size:9.5px; padding:2px 7px; border-radius:5px; background:rgba(108,99,255,.12);
    color:#9a94d8; white-space:nowrap; align-self:flex-start; margin-top:2px; }
  .fr-it .txt { flex:1; line-height:1.6; font-size:13px; color:var(--text-mid, #c9c9d8); word-break:break-word; }
  .fr-it .txt mark.fr-old { background:rgba(108,99,255,.3); color:#d6d2ff; border-radius:3px; padding:0 3px; font-weight:600; }
  .fr-it .txt .fr-arrow { color:var(--text-dim, #5a5a72); margin:0 6px; }
  .fr-it .txt .fr-new { background:rgba(34,197,94,.17); color:#8fefad; border-radius:3px; padding:0 3px; font-weight:600; }
  .fr-it .acts { display:flex; gap:6px; }
  .fr-b { border:1px solid var(--border-strong, #3a3a55); background:rgba(255,255,255,.04);
    color:var(--text, #cfcfdd); border-radius:7px; padding:6px 12px; font-size:11.5px; cursor:pointer;
    white-space:nowrap; font-family:inherit; }
  .fr-b:hover { border-color:var(--accent, #6c63ff); }
  .fr-b.go { background:rgba(108,99,255,.13); border-color:rgba(108,99,255,.47); color:#c4bdff; font-weight:600; }
  .fr-b.goap { background:rgba(34,197,94,.11); border-color:rgba(34,197,94,.4); color:#8fefad; font-weight:600; }
  .fr-b.skip { color:var(--text-mid, #8a8aa0); }
  .fr-it.done { opacity:.55; }
  .fr-it.ro { opacity:.6; }
  .fr-tag { font-size:10px; padding:3px 8px; border-radius:5px; white-space:nowrap; }
  .fr-tag.ok { background:rgba(34,197,94,.13); color:#8fefad; }
  .fr-tag.okap { background:rgba(34,197,94,.2); color:#a8f5c0; }
  .fr-tag.rot { background:rgba(255,255,255,.06); color:var(--text-mid, #8a8aa0); }
  .fr-empty { padding:22px 16px; text-align:center; color:var(--text-dim, #6a6a85); font-size:12px; }
  .fr-foot { display:flex; align-items:center; gap:14px; padding:10px 16px;
    border-top:1px solid var(--border, #26263a); font-size:11px; color:var(--text-dim, #7a7a92); }
  .fr-foot .kbd { background:rgba(255,255,255,.05); border:1px solid var(--border, #30304a);
    border-radius:4px; padding:1px 6px; font-family:var(--font-mono, monospace); font-size:10px; }
  mark.fr-rail { background:rgba(108,99,255,.32); color:inherit; border-radius:2px; padding:0 1px; }
  `;

  // ---------- 欄位模型 ----------
  function isOL() { return !!(window.fileInfo || fileInfo) && fileInfo.active_kind === 'output_lang'; }
  function colText(s, col) { return (col === 'first' ? s.en : s.zh) || ''; }
  function colLabel(col) {
    if (isOL()) return (_outputLangLabel(col) || (col === 'first' ? '第一語言' : '第二語言'));
    return col === 'first' ? '原文' : '譯文';
  }
  function colEditable(col) {
    // spec：output_lang 兩欄都可取代；舊式檔（profile/V6）只譯文欄；原文欄一律唯讀
    if (isOL()) return true;
    return col === 'second';
  }
  function colsOf(s) {
    const out = [];
    if ((s.en || '').length) out.push('first');
    const hasSecond = isOL() ? (s._hasSecond === true) : true;
    if (hasSecond && (s.zh || '').length) out.push('second');
    return out;
  }
  const key = (m) => `${m.idx}:${m.col}`;

  // ---------- 文字 utils（大小寫不敏感）----------
  function countCI(raw, q) {
    const lraw = raw.toLowerCase(), lq = q.toLowerCase();
    let n = 0, at = lraw.indexOf(lq);
    while (at !== -1) { n++; at = lraw.indexOf(lq, at + lq.length); }
    return n;
  }
  function replaceAllCI(raw, q, rep) {
    if (!q) return raw;
    const lraw = raw.toLowerCase(), lq = q.toLowerCase();
    let out = '', last = 0, at = lraw.indexOf(lq);
    while (at !== -1) { out += raw.slice(last, at) + rep; last = at + q.length; at = lraw.indexOf(lq, last); }
    return out + raw.slice(last);
  }
  function markCI(raw, q, cls) {
    const lraw = raw.toLowerCase(), lq = q.toLowerCase();
    let out = '', last = 0, at = lraw.indexOf(lq);
    while (at !== -1) {
      out += escapeHtml(raw.slice(last, at));
      out += `<mark class="${cls}">${escapeHtml(raw.slice(at, at + q.length))}</mark>`;
      last = at + q.length; at = lraw.indexOf(lq, last);
    }
    return out + escapeHtml(raw.slice(last));
  }

  // ---------- DOM ----------
  function build() {
    if (built) return;
    built = true;
    const st = document.createElement('style');
    st.textContent = CSS;
    document.head.appendChild(st);
    const el = document.createElement('div');
    el.className = 'fr-pop';
    el.id = 'frPop';
    el.hidden = true;
    el.innerHTML = `
      <div class="fr-head" id="frHead">
        <span class="t">尋找與取代</span><span class="drag">⠿</span>
        <button class="x" id="frClose" aria-label="關閉">✕</button>
      </div>
      <div class="fr-inputs">
        <div class="fr-field"><label>尋找（全部語言欄）</label>
          <div class="fr-inwrap"><span class="ic">🔍</span>
            <input id="frFind" type="text" placeholder="輸入字詞…"><span class="cnt" id="frCnt"></span></div></div>
        <div class="fr-field"><label>取代為</label>
          <div class="fr-inwrap"><span class="ic">↺</span>
            <input id="frRep" type="text" placeholder="留空 = 刪除字詞"></div></div>
      </div>
      <div class="fr-opts">
        <label><input type="checkbox" id="frPend"> 只搜未批核</label>
        <span class="hint">撳行＝跳去嗰段＋影片預覽</span>
        <button class="bulk" id="frBulk">全部取代</button>
      </div>
      <div class="fr-list" id="frList"><div class="fr-empty">輸入字詞開始搜尋</div></div>
      <div class="fr-foot"><span id="frStats">—</span>
        <span style="margin-left:auto;"><span class="kbd">Esc</span> 關閉 · <span class="kbd">⌘F</span> 重開</span></div>`;
    document.body.appendChild(el);

    document.getElementById('frClose').addEventListener('click', close);
    document.getElementById('frFind').addEventListener('input', (e) => {
      query = e.target.value;
      states = new Map();                 // 查詢改變 → reset 略過/完成記錄
      clearTimeout(debounceT);
      debounceT = setTimeout(runSearch, 150);
    });
    document.getElementById('frRep').addEventListener('input', (e) => {
      replaceText = e.target.value;
      renderList();                       // 即時更新 before→after 預覽
    });
    document.getElementById('frPend').addEventListener('change', (e) => {
      onlyPending = e.target.checked;
      runSearch();
    });
    document.getElementById('frBulk').addEventListener('click', bulkReplace);

    // 清單 delegation：掣 → 動作；行其他位置 → 跳段
    document.getElementById('frList').addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-act]');
      const row = e.target.closest('.fr-it');
      if (!row) return;
      const m = matches[Number(row.dataset.mi)];
      if (!m) return;
      if (btn) {
        e.stopPropagation();
        const act = btn.dataset.act;
        if (act === 'go') doReplace(m, false);
        else if (act === 'goap') doReplace(m, true);
        else if (act === 'skip') { states.set(key(m), 'skipped'); renderList(); }
        else if (act === 'unskip') { states.delete(key(m)); renderList(); }
        return;
      }
      setCursor(m.idx, true);
    });

    // 拖動
    const head = document.getElementById('frHead');
    head.addEventListener('mousedown', (e) => {
      if (e.target.closest('#frClose')) return;
      const r = el.getBoundingClientRect();
      drag = { dx: e.clientX - r.left, dy: e.clientY - r.top };
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!drag) return;
      el.style.left = Math.max(8, Math.min(window.innerWidth - 60, e.clientX - drag.dx)) + 'px';
      el.style.top = Math.max(8, Math.min(window.innerHeight - 60, e.clientY - drag.dy)) + 'px';
      el.style.transform = 'none';
    });
    document.addEventListener('mouseup', () => { drag = null; });
  }

  // ---------- 搜尋 ----------
  function runSearch() {
    matches = [];
    const q = query.trim();
    if (q) {
      segs.forEach((s, i) => {
        if (onlyPending && s.approved) return;
        for (const col of colsOf(s)) {
          const n = countCI(colText(s, col), q);
          if (n > 0) matches.push({ idx: i, col, count: n });
        }
      });
    }
    renderList();
    renderSegList();        // rail 重繪（wrapper 會 call decorateRail）
  }

  function renderList() {
    const q = query.trim();
    const list = document.getElementById('frList');
    if (!list) return;
    const occ = matches.reduce((a, m) => a + m.count, 0);
    const segsN = new Set(matches.map(m => m.idx)).size;
    document.getElementById('frCnt').textContent = q ? `${occ} 個 · ${segsN} 段` : '';

    if (!q) { list.innerHTML = '<div class="fr-empty">輸入字詞開始搜尋</div>'; updateFoot(); return; }
    if (!matches.length) { list.innerHTML = '<div class="fr-empty">冇匹配結果</div>'; updateFoot(); return; }

    list.innerHTML = matches.map((m, mi) => {
      const s = segs[m.idx];
      if (!s) return '';
      const st = states.get(key(m));
      const editable = colEditable(m.col);
      const raw = colText(s, m.col);
      let txt, right;
      if (st === 'replaced' || st === 'replaced_approved') {
        txt = `<span class="fr-new">${escapeHtml(m.after || raw)}</span>`;
        right = st === 'replaced_approved'
          ? '<span class="fr-tag okap">✓ 已取代＋批核</span>'
          : '<span class="fr-tag ok">✓ 已取代</span>';
      } else if (st === 'skipped') {
        txt = markCI(raw, q, 'fr-old');
        right = '<button class="fr-b skip" data-act="unskip">已略過 · 還原</button>';
      } else if (!editable) {
        txt = markCI(raw, q, 'fr-old');
        right = '<span class="fr-tag rot">唯讀</span>';
      } else {
        txt = markCI(raw, q, 'fr-old');
        const after = replaceAllCI(raw, q, replaceText);
        if (after !== raw) {
          const afterHtml = replaceText ? markCI(after, replaceText, 'fr-new') : escapeHtml(after);
          txt += `<span class="fr-arrow">→</span>` + afterHtml;
        }
        right = `<div class="acts">
          <button class="fr-b go" data-act="go">取代</button>
          <button class="fr-b goap" data-act="goap">取代並批核</button>
          <button class="fr-b skip" data-act="skip">略過</button></div>`;
      }
      const cls = (st === 'replaced' || st === 'replaced_approved') ? 'done' : (!editable ? 'ro' : '');
      return `<div class="fr-it ${cls}" data-mi="${mi}">
        <div class="meta"><span class="seg">#${s.id}</span><span class="tc">${escapeHtml(s.tsIn || '')}</span>
          <span class="lang">${escapeHtml(colLabel(m.col))}</span></div>
        <div class="txt">${txt}</div>${right}</div>`;
    }).join('');
    updateFoot();
  }

  function pendingMatches() {
    return matches.filter(m => colEditable(m.col) && !states.has(key(m)));
  }
  function updateFoot() {
    const done = [...states.values()].filter(v => v.startsWith('replaced')).length;
    const skipped = [...states.values()].filter(v => v === 'skipped').length;
    const left = pendingMatches().length;
    document.getElementById('frStats').textContent =
      query.trim() ? `已取代 ${done} · 略過 ${skipped} · 剩 ${left}` : '—';
    const bulk = document.getElementById('frBulk');
    bulk.textContent = `全部取代 (${left})`;
    bulk.disabled = left === 0 || query.trim() === '';
  }

  // ---------- 取代 ----------
  function doReplace(m, approve) {
    const q = query.trim();
    chain = chain.then(async () => {
      const s = segs[m.idx];
      if (!s) return;
      const raw = colText(s, m.col);
      const newText = replaceAllCI(raw, q, replaceText);
      if (newText === raw) { states.set(key(m), approve ? 'replaced_approved' : 'replaced'); m.after = raw; renderList(); return; }
      const body = { text: newText };
      if (isOL()) body.role = m.col;       // legacy 譯文欄：唔傳 role（寫 zh_text）
      if (!approve) body.keep_status = true;
      const r = await fetch(`${API_BASE}/api/files/${fileId}/translations/${s.idx}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
      const stStatus = data.translation && data.translation.status;
      segs = segs.map((seg, i) => i === m.idx
        ? { ...seg, [m.col === 'first' ? 'en' : 'zh']: newText,
            approved: stStatus === 'approved', edited: true }
        : seg);
      states.set(key(m), approve ? 'replaced_approved' : 'replaced');
      m.after = newText;
      renderSegList();
      if (cursorIdx === m.idx) renderDetail();
      renderList();
    }).catch((e) => { showToast(`取代失敗：${e.message}`, 'error'); });
    return chain;
  }

  async function bulkReplace() {
    const todo = pendingMatches();
    if (!todo.length) return;
    let ok = 0, fail = 0;
    for (const m of todo) {
      await doReplace(m, false);
      if (states.get(key(m)) === 'replaced') ok++; else fail++;
    }
    showToast(fail ? `全部取代：成功 ${ok}，失敗 ${fail}` : `已取代 ${ok} 行`, fail ? 'warning' : 'success');
  }

  // ---------- rail highlight（由 renderSegList wrapper call）----------
  function decorateRail() {
    if (!open) return;
    const q = query.trim();
    if (!q) return;
    matches.forEach((m) => {
      if (states.has(key(m))) return;
      const row = document.querySelector(`.rv-b-rail-item[data-idx="${m.idx}"]`);
      if (!row) return;
      const textEl = m.col === 'second'
        ? row.querySelector('.rv-b-rail-text-2')
        : row.querySelector('.rv-b-rail-text-1');
      if (!textEl) return;
      const s = segs[m.idx];
      if (!s) return;
      textEl.innerHTML = markCI(colText(s, m.col), q, 'fr-rail');
    });
  }

  // ---------- open/close ----------
  function openPop() {
    if (typeof segs === 'undefined' || !Array.isArray(segs) || !segs.length ||
        typeof fileInfo === 'undefined' || !fileInfo) {
      showToast('檔案載入中，請稍候…', 'info');
      return;
    }
    build();
    const el = document.getElementById('frPop');
    el.hidden = false;
    open = true;
    const f = document.getElementById('frFind');
    f.value = query;                       // 重開恢復上次查詢
    document.getElementById('frRep').value = replaceText;
    document.getElementById('frPend').checked = onlyPending;
    f.focus(); f.select();
    runSearch();
  }
  function close() {
    if (!built) return;
    document.getElementById('frPop').hidden = true;
    open = false;
    matches = [];
    renderSegList();                       // 清 rail highlight
  }
  function isOpen() { return open; }

  window.FindReplace = { open: openPop, close, isOpen, decorateRail };
})();
```

- [ ] **Step 2: Syntax check + commit**

```bash
node --check frontend/js/find-replace.js
git add frontend/js/find-replace.js
git commit -m "feat(find-replace): FindReplace module — 680px popup、即時搜全語言欄、逐行取代/取代並批核/略過"
```

---

### Task 3: proofread.html 接線 + 剷舊 find bar

**Files:**
- Modify: `frontend/proofread.html`

- [ ] **Step 1: 加 script tag** — line 1153 `<script src="js/video-fullscreen.js"></script>` 之後加：

```html
<script src="js/find-replace.js"></script>
```

- [ ] **Step 2: 剷 CSS（527-549）** — 由 `.find-bar {` 到 `mark.fb-match.fb-cur { ... }` 嘅 block 完結（連 `.find-bar[hidden]`/`.find-bar-input*`/`.find-bar-sep`/`.find-bar-count`/`.find-bar-group`）成段刪除。

- [ ] **Step 3: 剷 markup（899-932）** — 成個 `<div id="findBar" class="find-bar" …>…</div>` 刪除。

- [ ] **Step 4: 剷 JS 區塊** — 由 `// Find & Replace` section header（~3596，連頂部 `// ====` 兩行）到 `fbReplaceAll` 函數完結（即 `renderSegList` wrapper 之前）成段刪除（`fbMatches`/`fbCurMatch`/`openFindBar`/`closeFindBar`/`fbGetField`/`fbSearch`/`fbNav`/`fbReplaceCurrent`/`fbReplaceAll` 全部）。

- [ ] **Step 5: 簡化 renderSegList wrapper**（3749-3781）— 成個 function 換成：

```javascript
  // renderSegList — wraps _renderSegListBase so FindReplace can decorate rail matches
  function renderSegList() {
    _renderSegListBase();
    if (window.FindReplace) FindReplace.decorateRail();
  }
```

- [ ] **Step 6: keydown 接線**（3791-3800）— 現有：

```javascript
    // Cmd+F / Ctrl+F → open find bar (intercept even in inputs)
    if ((e.metaKey || e.ctrlKey) && e.key === 'f') {
      e.preventDefault();
      openFindBar();
      return;
    }
    // Escape → close find bar first; if not open, let the GA modal listener handle it
    if (e.key === 'Escape') {
      const bar = document.getElementById('findBar');
      if (!bar.hidden) { closeFindBar(); e.preventDefault(); return; }
    }
```
換成：
```javascript
    // Cmd+F / Ctrl+F → open find & replace popup (intercept even in inputs)
    if ((e.metaKey || e.ctrlKey) && e.key === 'f') {
      e.preventDefault();
      FindReplace.open();
      return;
    }
    // Escape → close find & replace first; if not open, let the GA modal listener handle it
    if (e.key === 'Escape') {
      if (window.FindReplace && FindReplace.isOpen()) { FindReplace.close(); e.preventDefault(); return; }
    }
```

- [ ] **Step 7: 殘留檢查 + syntax + commit**

```bash
grep -n "findBar\|fbFind\|fbSearch\|fbNav\|fbReplace\|fbMatches\|fbCurMatch\|fbOnlyPending\|fbGetField\|openFindBar\|closeFindBar\|fb-match\|find-bar" frontend/proofread.html
# Expected: 零輸出（全部剷晒）
python3 - <<'EOF'
import re, subprocess
html = open('frontend/proofread.html', encoding='utf-8').read()
open('/tmp/fr.js','w').write('\n;\n'.join(re.findall(r'<script>(.*?)</script>', html, re.DOTALL)))
EOF
node --check /tmp/fr.js
git add frontend/proofread.html
git commit -m "feat(find-replace): proofread 接 FindReplace popup，剷舊 find bar（CSS+markup+fb* JS）"
```

---

### Task 4: E2E（真 Chrome + 真後端）

前提：dev ff + :5001 重啟（backend 有改）。測試檔 `d15bba41e2b0`（output_lang）。**測試真改數據 — 結尾反向取代還原。**

- [ ] `/tmp/find_replace_e2e.py`：

```python
"""E2E: ⌘F 尋找取代 — 開窗、即時搜尋、跳段、取代(保持狀態)、取代並批核、還原。"""
import asyncio

from playwright.async_api import async_playwright

BASE = 'http://localhost:5001'
FILE_ID = 'd15bba41e2b0'


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', headless=True)
        page = await (await b.new_context(viewport={'width': 1600, 'height': 1000})).new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        await page.goto(BASE + '/login.html')
        await page.evaluate("""async () => { await fetch('/login', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({username:'admin_p3', password:'TestPass1!'})}); }""")
        await page.goto(BASE + f'/proofread.html?file_id={FILE_ID}')
        await page.wait_for_selector('.rv-b-rail-item', timeout=20000)
        await page.wait_for_timeout(800)

        # 舊 bar 應該唔存在
        assert await page.locator('#findBar').count() == 0, 'old find bar still present'

        # 搵一個真係存在嘅查詢詞（segs[1] 第一語言頭 2 隻字）+ 記原狀態
        probe = await page.evaluate("() => ({q: (segs[1].en || '').slice(0, 2), "
                                    "st: segs[1].approved, txt: segs[1].en})")
        q = probe['q']
        assert len(q) == 2, f'probe term too short: {probe}'
        print('query:', q, '| seg1 approved:', probe['st'])

        # ⌘F 開窗 + 即時搜尋
        await page.keyboard.press('Meta+f')
        await page.wait_for_selector('#frPop:not([hidden])', timeout=3000)
        await page.fill('#frFind', q)
        await page.wait_for_timeout(500)
        rows = await page.locator('.fr-it').count()
        cnt = await page.text_content('#frCnt')
        print('rows:', rows, '| cnt:', cnt)
        assert rows > 0 and ('個' in (cnt or ''))

        # 撳第一行（非掣位置）→ 跳段
        await page.locator('.fr-it .txt').first.click()
        await page.wait_for_timeout(400)

        # 「取代」keep-status：將 q → q+'査' 喺第一個未完成行
        await page.fill('#frRep', q + '査')
        await page.wait_for_timeout(300)
        first_btn = page.locator('.fr-it button[data-act="go"]').first
        mi = await page.evaluate("() => { const r = document.querySelector('.fr-it button[data-act=\\\"go\\\"]')"
                                 ".closest('.fr-it'); return Number(r.dataset.mi); }")
        info = await page.evaluate(f"(mi) => {{ /* matches 喺 module scope，經 DOM 攞 */ "
                                   f"const row = document.querySelectorAll('.fr-it')[mi]; "
                                   f"return {{seg: row.querySelector('.seg').textContent}}; }}", mi)
        print('replacing in row', mi, info)
        before = await page.evaluate("() => segs.map(s => ({en: s.en, ap: s.approved}))")
        await first_btn.click()
        await page.wait_for_timeout(900)
        tag = await page.locator('.fr-it.done .fr-tag').first.text_content()
        print('tag:', tag)
        assert '已取代' in tag

        # API 覆核：搵改咗嘅段 — 文字有 q+'査'、status 冇變
        changed = await page.evaluate(
            "async (q2) => { const r = await fetch(`/api/files/d15bba41e2b0/translations`);"
            " const d = await r.json();"
            " const hit = d.translations.find(t => Object.values(t.by_lang || {})"
            "   .some(v => (v.text || '').includes(q2)));"
            " return hit ? {idx: hit.idx, status: hit.status} : null; }", q + '査')
        print('changed row:', changed)
        assert changed, 'replacement not persisted'
        assert changed['status'] == ('approved' if before[changed['idx']]['ap'] else 'pending'), \
            'keep_status failed — status flipped'

        # 還原：搜 q+'査' → 取代返做 q（用「取代並批核」驗 approve 路徑 — 之後 unapprove 還原）
        was_approved = before[changed['idx']]['ap']
        await page.fill('#frFind', q + '査')
        await page.wait_for_timeout(500)
        await page.fill('#frRep', q)
        await page.wait_for_timeout(300)
        await page.locator('.fr-it button[data-act="goap"]').first.click()
        await page.wait_for_timeout(900)
        after = await page.evaluate(
            "async (i) => { const r = await fetch(`/api/files/d15bba41e2b0/translations`);"
            " const d = await r.json(); return d.translations[i].status; }", changed['idx'])
        assert after == 'approved', 'replace+approve did not approve'
        if not was_approved:
            await page.evaluate(
                "async (i) => { await fetch(`/api/files/d15bba41e2b0/translations/${i}/unapprove`,"
                " {method:'POST'}); }", changed['idx'])
        final = await page.evaluate(
            "async (i) => { const r = await fetch(`/api/files/d15bba41e2b0/translations`);"
            " const d = await r.json(); return {st: d.translations[i].status,"
            " ok: !JSON.stringify(d.translations[i]).includes('査')}; }", changed['idx'])
        print('final:', final)
        assert final['ok'], 'text not restored'
        assert final['st'] == ('approved' if was_approved else 'pending'), 'status not restored'

        # Esc 關 + ⌘F 重開保留查詢
        await page.keyboard.press('Escape')
        assert await page.evaluate("() => document.getElementById('frPop').hidden") is True
        await page.keyboard.press('Meta+f')
        await page.wait_for_timeout(300)
        assert (await page.input_value('#frFind')) == q + '査', 'query not preserved on reopen'

        await page.screenshot(path='/tmp/find-replace-e2e.png')
        print('JS errors:', errs if errs else 'none')
        assert not errs
        await b.close()
        print('FIND REPLACE E2E PASS')


asyncio.run(main())
```

執行者跑之前用 Read 檢查一次 script（f-string/quote escaping 易壞），跑完用 Read 開 screenshot 肉眼驗。

- [ ] 跑 E2E + screenshot 驗證；「全部取代」用細範圍人手快測（搜一個 2-3 row 詞 → 全部取代 → 反向全部取代還原）。

---

### Task 5: 文檔

- [ ] CLAUDE.md：proofread.html frontend 描述加尋找取代一句；Current State 加「Proofread 尋找與取代 (⌘F, NEW 2026-06-11)」段（680px popup、全語言欄、取代 keep_status／取代並批核／略過、全部取代、舊 find bar 已剷、`js/find-replace.js`）；REST 區註明 PATCH translations 接受 `keep_status`
- [ ] README.md：校對章節加「尋找與取代」用戶說明（繁中）
- [ ] Commit：`docs: 校對頁尋找與取代功能`

---

## 驗收清單

- [ ] `tests/test_find_replace_patch.py` + `tests/test_ai_edit.py`（regression）全 PASS（單獨跑）
- [ ] `FLASK_SECRET_KEY=test python -c "import app"` 唔爆
- [ ] `node --check frontend/js/find-replace.js` + proofread.html inline scripts 過
- [ ] proofread.html 零 `fb*`/`findBar`/`find-bar` 殘留
- [ ] E2E PASS（開窗／搜尋／跳段／取代保持狀態／取代並批核／還原／Esc／重開保留查詢／舊 bar 唔存在）
- [ ] CLAUDE.md + README 更新
