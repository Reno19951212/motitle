/* ============================================================
   MoTitle — 檔案庫輸出 popups (FilesExport)

   Two per-row export modals for Files.html, mirroring the dashboard's
   export features against the SAME backend endpoints:

   字幕輸出 — GET /api/files/<id>/subtitle.{srt,vtt,txt}?source=&order=
   影片輸出 — POST /api/render {file_id, format, subtitle_source,
              bilingual_order} → poll GET /api/renders/<id> →
              GET /api/renders/<id>/download
              (+ POST /api/files/<id>/translations/approve-all on the
               unapproved-segments confirm, same flow as the dashboard)

   Usage:
     FilesExport.init({ toast })          // optional toast(msg, kind)
     FilesExport.openSubtitle(file)       // file = /api/files entry
     FilesExport.openVideo(file)
   ============================================================ */
(function (global) {
  'use strict';

  const POLL_MS = 1500;

  let _toast = function () {};
  const state = {
    file: null, mode: null,          // 'subtitle' | 'video'
    source: '', order: 'en_top', format: 'mp4',
    renderId: null, pollTimer: null, awaitingConfirm: false,
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  /* ---- styles (injected once; reuses Files.html design tokens) ---- */
  let stylesInjected = false;
  function injectStyles() {
    if (stylesInjected) return;
    stylesInjected = true;
    const el = document.createElement('style');
    el.textContent = `
      .fx-overlay { position: fixed; inset: 0; z-index: 150; display: flex; align-items: center; justify-content: center; background: rgba(5,5,10,0.6); backdrop-filter: blur(3px); }
      .fx-panel { width: min(480px, calc(100vw - 40px)); max-height: calc(100vh - 80px); overflow: auto; background: var(--surface); border: 1px solid var(--border-strong); border-radius: 14px; box-shadow: var(--shadow); padding: 18px; }
      .fx-head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
      .fx-head .fx-title { font-size: 15px; font-weight: 800; }
      .fx-head .fx-x { margin-left: auto; width: 28px; height: 28px; border-radius: 7px; color: var(--text-dim); display: grid; place-items: center; }
      .fx-head .fx-x:hover { background: var(--surface-2); color: var(--text); }
      .fx-fname { font-size: 12px; color: var(--text-dim); margin-bottom: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .fx-sec { font-size: 10.5px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-dim); margin: 14px 0 8px; }
      .fx-seg { display: flex; flex-wrap: wrap; gap: 6px; }
      .fx-seg button { padding: 7px 12px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface-2); font-size: 12.5px; font-weight: 600; color: var(--text-mid); }
      .fx-seg button:hover { border-color: var(--border-strong); color: var(--text); }
      .fx-seg button.on { background: var(--accent-soft); border-color: var(--accent-ring); color: var(--accent-2); }
      .fx-order { display: none; align-items: center; gap: 8px; margin-top: 10px; }
      .fx-order.visible { display: flex; }
      .fx-order .fx-order-lab { font-size: 12px; color: var(--text-dim); }
      .fx-fmts { display: flex; flex-direction: column; gap: 6px; }
      .fx-fmt { display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface-2); text-align: left; }
      .fx-fmt:hover { border-color: var(--accent-ring); background: var(--surface-3); }
      .fx-fmt.on { background: var(--accent-soft); border-color: var(--accent-ring); }
      .fx-fmt .fb { flex: 0 0 58px; text-align: center; font-family: var(--font-mono); font-size: 11px; font-weight: 800; padding: 3px 0; border-radius: 6px; background: var(--surface-3); border: 1px solid var(--border-strong); color: var(--accent-2); }
      .fx-fmt .fd { font-size: 12.5px; color: var(--text-mid); }
      .fx-status { display: none; margin-top: 14px; padding: 10px 12px; border-radius: 10px; background: var(--surface-2); border: 1px solid var(--border); font-size: 12.5px; color: var(--text-mid); }
      .fx-status.visible { display: block; }
      .fx-status.error { border-color: rgba(239,68,68,0.4); color: var(--danger); }
      .fx-status.success { border-color: rgba(34,197,94,0.4); color: var(--success); }
      .fx-confirm-actions { display: flex; gap: 8px; margin-top: 8px; }
      .fx-foot { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
    `;
    document.head.appendChild(el);
  }

  /* ---- language options (descriptor-driven, legacy EN/ZH fallback) ---- */
  function langOptions(f) {
    const langs = Array.isArray(f.languages) ? f.languages : [];
    const first = langs.find((l) => l.role === 'first');
    const second = langs.find((l) => l.role === 'second');
    if (first || second) {
      const opts = [];
      if (first) opts.push({ value: 'first', label: `第一語言 · ${first.label || '原文'}（${(first.lang || '').toUpperCase()}）` });
      if (second) {
        opts.push({ value: 'second', label: `第二語言 · ${second.label || '譯文'}（${(second.lang || '').toUpperCase()}）` });
        opts.push({ value: 'bilingual', label: '雙語對照' });
      }
      return { opts, def: second ? 'bilingual' : 'first', hasSecond: !!second };
    }
    return {
      opts: [
        { value: 'en', label: '原文（EN）' },
        { value: 'zh', label: '譯文（ZH）' },
        { value: 'bilingual', label: '雙語對照' },
      ],
      def: 'bilingual',
      hasSecond: true,
    };
  }

  /* ---- modal scaffolding ---- */
  function closeModal() {
    if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
    state.awaitingConfirm = false;
    const ov = document.getElementById('fxOverlay');
    if (ov) ov.remove();
    document.removeEventListener('keydown', onEsc);
  }
  function onEsc(e) { if (e.key === 'Escape') closeModal(); }

  function openModal(file, mode) {
    injectStyles();
    closeModal();
    state.file = file;
    state.mode = mode;
    const lo = langOptions(file);
    state.source = lo.def;
    state.order = file.bilingual_order || 'en_top';
    state.format = 'mp4';
    state.renderId = null;

    const ov = document.createElement('div');
    ov.id = 'fxOverlay';
    ov.className = 'fx-overlay';
    ov.innerHTML = `<div class="fx-panel" role="dialog" aria-modal="true">
      <div class="fx-head">
        <span class="fx-title">${mode === 'subtitle' ? '字幕檔輸出' : '影片輸出（燒入字幕）'}</span>
        <button class="fx-x" id="fxClose" title="關閉">✕</button>
      </div>
      <div class="fx-fname" title="${esc(file.original_name)}">${esc(file.original_name)}</div>

      <div class="fx-sec">字幕內容</div>
      <div class="fx-seg" id="fxLangSeg">
        ${lo.opts.map((o) => `<button data-src="${o.value}" class="${o.value === state.source ? 'on' : ''}">${esc(o.label)}</button>`).join('')}
      </div>
      <div class="fx-order" id="fxOrderRow">
        <span class="fx-order-lab">次序</span>
        <div class="fx-seg">
          <button data-order="en_top" class="${state.order === 'en_top' ? 'on' : ''}">第一語言在上</button>
          <button data-order="zh_top" class="${state.order === 'zh_top' ? 'on' : ''}">第二語言在上</button>
        </div>
      </div>

      <div class="fx-sec">${mode === 'subtitle' ? '字幕檔格式（撳即下載）' : '影片格式'}</div>
      <div class="fx-fmts" id="fxFmts">
        ${mode === 'subtitle' ? `
          <button class="fx-fmt" data-dl="srt"><span class="fb">SRT</span><span class="fd">SubRip · 通用字幕</span></button>
          <button class="fx-fmt" data-dl="vtt"><span class="fb">VTT</span><span class="fd">WebVTT · 網頁字幕</span></button>
          <button class="fx-fmt" data-dl="txt"><span class="fb">TXT</span><span class="fd">純文字（無時碼）</span></button>
        ` : `
          <button class="fx-fmt on" data-format="mp4"><span class="fb">MP4</span><span class="fd">H.264 · 通用播放</span></button>
          <button class="fx-fmt" data-format="mxf"><span class="fb">MXF</span><span class="fd">ProRes · 廣播級</span></button>
          <button class="fx-fmt" data-format="mxf_xdcam_hd422"><span class="fb">XDCAM</span><span class="fd">MPEG-2 422 · 電視台標準</span></button>
        `}
      </div>

      <div class="fx-status" id="fxStatus"></div>

      <div class="fx-foot">
        ${mode === 'video' ? `
          <button class="btn btn-danger-ghost btn-sm" id="fxCancelRender" style="display:none;">取消渲染</button>
          <button class="btn btn-primary" id="fxStart">開始渲染</button>
        ` : ''}
        <button class="btn btn-ghost" id="fxDismiss">關閉</button>
      </div>
    </div>`;
    document.body.appendChild(ov);

    ov.addEventListener('click', (e) => { if (e.target === ov) closeModal(); });
    document.getElementById('fxClose').onclick = closeModal;
    document.getElementById('fxDismiss').onclick = closeModal;
    document.addEventListener('keydown', onEsc);

    // language seg
    document.querySelectorAll('#fxLangSeg [data-src]').forEach((b) => {
      b.onclick = () => {
        state.source = b.dataset.src;
        document.querySelectorAll('#fxLangSeg [data-src]').forEach((x) => x.classList.toggle('on', x === b));
        syncOrderRow();
      };
    });
    // order seg
    document.querySelectorAll('#fxOrderRow [data-order]').forEach((b) => {
      b.onclick = () => {
        state.order = b.dataset.order;
        document.querySelectorAll('#fxOrderRow [data-order]').forEach((x) => x.classList.toggle('on', x === b));
      };
    });
    syncOrderRow();

    if (mode === 'subtitle') {
      document.querySelectorAll('#fxFmts [data-dl]').forEach((b) => {
        b.onclick = () => downloadSubtitle(b.dataset.dl);
      });
    } else {
      document.querySelectorAll('#fxFmts [data-format]').forEach((b) => {
        b.onclick = () => {
          state.format = b.dataset.format;
          document.querySelectorAll('#fxFmts [data-format]').forEach((x) => x.classList.toggle('on', x === b));
        };
      });
      document.getElementById('fxStart').onclick = startRender;
      document.getElementById('fxCancelRender').onclick = cancelRender;
    }
  }

  function syncOrderRow() {
    document.getElementById('fxOrderRow').classList.toggle('visible', state.source === 'bilingual');
  }

  function setStatus(msg, tone) {
    const el = document.getElementById('fxStatus');
    if (!el) return;
    el.textContent = msg || '';
    el.classList.remove('error', 'success');
    if (tone === 'error') el.classList.add('error');
    if (tone === 'success') el.classList.add('success');
    el.classList.toggle('visible', !!msg);
  }

  /* ---- 字幕輸出 ---- */
  function downloadSubtitle(fmt) {
    const q = `?source=${encodeURIComponent(state.source)}&order=${encodeURIComponent(state.order)}`;
    const a = document.createElement('a');
    a.href = `/api/files/${encodeURIComponent(state.file.id)}/subtitle.${fmt}${q}`;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
    _toast(`已開始下載 ${fmt.toUpperCase()}`, 'info');
  }

  /* ---- 影片輸出 ---- */
  async function startRender() {
    const f = state.file;
    const btn = document.getElementById('fxStart');

    // Unapproved-segments gate — same rule as the dashboard (approval is a
    // translation concept; EN-only renders skip it).
    if (!state.awaitingConfirm && state.source !== 'en') {
      const total = f.segment_count || 0;
      const approved = f.approved_count || 0;
      if (total > 0 && approved < total) {
        state.awaitingConfirm = true;
        const el = document.getElementById('fxStatus');
        el.innerHTML = `⚠ 仲有 <b>${total - approved}</b> 段未批核 — 繼續會自動批核全部再渲染。
          <div class="fx-confirm-actions">
            <button class="btn btn-secondary btn-sm" id="fxConfirmGo">確認，繼續渲染</button>
            <a class="btn btn-ghost btn-sm" href="proofread.html?file_id=${esc(f.id)}">去校對頁</a>
          </div>`;
        el.classList.remove('error', 'success');
        el.classList.add('visible');
        document.getElementById('fxConfirmGo').onclick = async () => {
          try {
            const r = await fetch(`/api/files/${encodeURIComponent(f.id)}/translations/approve-all`, {
              method: 'POST', credentials: 'same-origin',
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            startRender();
          } catch (e) {
            setStatus(`批核失敗：${e.message || '網絡錯誤'}`, 'error');
            state.awaitingConfirm = false;
          }
        };
        return;
      }
    }

    btn.disabled = true;
    btn.textContent = '渲染中…';
    setStatus('開始渲染，請稍候…');

    const body = { file_id: f.id, format: state.format, subtitle_source: state.source };
    if (state.source === 'bilingual') body.bilingual_order = state.order;
    try {
      const r = await fetch('/api/render', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
      if (data.warning_missing_zh > 0) {
        _toast(`⚠ ${data.warning_missing_zh} 段未翻譯，會用原文替代渲染`, 'info');
      }
      state.renderId = data.render_id;
      document.getElementById('fxCancelRender').style.display = '';
      pollRender(data.render_id);
    } catch (e) {
      setStatus(`渲染失敗：${e.message || '網絡錯誤'}`, 'error');
      btn.disabled = false;
      btn.textContent = '重試';
    }
  }

  function renderFinished(btnText) {
    if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
    const btn = document.getElementById('fxStart');
    const cb = document.getElementById('fxCancelRender');
    if (cb) cb.style.display = 'none';
    if (btn) { btn.disabled = false; btn.textContent = btnText; }
  }

  function pollRender(renderId) {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(async () => {
      try {
        const r = await fetch(`/api/renders/${encodeURIComponent(renderId)}`, { credentials: 'same-origin' });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
        if (d.status === 'done') {
          renderFinished('再渲染一次');
          setStatus('渲染完成 ✓', 'success');
          const fmts = document.getElementById('fxFmts');
          const dl = document.createElement('a');
          dl.className = 'btn btn-primary';
          dl.style.cssText = 'display:flex;justify-content:center;margin-top:10px;';
          dl.href = `/api/renders/${encodeURIComponent(renderId)}/download`;
          dl.download = '';
          dl.textContent = '💾 下載影片';
          fmts.parentElement.insertBefore(dl, document.getElementById('fxStatus'));
        } else if (d.status === 'cancelled') {
          renderFinished('重試');
          setStatus('已取消');
        } else if (d.status === 'error') {
          renderFinished('重試');
          setStatus(`渲染失敗：${d.error || '未知錯誤'}`, 'error');
        } else if (typeof d.progress === 'number') {
          setStatus(`渲染中… ${Math.round(d.progress)}%`);
        }
      } catch (e) {
        renderFinished('重試');
        setStatus(`渲染狀態查詢失敗：${e.message || '網絡錯誤'}`, 'error');
      }
    }, POLL_MS);
  }

  async function cancelRender() {
    if (!state.renderId) return;
    try {
      const r = await fetch(`/api/renders/${encodeURIComponent(state.renderId)}`, {
        method: 'DELETE', credentials: 'same-origin',
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
      renderFinished('重試');
      setStatus('已取消');
      _toast('已取消渲染', 'info');
    } catch (e) {
      _toast(`取消失敗：${e.message || '網絡錯誤'}`, 'error');
    }
  }

  global.FilesExport = {
    init(opts) { if (opts && typeof opts.toast === 'function') _toast = opts.toast; },
    openSubtitle(file) { openModal(file, 'subtitle'); },
    openVideo(file) { openModal(file, 'video'); },
  };
})(window);
