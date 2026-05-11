// frontend/js/queue-panel.js — shared cross-account job queue panel.
//
// Polls /api/queue every 3s as a fallback, but every connected SocketIO
// client also receives 'queue_changed' broadcasts on every job state
// transition so updates feel instant across tabs and accounts.
async function refreshQueue() {
  try {
    const r = await fetch("/api/queue", { credentials: "same-origin" });
    if (!r.ok) return;
    const jobs = await r.json();
    renderQueueRows(jobs);
  } catch (e) {
    /* silent */
  }
}

const _TYPE_LABEL = { asr: "轉錄", translate: "翻譯", render: "渲染" };
const _STATUS_LABEL = {
  queued: "排隊",
  running: "進行中",
  done: "完成",
  failed: "失敗",
  cancelled: "已取消",
};
const _STATUS_COLOR = {
  queued: "var(--text-dim)",
  running: "var(--accent)",
  done: "var(--ok, #10b981)",
  failed: "var(--err, #ef4444)",
  cancelled: "var(--text-dim)",
};

function _escape(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function _truncate(s, n) {
  s = String(s || "");
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function renderQueueRows(jobs) {
  const panel = document.getElementById("queuePanel");
  if (!panel) return;
  if (!jobs || jobs.length === 0) {
    panel.innerHTML =
      '<div style="color:var(--text-dim);padding:8px;font-size:12px;">無進行中嘅工作</div>';
    return;
  }
  panel.innerHTML = jobs
    .map((j) => {
      const isActive = j.status === "queued" || j.status === "running";
      const typeLbl = _TYPE_LABEL[j.type] || j.type;
      const statusLbl = _STATUS_LABEL[j.status] || j.status;
      const statusColor = _STATUS_COLOR[j.status] || "var(--text-dim)";
      const opacity = isActive ? "1" : "0.65";
      const fileLabel = _escape(_truncate(j.file_name || j.file_id || "", 28));
      const showCancel = j.status === "queued" || j.status === "running";

      return `
        <div data-testid="queue-row" id="queueRow-${j.id}"
             data-job-status="${j.status}"
             style="display:flex;gap:8px;padding:6px 8px;border-bottom:1px solid var(--border);font-size:12px;align-items:center;opacity:${opacity};">
          <span style="color:var(--text-dim);min-width:14px;text-align:right;">${
            isActive ? "#" + (j.position + 1) : "·"
          }</span>
          <span style="color:var(--text-mid);min-width:42px;">${typeLbl}</span>
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_escape(
            j.file_name || j.file_id || ""
          )}">${fileLabel}</span>
          <span style="color:var(--text-dim);max-width:60px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_escape(
            j.owner_username || ""
          )}">${_escape(j.owner_username || "")}</span>
          <span style="color:${statusColor};">${statusLbl}</span>
          ${
            showCancel
              ? `<button data-testid="queue-cancel" id="queueCancelBtn-${j.id}"
                       onclick="cancelJob('${j.id}')"
                       title="取消"
                       style="background:none;border:0;color:var(--text-dim);cursor:pointer;padding:0 2px;">×</button>`
              : ""
          }
        </div>
      `;
    })
    .join("");
}

async function cancelJob(jobId) {
  // No native confirm() — the dialog's own "Cancel" button is labeled 取消,
  // identical to the verb the user just clicked, which trapped users into
  // dismissing the action they actually wanted. Cancelling a queued/running
  // job is reversible (just re-enqueue), so a one-shot click is safe.
  const r = await fetch(`/api/queue/${jobId}`, {
    method: "DELETE",
    credentials: "same-origin",
  });
  if (!r.ok) {
    const msg = "取消失敗：" + r.status;
    if (window.showToast) window.showToast(msg, "error");
    else alert(msg);
    return;
  }
  if (r.status === 202) {
    if (window.showToast) window.showToast("取消中…", "info");
    else if (window.toast) window.toast("取消中...");
  } else {
    if (window.showToast) window.showToast("已取消", "success");
  }
  refreshQueue();
  if (window.refreshFiles) refreshFiles();
}

async function retryFile(fileId) {
  const r = await fetch(`/api/files/${fileId}/transcribe`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!r.ok) {
    alert("重試失敗：" + r.status);
    return;
  }
  refreshQueue();
  if (window.refreshFiles) refreshFiles();
}

let _queueTimerId = null;
let _socketBound = false;

function _bindSocket() {
  if (_socketBound) return;
  // Use the page's existing socket if main app already created one
  // (dashboard sets window.socket). Otherwise create our own connection
  // (e.g. on /proofread.html where no global socket exists).
  let s = typeof window !== "undefined" ? window.socket : null;
  if (!s && typeof io === "function") {
    s = io(window.location.origin, {
      transports: ["polling", "websocket"],
      withCredentials: true,
    });
  }
  if (!s) return; // no Socket.IO client loaded on this page
  s.on("queue_changed", refreshQueue);
  _socketBound = true;
}

function startQueueRefresh() {
  if (_queueTimerId !== null) return;
  refreshQueue();
  _queueTimerId = setInterval(refreshQueue, 3000);
  _bindSocket();
  // window.socket may be created AFTER queue-panel.js runs (dashboard
  // builds it later). Retry binding for ~5s.
  let tries = 0;
  const bindRetry = setInterval(() => {
    _bindSocket();
    if (_socketBound || ++tries > 20) clearInterval(bindRetry);
  }, 250);
}

function stopQueueRefresh() {
  if (_queueTimerId !== null) {
    clearInterval(_queueTimerId);
    _queueTimerId = null;
  }
}

window.retryFile = retryFile;
window.refreshQueue = refreshQueue;
window.cancelJob = cancelJob;
window.startQueueRefresh = startQueueRefresh;
window.stopQueueRefresh = stopQueueRefresh;

startQueueRefresh();
