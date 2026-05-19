# Bold variant redesign tracker (feat/frontend-redesign)

**Branch base**: `feat/frontend-redesign` @ commit `10469e2`
**Started**: 2026-05-19
**Goal**: Extend Dashboard's Bold design language to 5 remaining pages with full Playwright verification.

## Status table

| Iter | Page | Route | Status | Commits | Playwright spec | Backend gaps |
|---|---|---|---|---|---|---|
| 1 | Timeline (Proofread) | `/proofread/:fileId` | not_started | | | |
| 2 | ASR Profile | `/asr_profiles` | not_started | | | |
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

[NOT_STARTED]

- Backend endpoints in scope: TBD
- Bold elements to reuse: TBD
- Design decisions: TBD
- Backend gaps discovered: TBD
- Commits: TBD
- Playwright spec: `tests-e2e/bold-proofread.spec.ts` (TBD)

## Iter 2 — ASR Profile

[NOT_STARTED]

## Iter 3 — MT Profile

[NOT_STARTED]

## Iter 4 — Glossary

[NOT_STARTED]

## Iter 5 — Admin

[NOT_STARTED]
