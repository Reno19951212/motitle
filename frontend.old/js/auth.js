// frontend/js/auth.js — R5 Phase 1 auth helper.
// fetchMe(): hydrates window.authState.user; redirects to /login.html on 401.
// logout(): POST /logout, redirect.
// R6 audit E2: install a global fetch wrapper that, on any 401 response,
// redirects to /login.html?next=<current path>. Pre-fix, only fetchMe()
// handled 401 — every other endpoint just surfaced a generic error and
// the user stayed on a broken page until they reloaded.
window.authState = { user: null };

(function installFetchAuthInterceptor() {
  if (window.__authInterceptorInstalled) return;
  window.__authInterceptorInstalled = true;
  const _origFetch = window.fetch.bind(window);
  let _redirecting = false;
  window.fetch = async function(input, init) {
    const resp = await _origFetch(input, init);
    if (resp.status === 401 && !_redirecting) {
      // Skip the redirect for the login endpoint itself + the readiness
      // probe — both are expected to potentially 401 / 200 without auth.
      const url = typeof input === "string" ? input : (input && input.url) || "";
      const isAuthEndpoint = /\/(login|logout|api\/me|api\/ready|api\/health)\b/.test(url);
      if (!isAuthEndpoint && location.pathname !== "/login.html") {
        _redirecting = true;
        const next = encodeURIComponent(location.pathname + location.search);
        location.href = "/login.html?next=" + next;
      }
    }
    return resp;
  };
})();

async function fetchMe() {
  try {
    const r = await fetch("/api/me", {credentials: "same-origin"});
    if (!r.ok) {
      window.location.href = "/login.html";
      return null;
    }
    const u = await r.json();
    window.authState.user = u;
    return u;
  } catch (e) {
    window.location.href = "/login.html";
    return null;
  }
}

async function logout() {
  await fetch("/logout", {method: "POST", credentials: "same-origin"});
  window.location.href = "/login.html";
}

window.fetchMe = fetchMe;
window.logout = logout;
