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
- [x] 4. Sidebar structure + collapsibility
- [x] 5. Profile selector (list-style, not a dropdown)
- [x] 6. Profile form — basic info section
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

### Area 4: Sidebar structure + collapsibility

**Screenshot:** `screenshots/04_sidebar-structure.png`

**What works:**
- Two clearly-delineated panels stack vertically: 「轉錄文字」 (current-file transcript) on top, 「設置」 (settings) below. The separation by concern (output vs configuration) is a reasonable starting point.
- Collapsible sub-sections (`🌐 語言配置`, `📖 術語表`) with the ▶ indicator reduce initial cognitive load for users who only care about the core playback controls.
- Active profile "Development" is highlighted with a green left-dot — standard "you are here" pattern.
- Empty state in the 轉錄文字 panel has an illustration + helper copy, avoiding a dead tabs-only state.
- Persistent status footer `已連接到 Whisper 服務器` gives the user confidence that the backend link is alive.
- Fixed-width 360px column on desktop is narrow enough to not dominate the viewport.

**Issues observed:**
- [P1] The "設置" panel conflates three logically distinct concerns into one undifferentiated scroll:
  (a) **Pipeline management** — `PIPELINE PROFILE` list with Edit/Del (affects the *next* transcription run)
  (b) **Playback rendering** — `字幕延遲`, `字幕顯示時長`, `字幕大小` sliders (affect *current* video playback only)
  (c) **Global config** — `🌐 語言配置`, `📖 術語表` (global, affects all runs)
  A user adjusting the subtitle delay slider has no way to know it is *playback-only* and does not re-trigger anything. The mental model leaks.
- [P1] Inline `Edit` / `Del` text links on each profile row are visually indistinguishable (same color, same font size, same proximity). For the active profile the `Del` is dimmed but the user has to visually parse "is it dimmed?" before clicking — not scannable.
- [P1] The three sliders have no visual separation between them and share the same purple accent. Scanning down the panel, it is easy to misread which number belongs to which slider, especially because `字幕延遲` shows a `同步補償` pill and auxiliary min/max labels while the other two do not.
- [P2] The "設置" panel has a single top-level header `⚙ 設置` then immediately drops into `PIPELINE PROFILE` without a clear hierarchy. Sliders have no group header. Collapsible sections have no group header. Everything is one flat list inside one panel.
- [P2] `🌐 語言配置` and `📖 術語表` headers have a ▶ glyph but no visible hover/pointer affordance in the idle state — they look like decorative markers rather than interactive elements.
- [P2] Slider annotations are inconsistent: `字幕延遲` shows "無延遲 / 5 秒", but `字幕顯示時長` and `字幕大小` show only the current value. Either all three should have min/max hints or none should.
- [P2] `+ New Profile` is a dashed-border button — a different button language than the filled purple `🚀 上傳並轉錄` on the main column. Two visually distinct "new action" styles in the same viewport with no rationale.
- [P3] The "轉錄文字" empty-state illustration occupies roughly 150px of vertical space. Once real data arrives it will push the setting panel below the fold; users will have to scroll just to see the 字幕延遲 slider they wanted to tweak.
- [P3] Below the `📖 術語表` collapsible there is a large empty region before the footer status — on a 1400px-tall viewport this is ~400px of wasted space.
- [P3] The footer `✅ 已連接到 Whisper 服務器` is far from where the user is looking when they interact with settings. A disconnect will not be noticed until the user scrolls all the way down.

**Recommendations:**
1. Split the "設置" panel into three clearly-labelled sub-panels:
   - **「Pipeline 配置」** — profile list + language + glossary (everything that feeds the next run)
   - **「播放調整」** — delay / display duration / font size sliders (rendering on the current clip only)
   - **「管理」** (collapsed by default) — CRUD for profiles, language configs, glossaries
   Put a thin divider rule between each, and a subtle mini-header in the body.
2. Replace inline `Edit` / `Del` text with icons: ✏ (pencil, neutral) and 🗑 (red). Wrap both in an overflow `⋯` menu if vertical space matters more than discoverability.
3. Add mini group headers for the sliders ("播放微調") and visual separators between each slider row. Alternatively, render each slider in its own subdued card with the label + value on one line and the track below.
4. Normalise slider annotations: either give all three sliders `min / max` hints or remove them from 字幕延遲.
5. Unify button vocabulary. Pick three styles only: `.btn-primary` (filled purple), `.btn-secondary` (outlined purple), `.btn-ghost` (text-only). `+ New Profile` should be `.btn-secondary` to match its secondary role.
6. Shrink the "轉錄文字" empty-state illustration by ~40% (smaller graphic, tighter padding) so that it doesn't crowd out settings once data arrives.
7. Move the connection status to the global header top-right, upgrading from the current tiny green dot to a colored pill with explicit text (`✅ Whisper / 🟢 Ollama Cloud`). Remove the bottom-of-sidebar duplicate.
8. Make collapsible section headers feel clickable: `cursor: pointer`, background tint on hover, and rotate the ▶ glyph to ▼ when expanded.

**Estimated impact:** high — the sidebar is the control centre and currently tangles three mental models into one scroll
**Estimated effort:** M-L — restructuring panel hierarchy, introducing sub-panel components, consolidating button styles

---

### Area 5: Profile selector (list-style, not a dropdown)

**Screenshot:** `screenshots/05_profile-selector.png`

**Note:** The area is labelled "dropdown" in the checklist, but the actual implementation is a vertical list (`#profileList`) with inline Edit/Del actions. No `<select>` is involved. Review applies to the list-selector as it exists.

**What works:**
- Active profile is clearly marked with a green dot prefix — low-cost, scannable
- Entire profile list is visible at once (two items) without drilling into a dropdown
- Edit / Del actions are inline on each row, so no hidden affordances
- "+ New Profile" button is directly above the list, in natural creation-flow position
- On the active profile, `Del` is dimmed, signalling that you cannot delete the currently-active profile

**Issues observed:**
- [P1] **No explicit activation affordance.** Looking at the two rows, a first-time user cannot tell how to switch from `Development` to `Broadcast Production`. The row has no pointer cursor, no "Activate" button, no radio indicator. Activation must be inferred by trial and error (click-the-name-and-hope) or learned from docs.
- [P1] **Edit and Del are visually indistinguishable.** Both render as small non-underlined text in the same color. On `Broadcast Production` both are active; on `Development` one is dimmed — but the dimming is subtle and the labels themselves do not differentiate. A hasty user will click the wrong one.
- [P1] **Dimmed `Del` on the active profile is ambiguous.** It is neither fully disabled (no cursor change, no tooltip explaining why) nor fully hidden. The user has to stare and guess whether their click will have an effect.
- [P2] **No metadata preview per profile.** `Broadcast Production` and `Development` differ in engine/language/style but the row shows only the name. Users must open the edit form to remember which profile is which — a full modal context-switch for a glance question.
- [P2] **"+ New Profile" button is weaker than the items below it.** The dashed border with neutral text is visually subordinate to the filled profile cards, so the eye scans past it. If creating a new profile is a first-class action it should match the button vocabulary elsewhere on the page.
- [P2] **`PIPELINE PROFILE` header is small caps in a dim color.** For what is arguably the most consequential setting in the app — the thing that determines what happens when you press Upload — the header lacks emphasis.
- [P3] **No hover feedback on profile rows.** A row should show a subtle background tint on hover to confirm it is interactive (once activation is wired up).
- [P3] **No keyboard shortcut for quick switching** (e.g. `Cmd+1` / `Cmd+2`) despite broadcast workflow being a power-user context where hotkeys matter.
- [P3] **Long profile names** would be truncated with no tooltip. Not visible in the current two-profile sample but easy to reach.

**Recommendations:**
1. Make the whole row an explicit activation target: `cursor: pointer`, hover background tint, `onclick` handler calling `POST /api/profiles/<id>/activate`. Show an optimistic toast `已啟用 <name>` on success.
2. Replace inline text `Edit` / `Del` with small icon buttons (✏ and 🗑) with different hover colors (neutral → blue / red). Add `aria-label` and tooltips. Consider moving them into a `⋯` overflow menu to free the row for the new click-to-activate target.
3. Fully disable `Del` on the active profile: `disabled` attribute, `opacity: 0.25`, `title="先切換至其他 Profile 才能刪除"`. The intent should be perceptible, not guessable.
4. Render a one-line metadata preview under each profile name: `mlx-whisper · en · qwen2.5-3b`. Use a dimmer color so it reads as supporting info.
5. Upgrade the `PIPELINE PROFILE` header to match other panel headers (larger font, slight accent color) and consider renaming to `Pipeline 配置` for consistency with the rest of the Chinese-language UI.
6. Rebuild `+ New Profile` as a secondary-style button (outlined purple with an icon) so it visually matches the rest of the button language without competing with the row list.
7. Add keyboard shortcut wiring: `data-hotkey="1"`, `data-hotkey="2"` on rows; press the number to activate. Surface in a `?` help modal.
8. Add `title` attribute on each row name so long names get full-text tooltips on hover.

**Estimated impact:** high — profile activation is the root of every transcription run, and currently requires guesswork
**Estimated effort:** S-M — CSS + small JS for click-to-activate + metadata rendering; no backend changes

---

### Area 6: Profile form — basic info section

**Screenshot:** `screenshots/06_profile-form-basic.png`

**What works:**
- Section is collapsible with a ▼ arrow in the expanded state — visual affordance is present
- `名稱 *` uses the standard asterisk convention to mark a required field
- `描述` is a textarea (multi-line), so longer notes like "Lightweight models for development and testing on MacBook (16GB RAM)" have room to breathe
- Section header + body are visually distinct from the panel background, making the form-in-sidebar boundary clear
- Default values populate correctly when editing an existing profile (no empty form on Edit)

**Issues observed:**
- [P1] **No reserved error slot.** If form validation fires (e.g. user clears `名稱`), any error message injected dynamically will cause layout jump. The adjacent fields have no stable `min-height` allowance.
- [P1] **No character count or maxlength on `描述`.** The user has no idea if they can write a sentence or a paragraph, and the backend has no visible guard either. A pasted 10 KB essay would silently flood the field.
- [P2] **Required asterisk is the same color as the label**, so it is not scannable — an error pattern visible only on careful read.
- [P2] **No inline help/examples** for `描述`. The placeholder `選填描述` is vague; a hint like `e.g. "RTHK style · 16GB MacBook · Cantonese output"` would guide the user.
- [P2] **The textarea font appears to render in a monospace-like stack**, inconsistent with the rest of the form. Likely an inherited browser default that was not overridden by the form CSS.
- [P2] **Section header click target is wide but only the ▼ arrow visibly signals interactivity.** A background-tint hover state would make the full-width click surface discoverable.
- [P3] **No form reset or discard control.** A user who starts editing and wants to bail has to close the form (losing all in-progress changes with no confirmation) or manually wipe every field.
- [P3] **No label/control association via `for`/`id`** is visibly confirmable from the screenshot; if absent, screen readers lose context.
- [P3] **Fixed textarea height (~60px)** means long descriptions become scrolling-inside-a-tiny-box. Auto-grow up to a max-height would fit natural writing.

**Recommendations:**
1. Reserve a 16–20px error slot under each input (`<div class="pf-error" role="alert"></div>`) so inline validation never shifts layout. Wire `validate()` to populate it.
2. Add `maxlength="40"` to `#pfName` and `maxlength="280"` to `#pfDesc`, with a small right-aligned counter `<span class="pf-counter">42 / 280</span>` under the textarea.
3. Style the required asterisk in `--danger` color with a small left margin so it reads as `名稱 *` with the star clearly separated.
4. Add a helper line under each field label: `<small class="pf-hint">Profile 的識別用途，例如 "Production RTHK Cantonese"</small>`.
5. Enforce font consistency: `.profile-edit-form input, .profile-edit-form textarea { font-family: inherit; }`.
6. Give `.profile-form-section-header:hover` a subtle background tint so the click target is perceivable.
7. Add a trailing `.btn-ghost` "清空表單" button in the form footer (or restore-defaults on Edit mode) with a confirm dialog.
8. Use `<label for="pfName">名稱 *</label>` bindings explicitly; add `aria-describedby` pointing at the helper/counter spans.
9. Enable textarea auto-grow: on `input`, set `style.height = 'auto'; style.height = (element.scrollHeight + 2) + 'px'`. Cap at e.g. 200px.

**Estimated impact:** medium — low-frequency interaction, but the first form a new user fills in, so a poor impression compounds
**Estimated effort:** S — mostly attributes + small CSS and JS; no backend coupling

---
