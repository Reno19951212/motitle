// Shared licence module: fetch status, render, copy install-id, activate.
// Used by license.html (wall) and user.html (授權 tab).
window.MoTitleLicense = (function () {
  async function fetchStatus() {
    const r = await fetch('/api/license', { credentials: 'same-origin' });
    if (!r.ok) return { state: 'none', unlocked: false };
    return r.json();
  }

  async function activate(token) {
    const r = await fetch('/api/license/activate', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: token.trim() }),
    });
    const body = await r.json().catch(() => ({}));
    return { ok: r.ok, body };
  }

  function describe(st) {
    if (st.state === 'active') return st.expires_at
      ? `已啟用 · 剩 ${st.days_left} 日`
      : '已啟用 · 永久授權';
    if (st.state === 'grace') return `寬限期 · 已過期 ${Math.abs(st.days_left)} 日，請盡快續費`;
    if (st.state === 'expired') return '已過期，請續費';
    if (st.state === 'wrong_machine') return '此 license 不屬於本機';
    if (st.state === 'invalid') return 'license 無效';
    return '未啟用';
  }

  // Render a grace/near-expiry banner into <body> on any page.
  async function maybeBanner() {
    const st = await fetchStatus();
    if (st.state === 'grace' || (st.unlocked && st.days_left !== null && st.days_left <= 14)) {
      const b = document.createElement('div');
      b.style.cssText = 'background:#b00020;color:#fff;padding:8px 16px;text-align:center;font-weight:600';
      b.textContent = `⚠️ ${describe(st)}`;
      document.body.prepend(b);
    }
    return st;
  }

  return { fetchStatus, activate, describe, maybeBanner };
})();
