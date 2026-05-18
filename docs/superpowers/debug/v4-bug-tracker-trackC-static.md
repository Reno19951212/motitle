# Bug Tracker — Track C (Static analysis)

**Track:** C
**Owner:** (to be filled by Track C subagent when work starts)
**Start:** 2026-05-18
**Status:** Not started

---

## Schema

Each finding is one H2 section:

```
## BUG-NNN: <短描述>
- **Status**: Open / In progress / Fixed / Wontfix / Deferred
- **Severity**: P0 / P1 / P2 / P3 (will triage in Phase 2)
- **A-phase origin**: P1 / A1 / A3 / A4 / A5 / A6 / cross-phase
- **Layer**: backend / frontend / E2E / docs / config / build
- **Discovery source**: Track C
- **Repro steps**: ...
- **Expected**: ...
- **Actual**: ...
- **Plan impact** (必選一個):
  - [ ] 純 bug fix
  - [ ] Spec 假設錯
  - [ ] 需開新 sub-phase
  - [ ] Defer 入 backlog
  - [ ] Confirmed out-of-scope
- **Suggested fix**: <approach>
- **Linked commit**: (Phase 3b 填寫)
```

---

## Entries

### AUDIT: Static analysis pass (no findings)

**Date:** 2026-05-18  
**Scope:** Surgical greps + tsc + lint (vulture/ts-prune excluded per spec §5.3)

#### Results

- **Grep 1 (alignment_pipeline imports)**: 0 matches
- **Grep 2 (sentence_pipeline imports)**: 0 matches
- **Grep 3 (post_processor imports)**: 0 matches
- **Grep 4 (profiles imports)**: 0 matches
- **Grep 5 (A5-deleted functions)**: 5 matches (all comments/docstrings, no functional imports)
  - `app.py:443` — comment explaining legacy pipeline removed
  - `app.py:668-669` — comment explaining legacy ASR/MT chain
  - `ollama_engine.py:760` — docstring reference to removed function
  - `files.py:502` — comment about concurrent worker thread (historical context)
- **Frontend legacy residue** — 0 matches:
  - `frontend.old` references: 0
  - `useActiveProfile` hook usage: 0
- **TypeScript strict** (`tsc --noEmit`): **clean** (0 errors)
- **Lint**: No lint script configured (npm run lint fails with "Missing script"); acceptable per spec

#### Conclusion

✅ **A5 cleanup invariant fully maintained**. All dead reference greps clean except for benign comments. Frontend legacy residue fully eliminated. TypeScript strict mode passes. No static-layer bugs detected.

---
