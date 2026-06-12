/* ============================================================
   MoTitle — 校對頁詞彙表掃描→剔選→逐項 AI 套用 modal (GlossaryReview)

   output_lang 檔專用。掃描純機械（zero LLM），套用逐項串行（⌘F promise chain 模式）。
   Spec: docs/superpowers/specs/2026-06-12-proofread-glossary-review-design.md §3.2

   依賴 proofread.html 全域（classic script 共享 global scope）：
   API_BASE, fileId, fileInfo, segs, escapeHtml, showToast,
   setCursor, loadSegments, _outputLangLabel
   ============================================================ */
(function () {
  'use strict';

  let scanData = null;       // 最近一次 POST glossary-preview response
  let applying = false;
  let _rowTexts = {};        // {`${lang}:${idx}` -> text} 本地 cache（套用後更新 expected_text 用）

  // ── modal 元素取得 ──────────────────────────────────────────
  function _el(id) { return document.getElementById(id); }

  function _overlay() { return _el('grOverlay'); }
  function _body()    { return _el('grBody'); }

  // ── 開啟掃描 ────────────────────────────────────────────────
  async function openScan() {
    if (!fileId) { showToast('未載入檔案', 'error'); return; }
    const overlay = _overlay();
    if (!overlay) { console.error('GlossaryReview: #grOverlay not found'); return; }

    // 重置 body 為 loading 狀態，先開 modal
    _body().innerHTML = '<div class="ga-progress">掃描中…</div>';
    _el('grSubtitle').textContent = '';
    _el('grApplyBtn').textContent = '套用選中 (0)';
    overlay.classList.add('open');

    try {
      const r = await fetch(`${API_BASE}/api/files/${fileId}/glossary-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${r.status}`);
      }
      scanData = await r.json();
      _buildRowTextCache();
      _renderModal();
    } catch (e) {
      _body().innerHTML = `<div class="ga-progress" style="color:var(--error,#f38ba8);">掃描失敗：${escapeHtml(e.message)}</div>`;
      showToast(`掃描失敗: ${e.message}`, 'error');
    }
  }

  // ── 建立 row text cache（expected_text 用）──────────────────
  function _buildRowTextCache() {
    _rowTexts = {};
    if (!scanData) return;
    (scanData.tracks || []).forEach(t => {
      (t.items || []).forEach(it => {
        const key = `${t.lang}:${it.idx}`;
        if (!_rowTexts[key]) _rowTexts[key] = it.row_text || _rowTextFromSegs(t.lang, it.idx);
      });
    });
  }

  function _rowTextFromSegs(lang, idx) {
    if (!Array.isArray(segs) || idx >= segs.length) return '';
    const s = segs[idx];
    if (!s) return '';
    // output_lang: by_lang[lang].text is canonical
    if (s.by_lang && s.by_lang[lang] && typeof s.by_lang[lang].text === 'string') return s.by_lang[lang].text;
    // mirror fields e.g. yue_text / en_text / zh_text
    if (typeof s[`${lang}_text`] === 'string') return s[`${lang}_text`];
    // last-resort: en_text or text for first lang
    if (s.en_text) return s.en_text;
    return s.text || '';
  }

  function _rowTextFor(lang, idx) {
    return _rowTexts[`${lang}:${idx}`] || _rowTextFromSegs(lang, idx);
  }

  function _setRowText(lang, idx, text) {
    _rowTexts[`${lang}:${idx}`] = text;
  }

  // ── 渲染 modal 內容 ─────────────────────────────────────────
  function _renderModal() {
    if (!scanData) return;
    const tracks = scanData.tracks || [];
    const totals = scanData.totals || {};

    // Header subtitle
    const totalFix = totals.fix || 0;
    const totalOk = totals.ok || 0;
    _el('grSubtitle').textContent =
      `${totals.rows || 0} 段 · ${tracks.length} 條語言軌 · 搵到 ${totalFix} 處候選、${totalOk} 處已符合`;

    _body().innerHTML = tracks.map((t, ti) => {
      const langLabel = _langLabel(t.lang);
      const dir = (t.mode === 'mt')
        ? `按原文命中詞條，檢查${escapeHtml(langLabel)}字幕有冇用標準譯名`
        : '將字幕入面嘅別名統一做標準名';
      const fixes = t.items ? t.items.filter(it => it.kind === 'fix') : [];
      const oks   = t.items ? t.items.filter(it => it.kind === 'ok')  : [];
      const inapp = (t.inapplicable_glossaries || []).length
        ? `<div class="trk-inapp">⚠ ${t.inapplicable_glossaries.map(escapeHtml).join('、')} 唔適用於呢條軌（原文語言唔對應）</div>`
        : '';

      const fixRows = fixes.length
        ? `<div class="ga-section-head"><label class="ga-select-all">
            <input type="checkbox" data-sa="${ti}" onchange="_grSelectAll(this,${ti})">
            <span>待修正 (${fixes.length}) — 全選</span>
           </label></div>`
          + fixes.map((it, ii) => _fixRowHtml(t, ti, ii, it)).join('')
        : '';

      const okRows = oks.length
        ? `<div class="ga-section-head ga-section-head-ok">已符合 (${oks.length}) — 純顯示</div>`
          + oks.map(it => _okRowHtml(t, it)).join('')
        : '';

      const emptyMsg = (!fixes.length && !oks.length)
        ? `<div style="padding:8px 0;font-size:12px;color:var(--text-dim);">呢條軌冇命中任何詞條</div>` : '';

      return `<div class="trk" data-ti="${ti}">
        <div class="trk-head">
          <span class="trk-lang">${escapeHtml(langLabel)}</span>
          <span class="trk-dir">${escapeHtml(dir)}</span>
          <span class="trk-count">${fixes.length} 待修正 · ${oks.length} 已符合</span>
        </div>
        ${inapp}${emptyMsg}${fixRows}${okRows}
      </div>`;
    }).join('');

    _wireFooter();
    _updateCount();
  }

  function _langLabel(lang) {
    // fileInfo.languages is [{role:'first'|'second', lang:'yue'|'en'|..., label:'...'}]
    if (fileInfo && Array.isArray(fileInfo.languages)) {
      const entry = fileInfo.languages.find(l => l.lang === lang);
      if (entry) return `${entry.label || entry.lang} · ${(entry.lang || '').toUpperCase()}`;
    }
    const FALLBACKS = { yue: '口語廣東話 · YUE', cmn: '中文書面語 · CMN',
                        zh: '中文 · ZH', en: '英文 · EN', ja: '日文 · JA' };
    return FALLBACKS[lang] || (lang ? lang.toUpperCase() : '—');
  }

  function _fixRowHtml(t, ti, ii, it) {
    const rowText = _rowTextFor(t.lang, it.idx);
    const checked = it.approved ? '' : 'checked';
    const badge = it.approved
      ? '<span class="ga-row-badge">已批核 — 唔會自動剔</span>' : '';
    return `<div class="ga-row" data-ti="${ti}" data-ii="${ii}">
      <input type="checkbox" class="gr-ck" ${checked} data-ti="${ti}">
      <div class="ga-row-body">
        <div class="ga-row-term">
          ${escapeHtml(it.alias)} → ${escapeHtml(it.canonical)}
          <span class="gl-src-tag">${escapeHtml(it.glossary || '')}</span>
          ${badge}
          <span class="seg-link" data-idx="${it.idx}" onclick="_grJumpSeg(${it.idx})">#${it.idx + 1} ${_fmtTc(it.start)}</span>
          <span class="gr-state"></span>
        </div>
        <div class="ga-row-line">字幕：${_hl(rowText, it.alias)}</div>
        <div class="ga-row-line ga-hint warn">⚠ AI 將判斷修改位置 · 套用唔會改批核狀態</div>
      </div>
    </div>`;
  }

  function _okRowHtml(t, it) {
    const rowText = _rowTextFor(t.lang, it.idx);
    return `<div class="ga-row matched" style="opacity:0.55;">
      <div class="ga-row-body">
        <div class="ga-row-term">
          ${escapeHtml(it.canonical)}
          <span class="gl-src-tag">${escapeHtml(it.glossary || '')}</span>
          <span class="seg-link" onclick="_grJumpSeg(${it.idx})">#${it.idx + 1} ${_fmtTc(it.start)}</span>
        </div>
        <div class="ga-row-line">字幕：${_hlOk(rowText, it.canonical)}</div>
      </div>
    </div>`;
  }

  // ── highlight helpers ───────────────────────────────────────
  function _hl(text, alias) {
    if (!alias || !text) return escapeHtml(text || '');
    const idx = text.indexOf(alias);
    if (idx < 0) return escapeHtml(text);
    return escapeHtml(text.slice(0, idx))
      + `<mark class="hl-alias">${escapeHtml(alias)}</mark>`
      + escapeHtml(text.slice(idx + alias.length));
  }

  function _hlOk(text, canonical) {
    if (!canonical || !text) return escapeHtml(text || '');
    const idx = text.indexOf(canonical);
    if (idx < 0) return escapeHtml(text);
    return escapeHtml(text.slice(0, idx))
      + `<mark class="hl-zh">${escapeHtml(canonical)}</mark>`
      + escapeHtml(text.slice(idx + canonical.length));
  }

  function _fmtTc(start) {
    if (start == null) return '';
    const t = Math.max(0, Math.round(start));
    const m = Math.floor(t / 60);
    const s = t % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  }

  // ── segment jump ────────────────────────────────────────────
  function _grJumpSeg(idx) {
    if (typeof setCursor === 'function') setCursor(idx, true);
  }

  // ── select-all per track ────────────────────────────────────
  window._grSelectAll = function (saEl, ti) {
    const checked = saEl.checked;
    document.querySelectorAll(`#grBody .ga-row[data-ti="${ti}"] .gr-ck`)
      .forEach(cb => { cb.checked = checked; });
    _updateCount();
  };

  function _updateCount() {
    const n = document.querySelectorAll('#grBody .gr-ck:checked').length;
    const btn = _el('grApplyBtn');
    if (btn) btn.textContent = `套用選中 (${n})`;
    // per-track select-all indeterminate
    document.querySelectorAll('#grBody [data-sa]').forEach(sa => {
      const ti = sa.dataset.sa;
      const all = document.querySelectorAll(`#grBody .ga-row[data-ti="${ti}"] .gr-ck`);
      const checked = Array.from(all).filter(c => c.checked).length;
      sa.indeterminate = checked > 0 && checked < all.length;
      sa.checked = checked > 0 && checked === all.length;
    });
  }

  // ── apply selected (串行 promise chain) ─────────────────────
  async function _applySelected() {
    if (applying) return;
    applying = true;
    const applyBtn = _el('grApplyBtn');
    const cancelBtn = _el('grCancelBtn');
    const rescanBtn = _el('grRescanBtn');
    const closeBtn = _el('grCloseBtn');
    if (applyBtn) applyBtn.disabled = true;
    if (cancelBtn) cancelBtn.disabled = true;
    if (rescanBtn) rescanBtn.disabled = true;
    if (closeBtn) closeBtn.disabled = true;

    const rowEls = Array.from(document.querySelectorAll('#grBody .ga-row[data-ti][data-ii]'))
      .filter(r => r.querySelector('.gr-ck') && r.querySelector('.gr-ck').checked);

    let ok = 0, fail = 0;
    for (const rowEl of rowEls) {
      const ti = parseInt(rowEl.dataset.ti, 10);
      const ii = parseInt(rowEl.dataset.ii, 10);
      if (!scanData || !scanData.tracks[ti]) continue;
      const t = scanData.tracks[ti];
      const fixes = (t.items || []).filter(it => it.kind === 'fix');
      const it = fixes[ii];
      if (!it) continue;

      const st = rowEl.querySelector('.gr-state');
      if (st) { st.textContent = '…'; st.className = 'gr-state'; }

      const expectedText = _rowTextFor(t.lang, it.idx);

      try {
        const r = await fetch(`${API_BASE}/api/files/${fileId}/glossary-apply-item`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            idx: it.idx,
            lang: t.lang,
            alias: it.alias,
            canonical: it.canonical,
            source: it.source || it.alias,
            glossary_id: it.glossary_id || null,
            entry_id: it.entry_id || null,
            glossary: it.glossary || '',
            expected_text: expectedText,
          }),
        });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
        _setRowText(t.lang, it.idx, body.text);  // 更新本地 cache
        if (st) { st.textContent = '✓'; st.className = 'gr-state ok'; }
        const ck = rowEl.querySelector('.gr-ck');
        if (ck) ck.checked = false;
        rowEl.classList.add('applied-ok');
        ok++;
      } catch (e) {
        if (st) { st.textContent = `✗ ${e.message}`; st.className = 'gr-state err'; }
        fail++;
      }
      _updateCount();
    }

    applying = false;
    if (applyBtn) applyBtn.disabled = false;
    if (cancelBtn) cancelBtn.disabled = false;
    if (rescanBtn) rescanBtn.disabled = false;
    if (closeBtn) closeBtn.disabled = false;

    showToast(`已套用 ${ok} 項${fail ? `，${fail} 項失敗` : ''}`, fail ? 'error' : 'success');
    if (typeof loadSegments === 'function') await loadSegments();
  }

  // ── footer + close wiring ───────────────────────────────────
  function _wireFooter() {
    const applyBtn = _el('grApplyBtn');
    const cancelBtn = _el('grCancelBtn');
    const rescanBtn = _el('grRescanBtn');
    const closeBtn  = _el('grCloseBtn');
    const overlay   = _overlay();

    if (applyBtn && !applyBtn._grWired) {
      applyBtn.addEventListener('click', _applySelected);
      applyBtn._grWired = true;
    }
    if (cancelBtn && !cancelBtn._grWired) {
      cancelBtn.addEventListener('click', _close);
      cancelBtn._grWired = true;
    }
    if (rescanBtn && !rescanBtn._grWired) {
      rescanBtn.addEventListener('click', openScan);
      rescanBtn._grWired = true;
    }
    if (closeBtn && !closeBtn._grWired) {
      closeBtn.addEventListener('click', _close);
      closeBtn._grWired = true;
    }
    if (overlay && !overlay._grEscWired) {
      overlay.addEventListener('keydown', e => {
        if (e.key === 'Escape' && !applying) _close();
      });
      overlay._grEscWired = true;
    }
  }

  function _close() {
    if (applying) return;
    const overlay = _overlay();
    if (overlay) overlay.classList.remove('open');
  }

  // ── expose global ───────────────────────────────────────────
  window.GlossaryReview = { openScan };

  // Wire Esc from proofread.html keyboard handler (supplement)
  document.addEventListener('keydown', e => {
    const overlay = _overlay();
    if (e.key === 'Escape' && overlay && overlay.classList.contains('open') && !applying) {
      _close();
    }
  });

})();
