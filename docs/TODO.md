# TODO

Pending feature ideas not yet planned/implemented. Move to
`docs/superpowers/specs/` once brainstormed.

---

## Live subtitle: ZH placeholder during translation

**Reported:** 2026-04-28

**Current behaviour:**
After ASR completes but MT (translation) hasn't started or finished, the
live-subtitle dual-line preview shows English on the top line and English
again on the bottom line (because `zh_text` is still equal to `text`).

**Desired behaviour:**

1. ASR done, MT not yet started → top line shows EN; bottom line shows
   placeholder `翻譯中`.
2. MT in progress → same as (1) until each segment's ZH arrives, then
   that segment switches the bottom line to ZH.
3. MT done → top line EN, bottom line ZH (current end-state, unchanged).

**Implementation hints:**
- Probably check `translation_status` (`pending` / `translating` / `done`)
  AND/OR per-segment `zh_text === en_text` heuristic in the live overlay
  renderer.
- Live-subtitle code is in `frontend/index.html` (subtitle overlay /
  preview area). Same SVG overlay used in proofread.html may need the
  same treatment.

**Dependencies:** none — pure frontend change.
