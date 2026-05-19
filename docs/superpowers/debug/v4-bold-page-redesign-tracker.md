# Bold variant redesign tracker (feat/frontend-redesign)

**Branch base**: `feat/frontend-redesign` @ commit `10469e2`
**Started**: 2026-05-19
**Goal**: Extend Dashboard's Bold design language to 5 remaining pages with full Playwright verification.

## Status table

| Iter | Page | Route | Status | Commits | Playwright spec | Backend gaps |
|---|---|---|---|---|---|---|
| 1 | Timeline (Proofread) | `/proofread/:fileId` | fixed | `2b9a441` + `450a83d` + `2882c14` | `tests-e2e/bold-proofread.spec.ts` (7 tests, all pass) | none |
| 2 | ASR Profile | `/asr_profiles` | fixed | (this branch) — see Iter 2 section below | `tests-e2e/bold-asr-profile.spec.ts` (5 tests, all pass) | none |
| 3 | MT Profile | `/mt_profiles` | not_started | | | |
| 4 | Glossary | `/glossaries` | not_started | | | |
| 5 | Admin | `/admin` | not_started | | | |

## Shared reference (read once)

- `frontend/src/styles/motitle-bold.css` — Bold design tokens + class catalog
- `frontend/src/pages/Dashboard.tsx` — canonical Bold layout reference:
  - `.b-rail` (left nav) — `BoldRail` component
  - `.b-topbar` (top strip) — `BoldTopbar` with `.pipeline-strip` + `.health-cluster` + Logout
  - Three-col `.b-content` grid
  - `.panel` for any content container
  - `.empty` + `.empty-icon` + `.empty-title` + `.empty-sub` for placeholders
- `frontend/src/lib/motitle-icons.tsx` — 40 Icons + Badge + MoTitleStageBadge

## Iter 1 — Timeline (Proofread)

[FIXED] — 2026-05-19

- Backend endpoints in scope (all already exist, none changed):
  - `GET /api/files/<id>` — file detail
  - `GET /api/files/<id>/translations` — translations list
  - `GET /api/files/<id>/segments` — ASR segments
  - `GET /api/files/<id>/media` — video stream for `<video src>`
  - `GET /api/pipelines/<id>` — pipeline lookup for font + glossary
  - `PATCH /api/files/<id>` — subtitle_source + bilingual_order
  - `PATCH /api/files/<id>/translations/<idx>` — segment edit
  - `POST /api/files/<id>/translations/<idx>/approve` — approve
  - `POST /api/files/<id>/pipeline_overrides` — prompt overrides
  - `POST /api/files/<id>/stages/<idx>/rerun` — re-run stage
  - `POST /api/render` — render
  - `POST /api/logout` — topbar logout

- Bold elements reused (zero copy/paste from Dashboard):
  - `BoldRail` — extracted to `frontend/src/components/BoldRail.tsx`
    with optional `activeId` prop. Dashboard now imports from there.
  - `.b-rail` + `.b-main` + `.b-topbar` + `.b-body` (`.b-body-proofread`
    variant w/ new grid template) + `.b-col` + `.panel` + `.panel-head`
    + `.panel-body` + `.empty` + `.empty-icon` + `.empty-title` from
    `motitle-bold.css`.
  - `.run-btn` + `.health-cluster` + `.health-pill` from Dashboard topbar.
  - `.badge.badge--accent` + `.badge.badge--idle` for file status pill.

- Bold elements added (new, ~80 lines CSS in motitle-bold.css):
  - `.back-btn` — Proofread-specific back-to-Dashboard chip
  - `.filename-strip` — filename + status badge + source dropdowns
  - `.action-chip` — Overrides chip (mirrors `.save-btn` cousin)
  - `.b-body-proofread` — 3-col grid w/ wider left for segment table
  - `.seg-table-wrap` — sticky thead + scrollable tbody for SegmentTable
  - `tr.active` — playhead-driven active row highlight

- Design decisions:
  - Proofread page bypasses the legacy `<Layout/>` shell (router.tsx
    moves `/proofread/:fileId` out from under `<Layout/>` branch — same
    pattern Dashboard already uses). This is the only structural router
    change required.
  - `TopBar.tsx` kept as a separate component (not inlined into
    index.tsx) so the existing `index.test.tsx` mock — which substitutes
    `<TopBar>` with a stub — keeps working without test changes.
  - Button visible text + aria-label both contain English keywords
    (`返回 Back`, `渲染 Render`, `提示詞 Overrides`) so existing
    Playwright regex matchers (`/Back/i`, `/Render/`, `/Overrides/i`)
    in `proofread-render-modal.spec.ts` + `proofread-prompt-override.spec.ts`
    + `proofread-load.spec.ts` continue to find them.
  - Playhead (`currentTime`) lifted to the page parent so VideoPanel +
    SegmentTable share the same source of truth. VideoPanel emits
    `onTimeUpdate(t)` from the `<video>` element's native `timeupdate`
    event; SegmentTable does a linear scan (97 segments × 60 Hz = 6 k
    ops/sec, negligible) to find the active row and pass `isFocused` to
    SegmentRow.
  - `VideoSubtitleOverlay` from Dashboard NOT extracted — the Proofread
    page reuses the existing `SubtitleOverlay` SVG component which has
    better paint-order geometry for libass parity. The Dashboard's
    text-shadow-based overlay continues to coexist (different code path,
    different concerns).
  - StageHistorySidebar default opens at segment idx 0 from the
    right-column "開啟 stage history sidebar" button. Per-row Eye icon
    in SegmentRow continues to open at the clicked row.

- Backend gaps discovered: none.

- Commits:
  - `2b9a441` — refactor(frontend): extract BoldRail to shared component
  - `450a83d` — feat(proofread): Bold layout rewrite with time-driven
    subtitle overlay
  - `2882c14` — test(e2e): bold-proofread.spec covering layout + segments
    + overlay + render + back nav

- Playwright spec: `tests-e2e/bold-proofread.spec.ts` — 7 tests, all
  pass first run. Full regression: 31 passed / 20 skipped / 0 failed
  (baseline 24 passed / 20 skipped, +7 new from this spec, no broken
  tests).

- Vitest: 204/204 pass (unchanged from baseline 204).

## Iter 2 — ASR Profile

[FIXED] — 2026-05-19

- Backend endpoints in scope (all already exist, none changed):
  - `GET /api/asr_profiles` — list visible profiles
  - `POST /api/asr_profiles` — create
  - `GET /api/asr_profiles/<id>` — single profile
  - `PATCH /api/asr_profiles/<id>` — update (owner only)
  - `DELETE /api/asr_profiles/<id>` — delete (owner only)
  - `POST /api/logout` — topbar logout

- Bold elements reused (zero copy/paste from Dashboard):
  - `BoldRail` from iter 1 with `activeId="asr"`.
  - `.b-rail` + `.b-main` + `.b-topbar` + `.b-body` + `.b-col` +
    `.panel` + `.panel-head` + `.panel-body` + `.empty` + `.empty-icon`
    + `.empty-title` + `.empty-sub` from `motitle-bold.css`.
  - `.back-btn` + `.run-btn` + `.health-cluster` + `.health-pill` +
    `.topbar-mid` + `.topbar-actions` from existing topbar primitives.
  - `.btn` + `.btn-primary` + `.btn-ghost` for form action buttons.

- Bold elements added (new, ~130 lines CSS in motitle-bold.css):
  - `.b-body.b-body-entity` — 2-col grid (360px list + 1fr form)
  - `.b-topbar .page-title` — used when there's no filename strip
  - `.profile-list` + `.profile-row` + `.profile-icon` +
    `.profile-text` + `.profile-name` + `.profile-meta` +
    `.profile-del` — list rows w/ active state + reveal-on-hover delete
  - `.entity-form` + `.field-row` + `.field-grid` + `.field-checks` +
    `.field-err` + `.form-actions` — Bold-styled form layout

- Other changes:
  - `BoldRail.RAIL_ITEMS` extended to include `asr`/`mt`/`admin`
    entries so the left rail exposes a per-page chip. Existing
    Dashboard items kept (home/files/proof/pipeline/gloss); two new
    Dashboard-related items (`files`, `lang`) were already there.
    Dashboard tests still pass because Dashboard does not assert any
    specific RAIL_ITEMS count.
  - Router `/asr_profiles` route moved out from under `<Layout/>` to
    sit alongside `Dashboard` + `Proofread` (full-page Bold). Same
    pattern iter 1 used for Proofread.

- Design decisions:
  - Form renders inline in the right column (not a modal dialog). This
    is more space-efficient for a 10-field schema and parallels how
    other native settings UIs work (Xcode / VS Code / Cursor settings).
    The previous shadcn Dialog-based form had a small viewport and was
    awkward when the user wanted to scroll or compare to the list.
  - Right-column empty state when nothing selected — "未選 Profile"
    with hint to pick a row or click + 新增 Profile.
  - Delete button on each row reveals on hover (mirrors Dashboard's
    `.qi-del` pattern). Confirm via `ConfirmDialog`.
  - Bold ASR rail icon = `waveform`, matching the ASR semantic in
    the design.
  - Topbar Logout chip kept (mirrors Proofread topbar) so users can
    log out from any page without going through SideNav (since we
    removed SideNav for this page).

- Existing `tests-e2e/asr-profiles-crud.spec.ts` needed updating —
  the old spec asserted `button name "+ New ASR Profile"` and an
  `<h2>New ASR Profile</h2>` heading inside a modal Dialog. New Bold
  variant has `+ 新增 Profile` button and inline form (no modal). Spec
  updated to use `.b-topbar .run-btn` selector + `getByLabel('Name')`
  + `getByLabel('Engine')` for the field assertions. Test intent
  (CRUD UI works) preserved.

- Dashboard + Proofread vitest specs: zero changes needed —
  BoldRail addition of `asr`/`mt`/`admin` items is additive; no
  Dashboard test asserts the exact RAIL_ITEMS length.

- Backend gaps discovered: none.

- Commits: (this branch — see git log)

- Playwright spec: `tests-e2e/bold-asr-profile.spec.ts` — 5 tests,
  all pass first run (Bold layout landmarks / rail active state /
  list existing profiles / create+read+delete round-trip / back nav).
  Full regression: 36 passed / 20 skipped / 0 failed (baseline 31
  passed, +5 new from this spec, no broken tests).

- Vitest: 204/204 pass (unchanged from iter 1 baseline 204).

## Iter 3 — MT Profile

[NOT_STARTED]

## Iter 4 — Glossary

[NOT_STARTED]

## Iter 5 — Admin

[NOT_STARTED]
