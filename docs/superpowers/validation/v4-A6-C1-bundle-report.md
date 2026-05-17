# v4.0 A6 C1 — Bundle Code-Splitting Report

**Captured:** 2026-05-17
**Branch:** chore/asr-mt-rearchitecture-research
**Pre-C1 commit:** 6b0e798 (A6 spec + plan)
**Post-C1 commit:** dac4464 (T2 React.lazy + Suspense)

## Summary

Main chunk: **652KB → 31KB** (raw, -95%) / **200KB → 11KB** (gzipped, -94%).
No more Vite `chunkSizeWarningLimit` warning. 7 vendor chunks + 8 per-page chunks emitted.

## Before (single chunk)

| Chunk | Raw | gzipped |
|---|---|---|
| `index-*.js` (everything) | 652 KB | 200 KB |
| `index-*.css` | 19.86 KB | 4.50 KB |

## After (split)

### Vendor chunks (cached across navs)

| Chunk | Raw | gzipped |
|---|---|---|
| `vendor-react` (React + ReactDOM + scheduler) | 165 KB | 54 KB |
| `vendor-forms` (react-hook-form + zod + @hookform/resolvers) | 90 KB | 25 KB |
| `vendor-ui` (@radix-ui + lucide-react) | 74 KB | 23 KB |
| `vendor-router` (react-router) | 65 KB | 22 KB |
| `vendor-dnd` (@dnd-kit) | 44 KB | 15 KB |
| `vendor-socket` (socket.io-client + engine.io) | 42 KB | 13 KB |
| `vendor-state` (zustand) | 3 KB | 1.4 KB |
| **Vendor total** | **483 KB** | **153 KB** |

### Per-page chunks (lazy loaded)

| Chunk | Raw | gzipped |
|---|---|---|
| `Dashboard` | 67.58 KB | 19.77 KB |
| `Proofread (index)` | 39.01 KB | 10.71 KB |
| `Pipelines` | 9.64 KB | 3.20 KB |
| `MtProfiles` | 5.53 KB | 2.01 KB |
| `Glossaries` | 5.42 KB | 2.18 KB |
| `AsrProfiles` | 5.02 KB | 1.74 KB |
| `Admin` | 4.66 KB | 1.49 KB |
| `Login` | 2.12 KB | 1.03 KB |
| **Per-page total** | **139 KB** | **42 KB** |

### Entry + misc

| Chunk | Raw | gzipped |
|---|---|---|
| `index` (entry + App + router) | 31.08 KB | 10.89 KB |
| Misc (Dialog/Tabs/Textarea/ConfirmDialog) | ~5 KB | ~2 KB |

## Acceptance vs. spec target

| Metric | Target | Actual | ✓ |
|---|---|---|---|
| Main chunk raw | ≤250 KB | 31 KB | ✓ |
| Main chunk gz | (informational) | 11 KB | — |
| No Vite size warning | required | confirmed (no `(!)` line) | ✓ |
| Per-page chunks | 7 | 8 (Dashboard/Pipelines/AsrProfiles/MtProfiles/Glossaries/Admin/Login/Proofread) | ✓ |
| Vendor chunks | 7 | 7 (react/router/ui/forms/dnd/socket/state) | ✓ |
| Vitest pass | 184 | 184 | ✓ |

## Notes

- `vendor-react` chunk includes ReactDOM + scheduler + jsx-runtime. Largest at 165 KB raw but ~54 KB gzipped — well within HTTP/2 multiplex efficiency.
- `Dashboard` is heaviest page chunk (67 KB) because it imports SocketProvider context + multiple sub-components. Acceptable.
- Proofread chunk inherits filename `index-CWuXN8y6.js` (39 KB) because the page module is `pages/Proofread/index.tsx`. Rollup derives chunk name from entry basename. Functionally lazy-loaded; just bears the `index` filename. Could be aliased via `output.chunkFileNames` later if desired.
- Initial page load now fetches: `index.html` (0.4 KB) + entry `index-*.js` (31 KB) + vendor-react (165 KB) + Login chunk (2 KB) = ~200 KB raw / ~67 KB gzipped on the login screen. Subsequent navs lazy-fetch the relevant page chunk + any additional vendor chunks (e.g. Pipelines page → vendor-dnd loads on demand).
