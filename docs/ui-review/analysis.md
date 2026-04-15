# Frontend UI Review & Optimization Analysis

**Mode:** Analysis only (no code changes). Each iteration reviews one area of the UI, captures a Playwright screenshot, and appends findings here.

**Scope:** Visual hierarchy, affordances, error/loading states, accessibility, keyboard navigation, consistency.

**Out of scope:** Backend changes, major rewrites, third-party libraries.

---

## Review Checklist (20 areas)

Check off each area as it is reviewed. Pick the next unchecked area in order.

- [x] 1. Dashboard overall layout + header
- [x] 2. File upload region (button + drag-drop zone)
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

### Area 1: Dashboard overall layout + header

**Screenshot:** `screenshots/01_dashboard-overall.png`

**What works:**
- Dark theme is appropriate for video editing context and reduces eye strain
- Three-column layout (video player / transcript / sidebar) makes sense for a video-centric workflow
- Connection status "已連接" present so the user knows the backend is reachable
- Accent purple is used consistently for interactive elements

**Issues observed:**
- [P1] The right sidebar conflates four very different concerns into one vertical stack: rendering controls (subtitle delay, font size), active-engine shortcut (`字幕 AI Whisper`), per-language tuning (`語言` / `詞彙表`), and pipeline management (`PIPELINE PROFILE` with Broadcast Production / Development). Users cannot tell at a glance which sections affect rendering, which affect the next transcription, and which are static configuration.
- [P1] "文件上載" (drag-drop zone) lives below the fold on smaller viewports but the video player above it sits empty most of the time. The upload affordance is therefore slow to reach on first visit — users have to scroll past a large blank video frame.
- [P2] Header contains only the app title and a connection indicator. There is no global "+ Upload" CTA, no link to proofread editor, no settings/help icon. Every action requires drilling into the sidebar or scrolling.
- [P2] The "已連接" indicator is small, monochrome, and positioned in the same color family as the title, making it easy to miss when disconnected would be critical information.
- [P2] Transcript preview area in the middle column shows SRT/VTT/TXT tabs even when no file is selected, so the tabs appear clickable but have nothing to show — a classic "dead state" problem.
- [P3] No breadcrumbs, navigation, or current-file indicator. When a user returns from Proofread editor, there is nothing on the dashboard telling them which file they last worked on.
- [P3] The sidebar has multiple collapsible sections but their default state (some open, some collapsed) has no obvious rationale — the Profile section is expanded showing two profiles while Language is collapsed despite being edited more often.

**Recommendations:**
1. Move the upload CTA into the header as a prominent "+ 上傳影片" button. Keep the drag-drop zone in the main area but shrink it when a file list already exists.
2. Split the right sidebar into three clearly-labelled groups: (a) "當前播放設定" (subtitle delay / font size / transparency — affects current playback only), (b) "Pipeline 設定" (profile + engine + language + glossary — affects next run), (c) "管理" (profile CRUD, language CRUD, glossary CRUD). Use a tab bar or H3 headers with explicit divider rules.
3. Upgrade the connection indicator to a colored pill (green ✓ / red ✗) with explicit text so status is scannable.
4. Empty-state the transcript column: if no file is selected, show an illustration + "揀一個檔案嚟睇字幕" CTA instead of bare tabs.
5. Add a current-file breadcrumb in the header once a file is selected ("📄 bbd1b34cb2ca.mp4 · 41 段 · 翻譯完成").
6. Settle the default collapse state based on edit frequency: Profile + Engine expanded, Language + Glossary + Font collapsed.

**Estimated impact:** high — first-impression affordances + recurring daily friction
**Estimated effort:** M — HTML restructure + CSS + a bit of JS for collapse defaults; no backend

---

### Area 2: File upload region (button + drag-drop zone)

**Screenshot:** `screenshots/02_upload-region.png`

**What works:**
- Dashed-border drop zone with upward-arrow icon clearly communicates "drop files here"
- Supported formats are listed inline so the user does not have to guess
- Two primary actions (上傳並轉錄 / 清除) are directly adjacent to the drop zone
- Panel has a clear header "📁 文件上傳" that matches the sidebar styling

**Issues observed:**
- [P1] The drop zone occupies ~200px of vertical space and is permanent. With 12 files already in the registry, that zone is mostly empty — users pay the same vertical cost whether they have 0 or 100 files. It should collapse after the first upload.
- [P1] The "🚀 上傳並轉錄" button is redundant with the drop zone: clicking it opens the native file picker, which is exactly what clicking the drop zone already does. Two affordances for the same action confuse new users (which is the "real" upload?) without saving any clicks.
- [P1] "🗑 清除" is dangerous and under-specified. The label does not say whether it clears the drop zone preview, the entire file list, or only the pending-upload state. It sits 8px from the primary upload button — a strong mis-click risk with no confirmation dialog.
- [P2] The supported-format list is a single dot-separated string "MP4 · MOV · AVI · MKV · WebM · MP3 · WAV · M4A". The eye cannot group by modality. Video vs audio formats are visually identical.
- [P2] No maximum-file-size hint. The backend enforces `MAX_CONTENT_LENGTH = 500MB` but the user discovers that only by hitting the error.
- [P2] Drag-over visual feedback exists in CSS (`.upload-zone.drag-over`) but its exact appearance needs verification — the static screenshot cannot confirm whether border/background change is conspicuous enough.
- [P3] No indication that multiple files can be uploaded in parallel. Users may think they need to wait for one to finish before starting another.
- [P3] The drop zone and the file list below it are in the same column, competing for attention. A user scanning for "what's my state" sees both a "do something" and a "here's what's done" element at the same weight.

**Recommendations:**
1. Collapse the drop zone to a ~60px strip after the first upload. Provide a "+ 新增檔案" text link/button in the strip that expands the full zone on click when the user wants to add more.
2. Delete the "上傳並轉錄" button. The drop zone already handles click + drag. If you want a redundant button for keyboard/pointer users, make it tab-focusable and label it "選擇檔案" — not a second "upload" action.
3. Move "清除" out of the upload panel entirely; put it as a trailing action next to the file list header ("清空列表" with a confirm dialog) so it is clearly list-scoped, not drop-zone-scoped.
4. Split the supported-format hint into two pills: `🎬 影片: MP4 MOV AVI MKV WebM` and `🎵 音訊: MP3 WAV M4A`. Add `最大 500 MB` inline.
5. Make the `.upload-zone.drag-over` state high-contrast: change background to `rgba(purple, 0.15)` and border to solid purple, not dashed, so there is no ambiguity.
6. Add a subtitle under the drop zone icon: "可同時拖入多個檔案 — 每個檔案會排隊處理" so the parallel-upload model is explicit.

**Estimated impact:** medium-high — recurring first-action friction; sharp downgrade once the user has more than a handful of files
**Estimated effort:** S — CSS + small JS for collapse state + one confirm dialog

---
