# user.html Redesign — Design Spec

**Date:** 2026-06-05
**Status:** Approved (brainstorming) → pending implementation plan
**Scope:** Frontend redesign of `frontend/user.html` + `frontend/js/user.js`, plus a small backend addition (per-user remarks).

---

## 1. Goal

Redesign the 帳戶 (Account) page to match the Dashboard (`index.html`) and Proofread (`proofread.html`) design language and layout conventions, driven by the actual ways the page is used. Replace the flat stacked-card layout and native browser dialogs with a polished, in-page experience. Add a per-user **備註 / Remarks** capability.

The page keeps doing exactly what it does today — **my account** (view identity, change password) and, for admins, **user management** (create / reset-password / toggle-admin / delete) and **audit log** — plus the new remarks field. No pipeline, ASR, or MT logic is touched.

---

## 2. Current state (what we're replacing)

`frontend/user.html` + `frontend/js/user.js`:

- Three `<section class="ucard">` stacked vertically: `#accountSection`, `#userMgmtSection` (admin), `#auditSection` (admin). The two admin sections are `hidden` by default and revealed in `loadMe()` when `me.is_admin`.
- Account section: a single avatar SVG + `#accountUsername` + `#accountRole` badge + change-password form (`#changePwForm`, `#changePwMsg`).
- User management: create form (`#adminUserCreateForm`) + table (`#adminUserList`). Per-row actions call `resetPassword()`, `toggleAdmin()`, `deleteUser()`.
- Audit log: table (`#adminAuditList`) — details rendered as raw `JSON.stringify` inside `<pre>`.

**Problems:**
1. Native `confirm()` / `prompt()` / `alert()` for delete, reset-password, and all error reporting — completely off-brand, no toast system.
2. Audit details are an unreadable raw-JSON `<pre>` dump; actor shown as a bare numeric `actor_user_id`.
3. Flat vertical stack with no hierarchy; admin sections dumped below the account card.
4. Sparse account card.

**Constraint — preserve all DOM ids that `user.js` drives** (or update `user.js` in lockstep):
`#accountUsername #accountRole #changePwForm #changePwMsg #adminUserCreateForm #adminUserList #adminAuditList #userMgmtSection #auditSection #userChipName`.
Since this redesign rewrites `user.js` too, ids may be restructured **as long as HTML and JS stay consistent** and the backend contract is unchanged (except the new remarks endpoints).

---

## 3. Approved design decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Overall layout | **Left tab navigation** — a 212px inner nav rail (inside `.b-main`, to the right of the global 64px rail) with two groups: 帳戶 and 管理·ADMIN. Content area shows one pane at a time. |
| D2 | Content width | **Full width** — content fills the remaining area (no `max-width` centering). |
| D3 | Admin destructive/edit actions | **Inline row expansion** — delete-confirm and reset-password expand a row directly under the target table row. No native dialogs, no center modal. |
| D4 | Audit log presentation | **Structured rows + expandable rich detail** — replace `<pre>` JSON with timestamp / actor (resolved to username + avatar) / colour-coded action badge / target, and a click-to-expand two-column detail block. Search box + action-type filter chips. |
| D5 | Remarks feature | **Per-user remarks**, admin-editable, **user can view their own**. Backend gains a `remarks` column + endpoint; `/api/me` returns the caller's remarks. |
| D6 | Feedback | **Toast system** (ported from `index.html` / `proofread.html`) replaces every `alert()`. Inline `#changePwMsg`-style messages kept where already present. |

---

## 4. Visual / design language (reuse, don't reinvent)

All tokens come verbatim from the shared design system already in `user.html`'s `:root` (identical to Dashboard/Proofread): `--bg #0a0a0f`, surfaces `--surface/-2/-3`, `--border`, `--accent #6c63ff`, `--accent-2 #a78bfa`, status colours, `--font-ui` (Inter + Noto Sans TC), `--font-mono` (JetBrains Mono). Reused component patterns: `.b-rail`, `.b-topbar`, `.page-id`, `.hpill` health cluster, `.user-chip`, `.kbd`, `.toast`/`.toast-stack`, badge/`btn` conventions, `.ucard` card with gradient lead bar.

**New, page-local components** (named to avoid collision):
- `.u-body` — `grid-template-columns: 212px 1fr` (inner nav + content).
- `.u-nav` / `.u-nav-group` / `.u-nav-item` (active = accent-soft + left accent bar, mirrors `.rail-btn.on`). Each admin nav item shows a mono count badge.
- `.u-content` / `.u-pane` (only `.on` pane visible; subtle fade-in).
- `.acct-*` identity card with avatar, `.role-pill`, and `.meta-chip` row (ID / 角色 / 建立).
- `.utable` polished: per-user colour avatar (initial), username + role pill, **remarks column**, mono timestamp, `.iconbtn` action group.
- `.expand-row` variants: `.expand-danger` (delete confirm), `.expand-edit` (reset password), `.expand-remark` (remarks textarea editor).
- Audit: `.audit-toolbar` (search + filter chips), `.audit-item` (grid row, caret rotates on open), `.audit-detail-row` → `.audit-detail-grid` of `.adetail-block` key-value cards.

---

## 5. Information architecture & panes

```
┌ global rail (64px, unchanged 5-item) ┐ ┌ b-main ─────────────────────────────────┐
│ M / 主頁 / 檔案 / 校對 / 術語表 / [User]│ │ topbar: page-id「帳戶/Account」· search · │
│                                       │ │         health pills · user-chip(avatar) │
│                                       │ ├──────────────┬──────────────────────────┤
│                                       │ │ u-nav 212px  │ u-content (full width)    │
│                                       │ │ 帳戶          │  [active pane]            │
│                                       │ │  • 我的帳戶   │                           │
│                                       │ │ 管理·ADMIN    │                           │
│                                       │ │  • 用戶管理 N │                           │
│                                       │ │  • 審計日誌 N │                           │
└───────────────────────────────────────┘ └──────────────┴──────────────────────────┘
```

### Pane 1 — 我的帳戶 (always present)
Two-column `.acct-grid` (collapses to 1 col < 1100px):
- **身份 · Identity** card: avatar, username (`#accountUsername`), role pill (`#accountRole`), meta-chips: ID / 角色 / 建立日期.
  - **Remarks display (D5):** if the signed-in user has a non-empty `remarks`, show a read-only "備註" line/chip here (sourced from `/api/me`). Hidden when empty. Users cannot edit their own remarks here.
- **更改密碼 · Change Password** card: `#changePwForm` (old + new password, rule hint, submit, `#changePwMsg`). Unchanged contract; restyled with field labels + focus ring.

### Pane 2 — 用戶管理 (admin only)
- **新增用戶** card: `#adminUserCreateForm` (username, password, is_admin checkbox, submit). Password rule hint retained.
- **Users table** (`#adminUserList` tbody preserved):
  - Columns: **ID · 用戶(avatar+name+role pill) · 備註Remarks · 建立時間 · 操作**.
  - Action group (`.iconbtn`, tooltip on each): 備註 ✎ · 重設密碼 🔒 · 升/降權限 ↑↓ · 刪除 🗑.
  - The signed-in admin's own row is marked (`.me`, "你自己") and its delete is disabled client-side (backend already 403s self-delete).
  - **Inline expansions (D3):**
    - 刪除 → `.expand-danger` row: "⚠ 確定刪除「{username}」？此操作無法復原" + 取消 / 確認刪除.
    - 重設密碼 → `.expand-edit` row: password input + 取消 / 確認重設 (client-side `< 8` guard before POST).
    - 備註 → `.expand-remark` row: textarea (≤500 chars, live counter) + 取消 / 儲存備註.
  - Only one expansion open per row at a time; opening one closes the others on that row.

### Pane 3 — 審計日誌 (admin only)
- **Toolbar:** search input (client-side filter over actor/action/target) + action-type filter chips (全部 / 建立 / 更新 / 刪除). Both filter the already-fetched rows; no new backend params required.
- **Rows** (`#adminAuditList` container preserved): each row = `ts` (formatted) · actor (resolved `actor_user_id` → username + avatar, see §6) · colour-coded action badge · target (`target_kind` + `target_id`, with username if it's a user target) · caret.
- **Expandable detail (D4):** click a row → two-column `.adetail-grid`:
  - **操作摘要 · Summary** block: operation (action), actor, target, ts.
  - **詳情 · Details** block: the `details` object rendered as key-value rows. A "複製 JSON" / "查看原始" affordance shows the raw `details` JSON for power users.
  - **Honesty clamp:** only fields the backend actually stores are shown. The audit schema is `{id, ts, actor_user_id, action, target_kind, target_id, details}` — there is **no ip_addr / user_agent / HTTP-status** stored, so those are NOT displayed (they were illustrative-only in the mockup). If `details` is null/empty, the Details block shows "— 無額外詳情 —".

---

## 6. Backend changes (minimal, additive)

### 6.1 Remarks column + endpoints (D5)
- **Schema:** add `remarks TEXT NOT NULL DEFAULT ''` to the `users` table. `init_db()` runs an idempotent guarded `ALTER TABLE users ADD COLUMN remarks ...` (wrapped to ignore "duplicate column" so existing DBs migrate on startup).
- **`auth/users.py`:**
  - `list_all_users()` and `_row_to_user()` include `remarks`.
  - New `update_remarks(db_path, user_id, remarks)` (validates length ≤ 500; trims).
  - `get_user_by_id()` returns `remarks`.
- **`auth/admin.py`:** new route `PATCH /api/admin/users/<int:user_id>/remarks` (`@admin_required`) → body `{remarks}`; updates, logs `log_audit(action="user.update_remarks", target_kind="user", target_id=user_id, details={"remarks": remarks})`; returns `{ok, remarks}`. 404 if user absent, 400 if remarks > 500 chars.
- **`auth/routes.py`:** `/api/me` response gains `"remarks": <caller's remarks>` (read-only; user sees own only). The `R5_AUTH_BYPASS` branch returns `"remarks": ""`.

### 6.2 No other backend change
Audit actor-name resolution is done **client-side** (the admin page already fetches `/api/admin/users`, so it builds an `id → username` map) — no backend join, no new audit fields. List endpoints, decorators, password policy, last-admin guards: untouched.

---

## 7. Frontend module structure

`frontend/js/user.js` is rewritten but stays a single vanilla module (no build step — project rule). Internal organisation, small focused functions:

- **bootstrap:** `loadMe()` → fill identity, own-remarks display, reveal admin nav items + panes, `loadUsers()`, `loadAudit()`.
- **tabs:** `switchPane(name)` toggles `.u-pane.on` + `.u-nav-item.on`.
- **account:** change-password handler (existing contract) → inline `#changePwMsg` + toast.
- **users:** `renderUsers()` (builds rows incl. avatar/role-pill/remarks/actions), `expandRow(userId, kind)` (danger/edit/remark — mutually exclusive), `confirmDelete()`, `confirmReset()`, `saveRemarks()`, `toggleAdmin()`. All replace native dialogs with inline rows + toast.
- **audit:** `renderAudit(rows, userMap)`, `filterAudit()` (search + chip), `toggleAuditDetail(id)`.
- **toast:** ported `showToast(msg, kind)` + `.toast-stack`.
- **escaping:** an `escapeHtml()` helper for all interpolated user/remarks/audit strings (XSS guard — remarks are free text).

Immutability: render functions rebuild from fetched data; no in-place mutation of shared state objects (follow project coding-style rule).

---

## 8. Edge cases & error handling

- **Non-admin user:** admin nav items + panes never rendered; only 我的帳戶 visible. `/api/me` 401 → redirect `/login.html` (existing behaviour kept).
- **Remarks:** empty allowed (clears); >500 chars blocked client-side + 400 server-side; HTML-escaped on display.
- **Self-actions:** own delete disabled (UI) + 403 (backend); last-admin demote/delete → backend 403 surfaced as toast.
- **Reset password < 8 chars:** client guard + backend 400 → toast with the friendly message.
- **Audit actor not in user map** (e.g. deleted user, or `actor_user_id = 0` for `login_failed`): fall back to `#<id>` / "系統".
- **Fetch failures:** every fetch handles non-ok → toast; no silent swallow.

---

## 9. Testing

- **Backend (pytest):** remarks column migration is idempotent; `update_remarks` length validation; `PATCH …/remarks` happy-path + 404 + 400 + non-admin 403; `/api/me` includes remarks; `user.update_remarks` audit row written. Extend `tests/test_admin_users.py`.
- **Frontend (Playwright, existing harness):** admin sees 3 nav items; non-admin sees 1; inline delete confirm flow; reset-password inline flow; remarks edit persists + shows toast; audit row expands to detail; native `confirm/prompt/alert` are gone (no dialog handlers fire). Preserve existing `data-testid` hooks (`admin-user-create-submit`, `admin-user-row`, `admin-user-delete`) and add ones for the new controls.
- **Manual:** curl `PATCH /api/admin/users/<id>/remarks`; verify `/api/me` remarks; visual pass on the three panes at ≥1100px and < 1100px.

---

## 10. Out of scope

- No change to the global 5-item rail, auth/session model, password policy, or any pipeline/ASR/MT code.
- No pagination/server-side search for audit (client-side filter over the existing ≤100/500 rows is sufficient for this single-tenant LAN tool).
- No avatar uploads (avatars are generated initials).

---

## 11. Pre-implementation note — worktree base

The active worktree (`.claude/worktrees/feat+user-html-frontend`) was created from a **fresh** base (origin/main) and does **not** contain `frontend/user.html`, `frontend/js/user.js`, or `backend/auth/` — those live on the `feat/glossary-v2` branch of the main checkout. **Step 0 of the implementation plan must rebase/reset this worktree's branch onto `feat/glossary-v2`** (or recreate the worktree from it) so the redesign targets the real files. This is a setup step, not part of the feature itself.

---

## 12. Documentation updates required on completion

Per CLAUDE.md "Mandatory documentation updates": update CLAUDE.md (REST endpoints table — add `PATCH /api/admin/users/<id>/remarks`; `/api/me` remarks field; user.html description), README.md (Traditional Chinese, user-facing), and docs/PRD.md status markers. A matching implementation plan lives at `docs/superpowers/plans/2026-06-05-user-html-redesign-plan.md`.
