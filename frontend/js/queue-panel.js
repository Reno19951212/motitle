// frontend/js/queue-panel.js — shared cross-account job queue panel.
//
// Polls /api/queue every 3s as a fallback, but every connected SocketIO
// client also receives 'queue_changed' broadcasts on every job state
// transition so updates feel instant across tabs and accounts.
//
// Phase C additions: per-row progress bar driven by 'pipeline_progress'
// socket event. Cache seeded from /api/queue.progress_pct for cold-start.

const _progressCache = new Map() // file_id → {pct, stage_label, stage_state, pipeline_kind, stages, stage_index}

function _onPipelineProgress(payload) {
  if (!payload || !payload.file_id) return
  _progressCache.set(payload.file_id, {
    pct: payload.pct,
    stage_label: payload.stage_label,
    stage_state: payload.stage_state,
    pipeline_kind: payload.pipeline_kind,
    stages: Array.isArray(payload.stages) ? payload.stages : null,
    stage_index: payload.stage_index != null ? payload.stage_index : null,
  })
  _patchRowProgress(payload.file_id)

  // C2: done-state auto-hide — remove row 2s after completion
  if (payload.stage_state === 'done' && payload.pct === 100) {
    setTimeout(() => {
      const row = document.querySelector(`[data-file-id="${CSS.escape(payload.file_id)}"]`)
      if (row && row.dataset.jobStatus === 'done') row.remove()
    }, 2000)
  }
}

function _patchRowProgress(fileId) {
  const snap = _progressCache.get(fileId)
  if (!snap) return
  document.querySelectorAll(`[data-file-id="${CSS.escape(fileId)}"]`).forEach((row) => {
    _updateRowProgressUI(row, snap)
  })
}

function _updateRowProgressUI(row, snap) {
  // If we have step-diagram data, replace the progress area with the diagram
  const progressEl = row.querySelector('.qp-progress')
  if (progressEl && snap.stages && snap.stages.length > 0 && typeof window.renderStepDiagram === 'function') {
    progressEl.innerHTML = window.renderStepDiagram(snap.stages, snap.stage_index, snap.stage_state, snap.pct)
    return
  }
  // Fallback: legacy bar/spinner/pct
  const pctEl = row.querySelector('.qp-pct')
  const barFillEl = row.querySelector('.qp-bar-fill')
  const labelEl = row.querySelector('.qp-stage-label')
  const spinnerEl = row.querySelector('.qp-spinner')
  const barEl = row.querySelector('.qp-bar')
  const isIdle = snap.stage_state === 'idle' || snap.pct === null || snap.pct === undefined
  if (pctEl) pctEl.textContent = isIdle ? '' : `${snap.pct}%`
  if (barFillEl) barFillEl.style.width = isIdle ? '0%' : `${snap.pct}%`
  if (spinnerEl) spinnerEl.style.display = isIdle ? 'inline-block' : 'none'
  if (barEl) barEl.style.display = isIdle ? 'none' : 'block'
  if (labelEl && snap.stage_label) labelEl.textContent = snap.stage_label
}

async function refreshQueue() {
  try {
    const r = await fetch('/api/queue', { credentials: 'same-origin' })
    if (!r.ok) return
    const jobs = await r.json()
    renderQueueRows(jobs)
  } catch (e) {
    /* silent */
  }
}

const _TYPE_LABEL = { asr: '轉錄', translate: '翻譯', render: '渲染' }
const _STATUS_LABEL = {
  queued: '排隊',
  running: '進行中',
  done: '完成',
  failed: '失敗',
  cancelled: '已取消',
}
const _STATUS_COLOR = {
  queued: 'var(--text-dim)',
  running: 'var(--accent)',
  done: 'var(--ok, #10b981)',
  failed: 'var(--err, #ef4444)',
  cancelled: 'var(--text-dim)',
}

function _escape(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  )
}

function _truncate(s, n) {
  s = String(s || '')
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

function renderQueueRows(jobs) {
  const panel = document.getElementById('queuePanel')
  if (!panel) return
  if (!jobs || jobs.length === 0) {
    panel.innerHTML =
      '<div style="color:var(--text-dim);padding:8px;font-size:12px;">無進行中嘅工作</div>'
    return
  }

  // Seed progress cache from /api/queue. The backend resets its snapshot at
  // each job-start, so the server is authoritative for the *stage*: when the
  // stage or pipeline_kind changes (a new/different job for this file) we
  // overwrite the stale in-memory entry. Within the same stage we keep the
  // higher pct so the 3s poll never drags a live socket update backwards (and
  // still advances when no socket is connected). Without this, re-running a
  // file showed the *previous* job's stage because the cache was preferred
  // over the fresh server value.
  jobs.forEach((j) => {
    if (!j.file_id) return
    const srv = {
      pct: j.progress_pct != null ? j.progress_pct : null,
      stage_label: j.stage_label || null,
      stage_state: j.stage_state || (j.status === 'queued' ? 'idle' : 'active'),
      pipeline_kind: j.pipeline_kind || null,
      stages: Array.isArray(j.stages) ? j.stages : null,
      stage_index: j.stage_index != null ? j.stage_index : null,
    }
    const prev = _progressCache.get(j.file_id)
    const stageChanged =
      !prev ||
      prev.stage_index !== srv.stage_index ||
      prev.pipeline_kind !== srv.pipeline_kind
    if (stageChanged || (srv.pct != null && (prev.pct == null || srv.pct > prev.pct))) {
      _progressCache.set(j.file_id, srv)
    }
  })

  panel.innerHTML = jobs
    .map((j) => {
      const isActive = j.status === 'queued' || j.status === 'running'
      const typeLbl = _TYPE_LABEL[j.type] || j.type
      const statusLbl = _STATUS_LABEL[j.status] || j.status
      const statusColor = _STATUS_COLOR[j.status] || 'var(--text-dim)'
      const opacity = isActive ? '1' : '0.65'
      const fileLabel = _escape(_truncate(j.file_name || j.file_id || '', 28))
      const showCancel = j.status === 'queued' || j.status === 'running'

      // Derive progress snap for this row's initial render
      const snap = _progressCache.get(j.file_id) || {
        pct: j.progress_pct != null ? j.progress_pct : null,
        stage_label: j.stage_label || null,
        stage_state: j.stage_state || (j.status === 'queued' ? 'idle' : null),
        pipeline_kind: j.pipeline_kind || null,
        stages: Array.isArray(j.stages) ? j.stages : null,
        stage_index: j.stage_index != null ? j.stage_index : null,
      }
      const isIdle = snap.stage_state === 'idle' || snap.pct === null || snap.pct === undefined
      const showBarBlock = isIdle ? 'none' : 'block'
      const showSpinnerInline = isIdle ? 'inline-block' : 'none'
      const initialPct = snap.pct != null ? snap.pct : 0
      const initialPctText = snap.pct != null ? `${snap.pct}%` : ''
      // Stage label for the legacy (no step-diagram) progress area. Do NOT
      // fall back to the status text — the row now has a dedicated status
      // column, so a fallback would render the status twice (e.g. "排隊 … 排隊"
      // on a queued render row).
      const labelOrFallback = _escape(snap.stage_label || '')

      // Build the progress area: step diagram if stages available, else legacy bar
      const hasStages = snap.stages && snap.stages.length > 0 && typeof window.renderStepDiagram === 'function'
      const progressAreaInner = hasStages
        ? window.renderStepDiagram(snap.stages, snap.stage_index, snap.stage_state, snap.pct)
        : `<span class="qp-stage-label" style="font-size:11px;color:var(--text-mid);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${labelOrFallback}</span>
            <div class="qp-progress-line" style="display:flex;align-items:center;gap:6px;">
              <div class="qp-bar" style="flex:1;height:4px;background:rgba(255,255,255,0.08);border-radius:2px;overflow:hidden;display:${showBarBlock};">
                <div class="qp-bar-fill" style="height:100%;width:${initialPct}%;background:var(--accent);transition:width 0.3s ease;"></div>
              </div>
              <span class="qp-spinner" style="display:${showSpinnerInline};width:10px;height:10px;border:1.5px solid var(--text-dim);border-top-color:var(--accent);border-radius:50%;animation:qpSpin 0.8s linear infinite;flex-shrink:0;"></span>
              <span class="qp-pct" style="font-size:11px;color:var(--accent);min-width:30px;text-align:right;">${_escape(initialPctText)}</span>
            </div>`

      const cancelBtn = showCancel
        ? `<button data-testid="queue-cancel" id="queueCancelBtn-${j.id}"
                   onclick="cancelJob('${j.id}')" title="取消"
                   style="background:none;border:0;color:var(--text-dim);cursor:pointer;padding:0 2px;flex-shrink:0;">×</button>`
        : ''
      // Two-line row: the queue panel is only ~278px wide. A single flex line
      // forced the status text to wrap vertically ("進/行/中") and crushed the
      // owner to "a…". Line 1 carries identity (pos / type / filename / owner /
      // ×); line 2 carries the step-diagram + a nowrap status, each with room
      // to render correctly (incl. the 5-stage V6 diagram).
      return `
        <div data-testid="queue-row" id="queueRow-${j.id}"
             data-file-id="${_escape(j.file_id || '')}"
             data-job-status="${j.status}"
             style="display:flex;flex-direction:column;gap:3px;padding:6px 8px;border-bottom:1px solid var(--border);font-size:12px;opacity:${opacity};">
          <div style="display:flex;gap:6px;align-items:center;min-width:0;">
            <span style="color:var(--text-dim);min-width:14px;text-align:right;flex-shrink:0;">${
              isActive ? '#' + (j.position + 1) : '·'
            }</span>
            <span style="color:var(--text-mid);flex-shrink:0;">${typeLbl}</span>
            <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_escape(
              j.file_name || j.file_id || ''
            )}">${fileLabel}</span>
            <span style="color:var(--text-dim);max-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex-shrink:0;" title="${_escape(
              j.owner_username || ''
            )}">${_escape(j.owner_username || '')}</span>
            ${cancelBtn}
          </div>
          <div style="display:flex;gap:6px;align-items:center;min-width:0;">
            <div class="qp-progress" style="flex:1;min-width:0;display:flex;flex-direction:column;gap:2px;overflow:hidden;">
              ${progressAreaInner}
            </div>
            <span style="color:${statusColor};white-space:nowrap;flex-shrink:0;">${statusLbl}</span>
          </div>
        </div>
      `
    })
    .join('')
}

async function cancelJob(jobId) {
  // No native confirm() — the dialog's own "Cancel" button is labeled 取消,
  // identical to the verb the user just clicked, which trapped users into
  // dismissing the action they actually wanted. Cancelling a queued/running
  // job is reversible (just re-enqueue), so a one-shot click is safe.
  const r = await fetch(`/api/queue/${jobId}`, {
    method: 'DELETE',
    credentials: 'same-origin',
  })
  if (!r.ok) {
    const msg = '取消失敗：' + r.status
    if (window.showToast) window.showToast(msg, 'error')
    else alert(msg)
    return
  }
  if (r.status === 202) {
    if (window.showToast) window.showToast('取消中…', 'info')
    else if (window.toast) window.toast('取消中...')
  } else {
    if (window.showToast) window.showToast('已取消', 'success')
  }
  refreshQueue()
  if (window.refreshFiles) refreshFiles()
}

async function retryFile(fileId) {
  const r = await fetch(`/api/files/${fileId}/transcribe`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  if (!r.ok) {
    // R6 audit E batch — surface body.error so retry failures aren't opaque.
    let detail = `HTTP ${r.status}`
    try {
      const body = await r.json()
      if (body && body.error) detail = body.error
    } catch (_) {}
    const msg = `重試失敗：${detail}`
    if (window.showToast) window.showToast(msg, 'error')
    else alert(msg)
    return
  }
  if (window.showToast) window.showToast('已重新提交', 'success')
  refreshQueue()
  if (window.refreshFiles) refreshFiles()
}

let _queueTimerId = null
// R6 audit M5/M6 — track the socket instance we last bound to. When the
// dashboard's restartService swaps window.socket for a new instance, we
// need to re-attach the 'queue_changed' listener; pre-fix a boolean flag
// blocked the rebind and the new socket's events were silently dropped.
let _boundSocket = null
let _bindRetryTimer = null

function _bindSocket() {
  // Use the page's existing socket if main app already created one
  // (dashboard sets window.socket). Otherwise create our own connection
  // (e.g. on /proofread.html where no global socket exists).
  let s = typeof window !== 'undefined' ? window.socket : null
  if (!s && typeof io === 'function') {
    s = io(window.location.origin, {
      transports: ['polling', 'websocket'],
      withCredentials: true,
    })
    if (typeof window !== 'undefined') window.__queuePanelSocket = s
  }
  if (!s) return // no Socket.IO client loaded on this page
  if (s === _boundSocket) return // already attached to this exact instance
  // Detach from any previous socket so we don't accumulate stale handlers
  // when restartService swaps the connection.
  if (_boundSocket && typeof _boundSocket.off === 'function') {
    try { _boundSocket.off('queue_changed', refreshQueue) } catch (_) {}
    try { _boundSocket.off('pipeline_progress', _onPipelineProgress) } catch (_) {}
  }
  s.on('queue_changed', refreshQueue)
  s.on('pipeline_progress', _onPipelineProgress)
  _boundSocket = s
  // Force a fresh poll right after rebind to reconcile any events missed
  // while the socket was reconnecting.
  refreshQueue()
}

function startQueueRefresh() {
  if (_queueTimerId !== null) return
  refreshQueue()
  _queueTimerId = setInterval(refreshQueue, 3000)
  _bindSocket()
  // window.socket may be created (or swapped) AFTER queue-panel.js runs;
  // poll for changes for the lifetime of the page (every 1s, cheap).
  if (_bindRetryTimer === null) {
    _bindRetryTimer = setInterval(_bindSocket, 1000)
  }
}

function stopQueueRefresh() {
  if (_queueTimerId !== null) {
    clearInterval(_queueTimerId)
    _queueTimerId = null
  }
  if (_bindRetryTimer !== null) {
    clearInterval(_bindRetryTimer)
    _bindRetryTimer = null
  }
}

window.retryFile = retryFile
window.refreshQueue = refreshQueue
window.cancelJob = cancelJob
window.startQueueRefresh = startQueueRefresh
window.stopQueueRefresh = stopQueueRefresh

// Phase D test introspection helpers
if (typeof window !== 'undefined') {
  window.__progressCacheGet = (fid) => _progressCache.get(fid)
  window.__pipelineProgressHandler = _onPipelineProgress
}

startQueueRefresh()
