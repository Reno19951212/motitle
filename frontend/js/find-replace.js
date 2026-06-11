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
