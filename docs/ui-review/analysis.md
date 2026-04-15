# Frontend UI Review & Optimization Analysis

**Mode:** Analysis only (no code changes). Each iteration reviews one area of the UI, captures a Playwright screenshot, and appends findings here.

**Scope:** Visual hierarchy, affordances, error/loading states, accessibility, keyboard navigation, consistency.

**Out of scope:** Backend changes, major rewrites, third-party libraries.

---

## Review Checklist (20 areas)

Check off each area as it is reviewed. Pick the next unchecked area in order.

- [x] 1. Dashboard overall layout + header
- [x] 2. File upload region (button + drag-drop zone)
- [x] 3. File list card (status badges, re-transcribe, delete)
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

### Area 3: File list card (status badges, re-transcribe, delete)

**Screenshot:** `screenshots/03_file-list-card.png`

**What works:**
- Filename has full-width room; long YouTube-derived names are not visually clipped beyond what CSS truncation demands
- Two-row layout separates identity (filename + size + status) from context and actions (engine chips + downloads + CTAs)
- Color-coded green pills for completed states stand out against the dark background
- SRT / VTT / TXT download links are always one click away, directly on the card — no need to open a sub-panel
- Engine provenance chips (`medium · mlx-whisper` + `gpt-oss-120b-cloud`) document what produced this result — valuable for debugging and reproducibility

**Issues observed:**
- [P1] The card has two "done" pills (`完成` top-right for transcription, `翻譯完成` row 2 for translation) styled identically. Users cannot visually distinguish the two lifecycle stages — both are green pill shape/size/color. The meaning is learned, not perceived.
- [P1] No visual hierarchy on row 2: engine chips, status pill, three download links, `重新翻譯`, and `校對` are all rendered with the same pill-button vocabulary. The card is visually "flat" — everything competes for the eye.
- [P1] `×` (delete) is top-right, adjacent to the `完成` badge, with no confirm dialog. Destructive action sits directly next to a static status badge — high mis-click risk, zero recovery.
- [P2] Engine chips (`medium · mlx-whisper`, `gpt-oss-120b-cloud`) look like clickable buttons (same rounded pill shape as the SRT/VTT/TXT download links) but are static labels. Affordance confusion: user may try to click to "change engine".
- [P2] The filename itself is clickable (opens proofread editor) but has no underline, no color shift, no pointer hint. Discoverability: low. Only learned by accident.
- [P2] Two CTAs at the end of row 2: `重新翻譯` (outlined purple) and `校對` (filled purple). Reading order is `重新翻譯` → `校對` but visual weight says `校對` is primary. Conflict between left-to-right priority and visual priority.
- [P3] `48.6 MB` on row 1 uses space that could show richer metadata (duration, segment count, uploaded-at timestamp). File size alone becomes uninteresting once the file is done.
- [P3] No relative upload time ("2 小時前") and no duration ("⏱ 4:32"). For broadcast workflow these are more useful than byte count.
- [P3] When the card is `.active` (selected) the only difference is a purple border per the CSS. No additional affordance to say "this is the file currently playing in the video column" — easy to lose track when scrolling.

**Recommendations:**
1. Differentiate the two status pills: `✓ 轉譯` as an outlined pill (lifecycle stage 1), `✓ 翻譯` as a filled pill (lifecycle stage 2), or use distinct icons. Pair each with a tooltip that shows the completed-at timestamp.
2. Restyle row 2 with explicit groups separated by spacing and subtle dividers: `[engine chips]  |  [status pill]  |  [download pills]  →  [action cluster]`. Downgrade engine chips to flat tags (no border, dimmer background).
3. Move `×` delete into an overflow menu (`⋯`) with explicit label "刪除檔案" and a confirm dialog. Keep the top-right area for lifecycle badges only.
4. Make the filename an explicit link: hover underline, cursor `pointer`, and a trailing `↗` icon. Add `title="打開校對編輯器"` so the action is discoverable.
5. Collapse `重新翻譯` into the overflow menu — it is rarely used once a file is approved. Row 2 then shows only one CTA: `校對 →`.
6. Replace `48.6 MB` with a compact metadata strip: `⏱ 4:32 · 41 段 · 2 天前`. File size can move to a tooltip on the overflow menu if anyone cares.
7. When `.file-card.active`, add a left border accent stripe and a small "▶ 播放中" chip near the filename — visual pinning so users scrolling through a long list can always spot "where I am now".

**Estimated impact:** high — this card is the primary recurring interaction surface
**Estimated effort:** M — two CSS refactors + one JS overflow menu + safer delete confirm

---
