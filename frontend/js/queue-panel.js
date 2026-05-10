// frontend/js/queue-panel.js — R5 Phase 1 job queue panel.
// Polls /api/queue every 3s. Owner sees own queued+running jobs; admin
// sees all active. Each row shows position/type/owner/status with a cancel
// button on queued jobs.
async function refreshQueue() {
  try {
    const r = await fetch("/api/queue", {credentials: "same-origin"});
    if (!r.ok) return;
    const jobs = await r.json();
    renderQueueRows(jobs);
  } catch (e) { /* silent */ }
}

function renderQueueRows(jobs) {
  const panel = document.getElementById("queuePanel");
  if (!panel) return;
  if (jobs.length === 0) {
    panel.innerHTML = '<div style="color:var(--text-dim);padding:8px;font-size:12px;">無進行中嘅工作</div>';
    return;
  }
  panel.innerHTML = jobs.map(j => `
    <div data-testid="queue-row" id="queueRow-${j.id}"
         style="display:flex;gap:8px;padding:6px 8px;border-bottom:1px solid var(--border);font-size:12px;">
      <span>#${j.position + 1}</span>
      <span style="color:var(--text-mid);min-width:60px;">${j.type}</span>
      <span style="flex:1;">${j.owner_username}</span>
      <span style="color:${j.status === 'running' ? 'var(--accent)' : 'var(--text-dim)'};">${j.status}</span>
      ${j.status === 'queued' ? `
        <button data-testid="queue-cancel" id="queueCancelBtn-${j.id}"
                onclick="cancelJob('${j.id}')"
                style="background:none;border:0;color:var(--text-dim);cursor:pointer;">×</button>
      ` : ''}
    </div>
  `).join("");
}

async function cancelJob(jobId) {
  if (!confirm("取消呢個工作？")) return;
  await fetch(`/api/queue/${jobId}`, {method: "DELETE", credentials: "same-origin"});
  refreshQueue();
}

window.refreshQueue = refreshQueue;
window.cancelJob = cancelJob;

// Auto-refresh every 3s
setInterval(refreshQueue, 3000);
refreshQueue();
