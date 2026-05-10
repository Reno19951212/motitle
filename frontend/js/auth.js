// frontend/js/auth.js — R5 Phase 1 auth helper.
// fetchMe(): hydrates window.authState.user; redirects to /login.html on 401.
// logout(): POST /logout, redirect.
window.authState = { user: null };

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
