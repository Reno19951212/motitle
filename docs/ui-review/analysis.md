# Frontend UI Review & Optimization Analysis

**Mode:** Analysis only (no code changes). Each iteration reviews one area of the UI, captures a Playwright screenshot, and appends findings here.

**Scope:** Visual hierarchy, affordances, error/loading states, accessibility, keyboard navigation, consistency.

**Out of scope:** Backend changes, major rewrites, third-party libraries.

---

## Review Checklist (20 areas)

Check off each area as it is reviewed. Pick the next unchecked area in order.

- [ ] 1. Dashboard overall layout + header
- [ ] 2. File upload region (button + drag-drop zone)
- [ ] 3. File list card (status badges, re-transcribe, delete)
- [ ] 4. Sidebar structure + collapsibility
- [ ] 5. Profile selector dropdown
- [ ] 6. Profile form — basic info section
- [ ] 7. Profile form — ASR parameters section
- [ ] 8. Profile form — Translation engine dropdown (local/cloud optgroup)
- [ ] 9. Profile form — Font configuration section
- [ ] 10. Transcription progress bar + ETA
- [ ] 11. Real-time subtitle segment display during transcription
- [ ] 12. Translation status badge + re-translate button flow
- [ ] 13. Language config panel
- [ ] 14. Glossary management panel
- [ ] 15. Proofread editor — video player controls
- [ ] 16. Proofread editor — segment table editing UX
- [ ] 17. Proofread editor — approval buttons (per-segment + bulk)
- [ ] 18. Proofread editor — keyboard shortcuts discoverability
- [ ] 19. Error states (upload/API/translation failures)
- [ ] 20. Loading states consistency + Ollama signin button UX

---

## Findings

Each entry below follows this template:

```
### Area N: <name>

**Screenshot:** `screenshots/NN_<slug>.png`

**What works:**
- ...

**Issues observed:**
- [Priority P1/P2/P3] ...

**Recommendations:**
1. ...

**Estimated impact:** <low / medium / high>
**Estimated effort:** <S / M / L>
```

---
