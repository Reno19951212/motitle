/* ============================================================
   MoTitle — 檔案庫 Files page logic (vanilla JS)
   REAL-wired to the live backend:
     - GET  /api/files                         (list, polled every 3s)
     - GET  /api/files/<id>/subtitle.srt       (bulk / per-row SRT download)
     - DELETE /api/files/<id>                  (bulk / per-row delete)
     - GET  /api/me                            (user chip)
   Client-side tab filtering + filename filter + sorting are done on the
   fetched list because /api/files has no server-side filter param.

   Upload is handled by redirecting to index.html, where the real
   cross-language upload popup lives — there is no standalone upload
   modal here.
   ============================================================ */
(function () {
  'use strict';

  const POLL_MS = 3000;

  /* ---- live state ---- */
  let FILES = [];          // last fetched /api/files list
  let activeTab = 'all';
  let query = '';
  let sortKey = 'date';
  const selected = new Set();
  let firstLoad = true;

  /* ---- status model (derived from real registry statuses) ----
     Real file.status values: uploaded / transcribing / done / error
     Real file.translation_status: null / translating / done
     We derive a display status key for tab filtering + badge. */
  function statusOf(f) {
    if (f.status === 'error') return { key: 'error', label: '錯誤', cls: 'badge--error', dot: true };
    if (f.status === 'transcribing' || f.status === 'extracting') return { key: 'processing', label: '轉錄中', cls: 'badge--processing', dot: true };
    if (f.translation_status === 'translating') return { key: 'processing', label: '翻譯中', cls: 'badge--processing', dot: true };
    if (f.status === 'uploaded' || f.status === 'queued') return { key: 'processing', label: '排隊中', cls: 'badge--queued', dot: true };
    if (f.status === 'done') {
      const segs = f.segment_count || 0;
      const ap = f.approved_count || 0;
      if (segs > 0 && ap >= segs) return { key: 'done', label: '已完成', cls: 'badge--done-solid' };
      return { key: 'review', label: '待校對', cls: 'badge--queued', dot: true };
    }
    return { key: 'idle', label: '待處理', cls: 'badge--idle' };
  }

  /* ---- formatters ---- */
  function fmtSize(bytes) {
    if (!bytes || bytes < 0) return '—';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
  }
  function fmtRel(ts) {
    // uploaded_at is a unix epoch (seconds). Guard against ms / missing.
    if (!ts) return '—';
    if (ts > 1e12) ts = ts / 1000; // tolerate millisecond timestamps
    const d = Math.floor(Date.now() / 1000) - ts;
    if (d < 0) return '剛剛';
    if (d < 60) return '剛剛';
    if (d < 3600) return Math.floor(d / 60) + ' 分鐘前';
    if (d < 86400) return Math.floor(d / 3600) + ' 小時前';
    if (d < 86400 * 7) return Math.floor(d / 86400) + ' 天前';
    const dt = new Date(ts * 1000);
    return `${dt.getMonth() + 1}月${dt.getDate()}日`;
  }
  function ext(name) { const m = String(name || '').match(/\.([a-z0-9]+)$/i); return m ? m[1].toUpperCase() : 'FILE'; }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

  /* ---- tab defs ---- */
  const TAB_DEFS = [
    { key: 'all', label: '全部', match: () => true },
    { key: 'done', label: '已完成', match: (f) => statusOf(f).key === 'done' },
    { key: 'review', label: '待校對', match: (f) => statusOf(f).key === 'review' },
    { key: 'processing', label: '處理中', match: (f) => statusOf(f).key === 'processing' },
    { key: 'error', label: '錯誤', match: (f) => statusOf(f).key === 'error' },
  ];
  // order used by the status sort
  const STATUS_ORDER = { processing: 0, review: 1, error: 2, done: 3, idle: 4 };

  function visibleFiles() {
    const tab = TAB_DEFS.find((t) => t.key === activeTab) || TAB_DEFS[0];
    let list = FILES.filter((f) => tab.match(f));
    if (query) {
      const q = query.toLowerCase();
      list = list.filter((f) => String(f.original_name || '').toLowerCase().includes(q));
    }
    list = list.slice().sort((a, b) => {
      if (sortKey === 'name') return String(a.original_name || '').localeCompare(String(b.original_name || ''));
      if (sortKey === 'segs') return (b.segment_count || 0) - (a.segment_count || 0);
      if (sortKey === 'status') return (STATUS_ORDER[statusOf(a).key] ?? 9) - (STATUS_ORDER[statusOf(b).key] ?? 9);
      return (b.uploaded_at || 0) - (a.uploaded_at || 0); // date (newest first)
    });
    return list;
  }

  /* ---- render: stats ---- */
  function renderStats() {
    const total = FILES.length;
    const done = FILES.filter((f) => statusOf(f).key === 'done').length;
    const proc = FILES.filter((f) => statusOf(f).key === 'processing').length;
    const review = FILES.filter((f) => statusOf(f).key === 'review').length;
    const totSegs = FILES.reduce((a, f) => a + (f.segment_count || 0), 0);
    // /api/files does NOT return per-file duration, so the design's "總時長"
    // is reframed as total segment count across the library (the closest
    // real-data signal we have).
    const cards = [
      { k: '檔案總數', v: total, sub: '個', dot: 'var(--accent-2)' },
      { k: '已完成', v: done, sub: '個', dot: 'var(--success)' },
      { k: '待校對 / 處理中', v: review + proc, sub: '個', dot: 'var(--warning)' },
      { k: '總段數', v: totSegs, sub: '段', dot: 'var(--info)' },
    ];
    document.getElementById('stats').innerHTML = cards.map((c) => `
      <div class="stat">
        <div class="s-k"><span class="sd" style="background:${c.dot}"></span>${c.k}</div>
        <div class="s-v tnum">${c.v}<small>${c.sub}</small></div>
      </div>`).join('');
  }

  /* ---- render: tabs ---- */
  function renderTabs() {
    document.getElementById('tabs').innerHTML = TAB_DEFS.map((t) => {
      const n = FILES.filter((f) => t.match(f)).length;
      return `<button class="tab ${t.key === activeTab ? 'on' : ''}" data-tab="${t.key}">${t.label}<span class="cnt">${n}</span></button>`;
    }).join('');
    document.querySelectorAll('.tab').forEach((el) => {
      el.onclick = () => { activeTab = el.dataset.tab; renderTabs(); renderRows(); };
    });
  }

  /* ---- render: language chips (role first=purple, second=cyan) ---- */
  function langChips(f) {
    const langs = Array.isArray(f.languages) ? f.languages : [];
    const first = langs.find((l) => l.role === 'first');
    const second = langs.find((l) => l.role === 'second');
    let h = '';
    if (first) h += `<span class="lchip lchip--1" title="目標第一語言（${esc((first.lang || '').toUpperCase())}）">${esc((first.lang || '').toUpperCase())}</span>`;
    if (second) h += `<span class="lchip lchip--2" title="目標第二語言（${esc((second.lang || '').toUpperCase())}）">${esc((second.lang || '').toUpperCase())}</span>`;
    return h ? `<span class="lang-chips">${h}</span>` : '<span class="dim">—</span>';
  }

  /* ---- render: segment / approved cell ---- */
  function segCell(f) {
    const st = statusOf(f);
    if (st.key === 'processing') {
      return `<div class="seg-cell">處理中…</div>`;
    }
    const segs = f.segment_count || 0;
    if (!segs) return '<span class="dim">—</span>';
    const ap = f.approved_count || 0;
    const full = ap >= segs;
    return `<div class="seg-cell">${segs} 段<br><span class="ap">${full ? '全部已核准' : ap + ' / ' + segs + ' 已核准'}</span></div>`;
  }

  function rowActions(f) {
    const st = statusOf(f);
    const canProof = st.key === 'done' || st.key === 'review';
    return `
      <div class="row-acts">
        ${canProof ? `<a class="btn btn-sm btn-outline" href="proofread.html?file_id=${esc(f.id)}">校對 →</a>` : ''}
        ${canProof ? `<button class="btn btn-sm btn-secondary" data-export-sub="${esc(f.id)}" title="輸出字幕檔（SRT / VTT / TXT）"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v8M4 7l4 4 4-4M2 13h12"/></svg>字幕</button>` : ''}
        ${canProof ? `<button class="btn btn-sm btn-secondary" data-export-vid="${esc(f.id)}" title="輸出燒入字幕影片（MP4 / MXF / XDCAM）"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="12" height="10" rx="1"/><path d="M2 6h12M2 10h12M5 3v10M11 3v10"/></svg>影片</button>` : ''}
        <div class="menu-wrap">
          <button class="btn-icon" data-menu="${esc(f.id)}" title="更多"><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="3" r="1.4"/><circle cx="8" cy="8" r="1.4"/><circle cx="8" cy="13" r="1.4"/></svg></button>
        </div>
      </div>`;
  }

  /* ---- render: rows ---- */
  function renderRows() {
    const list = visibleFiles();
    const tbody = document.getElementById('rows');
    if (!list.length) {
      tbody.innerHTML = `<tr class="empty-row"><td colspan="7"><div class="empty-in">
        <div class="ei"><svg width="24" height="24" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="12" height="10" rx="1"/><path d="M2 6h12"/></svg></div>
        <div class="et">${query ? '冇符合「' + esc(query) + '」嘅檔案' : (firstLoad ? '載入中…' : '此分類冇檔案')}</div>
      </div></td></tr>`;
      syncBulk(); syncCheckAll();
      return;
    }
    tbody.innerHTML = list.map((f) => {
      const st = statusOf(f);
      const on = selected.has(f.id);
      const canProof = st.key === 'done' || st.key === 'review';
      return `<tr class="${on ? 'sel' : ''}" data-id="${esc(f.id)}">
        <td class="cell-check"><span class="chk ${on ? 'on' : ''}" data-check="${esc(f.id)}"><svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8.5l3.5 3.5L13 5"/></svg></span></td>
        <td class="cell-file">
          <div class="file-id">
            <div class="file-thumb"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1.5" y="3" width="13" height="10" rx="1.5"/><path d="M6.5 6l3.5 2-3.5 2z" fill="currentColor" stroke="none"/></svg></div>
            <div style="min-width:0;">
              <div class="file-name ${canProof ? 'link' : ''}" ${canProof ? `data-open="${esc(f.id)}"` : ''} title="${esc(f.original_name)}">${esc(f.original_name)}</div>
              <div class="file-sub">${esc(ext(f.original_name))} · ${esc(fmtSize(f.size))}</div>
            </div>
          </div>
        </td>
        <td>${langChips(f)}</td>
        <td>${segCell(f)}</td>
        <td><span class="badge ${st.cls}">${st.dot ? '<span class="dot"></span>' : ''}${st.label}</span></td>
        <td class="dim" style="font-size:12px;white-space:nowrap;">${esc(fmtRel(f.uploaded_at))}</td>
        <td>${rowActions(f)}</td>
      </tr>`;
    }).join('');

    // wire checkboxes
    tbody.querySelectorAll('[data-check]').forEach((el) => {
      el.onclick = (e) => { e.stopPropagation(); toggleSel(el.dataset.check); };
    });
    // wire name open
    tbody.querySelectorAll('[data-open]').forEach((el) => {
      el.onclick = () => { location.href = 'proofread.html?file_id=' + el.dataset.open; };
    });
    // wire row menus
    tbody.querySelectorAll('[data-menu]').forEach((el) => {
      el.onclick = (e) => { e.stopPropagation(); openMenu(el, el.dataset.menu); };
    });
    // wire export popups (字幕 / 影片) — logic lives in js/files-export.js
    tbody.querySelectorAll('[data-export-sub]').forEach((el) => {
      el.onclick = (e) => {
        e.stopPropagation();
        const f = FILES.find((x) => x.id === el.dataset.exportSub);
        if (f && window.FilesExport) FilesExport.openSubtitle(f);
      };
    });
    tbody.querySelectorAll('[data-export-vid]').forEach((el) => {
      el.onclick = (e) => {
        e.stopPropagation();
        const f = FILES.find((x) => x.id === el.dataset.exportVid);
        if (f && window.FilesExport) FilesExport.openVideo(f);
      };
    });
    syncBulk(); syncCheckAll();
  }

  /* ---- selection ---- */
  function toggleSel(id) {
    if (selected.has(id)) selected.delete(id); else selected.add(id);
    renderRows();
  }
  function syncCheckAll() {
    const vis = visibleFiles();
    const all = vis.length > 0 && vis.every((f) => selected.has(f.id));
    document.getElementById('checkAll').classList.toggle('on', all);
  }
  document.getElementById('checkAll').onclick = () => {
    const vis = visibleFiles();
    const all = vis.length > 0 && vis.every((f) => selected.has(f.id));
    if (all) vis.forEach((f) => selected.delete(f.id));
    else vis.forEach((f) => selected.add(f.id));
    renderRows();
  };

  /* ---- real backend calls ---- */
  function downloadSrt(id) {
    // GET /api/files/<id>/subtitle.srt — trigger a browser download via an <a>.
    const a = document.createElement('a');
    a.href = `/api/files/${encodeURIComponent(id)}/subtitle.srt`;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function deleteFile(id) {
    const r = await fetch(`/api/files/${encodeURIComponent(id)}`, { method: 'DELETE', credentials: 'same-origin' });
    if (!r.ok) {
      let msg = '刪除失敗';
      try { const j = await r.json(); if (j && j.error) msg = j.error; } catch (e) { /* ignore */ }
      throw new Error(msg);
    }
  }

  /* ---- bulk bar ---- */
  function syncBulk() {
    const slot = document.getElementById('bulkSlot');
    if (!selected.size) { slot.innerHTML = ''; return; }
    slot.innerHTML = `<div class="bulkbar">
      <span class="bb-count">已選 <b>${selected.size}</b> 個檔案</span>
      <span class="spacer"></span>
      <button class="btn btn-secondary btn-sm" id="bbDownload"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M8 11V3M8 11L5 8M8 11l3-3M3 13h10"/></svg>批次下載 SRT</button>
      <button class="btn btn-danger-ghost btn-sm" id="bbDelete"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4h10M6 4V3h4v1M5 4l.5 9h5L11 4"/></svg>刪除</button>
      <button class="btn btn-ghost btn-sm" id="bbClear">取消選取</button>
    </div>`;
    document.getElementById('bbClear').onclick = () => { selected.clear(); renderRows(); };

    document.getElementById('bbDownload').onclick = () => {
      const ids = Array.from(selected);
      // Stagger downloads slightly so the browser doesn't drop concurrent navigations.
      ids.forEach((id, i) => setTimeout(() => downloadSrt(id), i * 350));
      toast(`已開始下載 ${ids.length} 個 SRT`, 'info');
    };

    document.getElementById('bbDelete').onclick = async () => {
      const ids = Array.from(selected);
      if (!window.confirm(`確定刪除 ${ids.length} 個檔案？此操作無法復原。`)) return;
      let ok = 0, fail = 0;
      for (const id of ids) {
        try { await deleteFile(id); ok++; } catch (e) { fail++; }
      }
      selected.clear();
      await refresh();
      if (fail) toast(`已刪除 ${ok} 個，${fail} 個失敗`, 'error');
      else toast(`已刪除 ${ok} 個檔案`, 'info');
    };
  }

  /* ---- row dropdown menu ---- */
  let openMenuEl = null;
  function closeMenu() { if (openMenuEl) { openMenuEl.remove(); openMenuEl = null; } }
  function openMenu(anchor, id) {
    if (openMenuEl) { const was = openMenuEl.dataset.for === id; closeMenu(); if (was) return; }
    const f = FILES.find((x) => x.id === id);
    if (!f) return;
    const st = statusOf(f);
    const canProof = st.key === 'done' || st.key === 'review';
    const menu = document.createElement('div');
    menu.className = 'menu';
    menu.dataset.for = id;
    menu.innerHTML = `
      ${canProof ? `<button data-act="open"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4a1 1 0 011-1h3l1.5 2H13a1 1 0 011 1v6a1 1 0 01-1 1H3a1 1 0 01-1-1z"/></svg>打開</button>` : ''}
      ${canProof ? '<div class="sep"></div>' : ''}
      <button class="danger" data-act="delete"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4h10M6 4V3h4v1M5 4l.5 9h5L11 4"/></svg>刪除檔案</button>`;
    anchor.parentElement.appendChild(menu);
    openMenuEl = menu;
    menu.querySelectorAll('[data-act]').forEach((b) => {
      b.onclick = async (e) => {
        e.stopPropagation();
        const act = b.dataset.act;
        closeMenu();
        if (act === 'open') location.href = 'proofread.html?file_id=' + id;
        else if (act === 'delete') {
          if (!window.confirm(`確定刪除「${f.original_name}」？此操作無法復原。`)) return;
          try { await deleteFile(id); selected.delete(id); await refresh(); toast('已刪除檔案', 'info'); }
          catch (err) { toast(err.message || '刪除失敗', 'error'); }
        }
      };
    });
  }
  // Close on any outside click. Capture phase, so row buttons that call
  // e.stopPropagation() (checkboxes, 字幕/影片 export, another row's 三點)
  // can no longer strand an open menu on screen.
  document.addEventListener('click', (e) => {
    if (!openMenuEl) return;
    const t = e.target;
    if (openMenuEl.contains(t)) return; // menu item clicks close themselves
    // Clicking the SAME row's 三點 button must fall through to its own
    // toggle handler (close), not close-here-then-reopen-there.
    const btn = t && t.closest ? t.closest('[data-menu]') : null;
    if (btn && btn.dataset.menu === openMenuEl.dataset.for) return;
    closeMenu();
  }, true);

  /* ---- toolbar wires ---- */
  document.getElementById('search').oninput = (e) => { query = e.target.value; renderRows(); };
  document.getElementById('sort').onchange = (e) => { sortKey = e.target.value; renderRows(); };
  // Upload lives on the dashboard (the cross-language upload popup). Redirect there.
  document.getElementById('uploadBtn').onclick = () => { location.href = 'index.html'; };
  document.getElementById('refreshBtn').onclick = () => { refresh(); toast('已重新整理', 'info'); };
  document.querySelectorAll('th.sortable').forEach((th) => {
    th.onclick = () => {
      sortKey = th.dataset.sort;
      const sel = document.getElementById('sort');
      if ([...sel.options].some((o) => o.value === sortKey)) sel.value = sortKey;
      document.querySelectorAll('th.sortable').forEach((x) => x.classList.toggle('sorted', x === th));
      renderRows();
    };
  });

  /* ---- user chip (real /api/me) ---- */
  async function loadUser() {
    try {
      const r = await fetch('/api/me', { credentials: 'same-origin' });
      if (!r.ok) return;
      const j = await r.json();
      const name = j.username || j.name;
      if (name) document.getElementById('userChipName').textContent = name;
      if (j.is_admin) {
        const al = document.getElementById('adminLink');
        if (al) al.style.display = 'inline';
      }
    } catch (e) { /* keep default */ }
  }

  /* ---- toast ---- */
  function toast(msg, kind = 'success') {
    const el = document.createElement('div');
    el.className = 'toast ' + kind;
    const ic = kind === 'error'
      ? '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="8" cy="8" r="6.5"/><path d="M8 5v4M8 11h.01"/></svg>'
      : (kind === 'info'
        ? '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="8" cy="8" r="6.5"/><path d="M8 7.5v4M8 5h.01"/></svg>'
        : '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8.5l3.5 3.5L13 5"/></svg>');
    el.innerHTML = ic + '<span>' + esc(msg) + '</span>';
    document.getElementById('toasts').appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .25s'; setTimeout(() => el.remove(), 260); }, 2200);
  }

  /* ---- data fetch + render ---- */
  async function refresh() {
    try {
      const r = await fetch('/api/files', { credentials: 'same-origin' });
      if (r.status === 401) { location.href = 'login.html'; return; }
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      FILES = Array.isArray(j.files) ? j.files : [];
      // Drop selections for files that no longer exist.
      const ids = new Set(FILES.map((f) => f.id));
      for (const id of Array.from(selected)) if (!ids.has(id)) selected.delete(id);
      firstLoad = false;
      renderStats();
      renderTabs();
      renderRows();
    } catch (e) {
      if (firstLoad) {
        firstLoad = false;
        document.getElementById('rows').innerHTML =
          `<tr class="empty-row"><td colspan="7"><div class="empty-in">
            <div class="ei"><svg width="24" height="24" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="6.5"/><path d="M8 5v4M8 11h.01"/></svg></div>
            <div class="et">無法連接後端 — ${esc(e.message || '請稍後重試')}</div>
          </div></td></tr>`;
      }
      // On a transient poll error, keep the last good render.
    }
  }

  /* ---- boot ---- */
  if (window.FilesExport) FilesExport.init({ toast });
  loadUser();
  const _logoutBtn = document.getElementById('userChipLogout');
  if (_logoutBtn) _logoutBtn.addEventListener('click', () => { if (window.logout) window.logout(); });
  refresh();
  setInterval(refresh, POLL_MS);
})();
