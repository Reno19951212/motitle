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
- [x] 7. Profile form — ASR parameters section
- [x] 8. Profile form — Translation engine dropdown (local/cloud optgroup)
- [x] 9. Profile form — Font configuration section
- [x] 10. Transcription progress bar + ETA
- [x] 11. Real-time subtitle segment display during transcription
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

### Area 7: Profile form — ASR parameters section

**Screenshot:** `screenshots/07_profile-form-asr.png`

**What works:**
- Engine dropdown is prominent at the top with an availability indicator `● 可用` — immediate feedback on whether the chosen engine can actually run
- Parameters are dynamically loaded from the backend schema (no hard-coded assumptions), so adding a new engine automatically surfaces its params
- `引擎參數` sub-header separates the engine selector from the engine-specific parameters
- Each parameter row has its own control; consistent dropdown styling
- The section is collapsible, reducing vertical cost when users aren't tuning

**Issues observed:**
- [P1] **Parameter labels are the raw schema keys in ALL-CAPS English**: `CONDITION ON PREVIOUS TEXT`, `LANGUAGE`, `MODEL SIZE`, `LANGUAGE CONFIG ID`. The rest of the UI is Traditional Chinese (title-cased). A user who can't decode the field name has zero recourse — there is no translation, no tooltip, nothing.
- [P1] **No parameter descriptions anywhere.** A user staring at `CONDITION ON PREVIOUS TEXT` cannot guess what it does without reading the faster-whisper source. The schema-driven form surfaces the keys but drops the intent.
- [P1] **`LANGUAGE` and `LANGUAGE CONFIG ID` both appear with the same label styling**, despite referring to two different things (Whisper language code vs reference to a language-config preset file). Their adjacency plus name similarity reads as either redundancy or confusion — neither is good.
- [P2] **Boolean fields are rendered as dropdowns** (`true` / `false`). `renderParamField` treats `type: "boolean"` as a `<select>` with two options instead of a toggle switch. This inflates vertical space and misrepresents the control.
- [P2] **No defaults indicator.** The user cannot tell whether `medium` is the default `MODEL SIZE` or a value they once overrode. There is no `(預設)` marker, no reset-to-default control.
- [P2] **`MODEL SIZE`** has no hint about the quality/latency trade-off. A newcomer does not know `medium` is the middle of a five-step curve — should they go `small` to save RAM or `large` for accuracy?
- [P2] **No field grouping**. All four parameters are stacked with identical weight. Language-related fields should be visually clustered; quality fields should be clustered. Right now the eye cannot find related knobs.
- [P3] **Dropdown chevron contrast is low** against the dark background — the `▼` is tiny and muted.
- [P3] **Label casing is inconsistent** inside the same card: `引擎` and `引擎參數` are Chinese, the parameter labels are ALL-CAPS English. Looks like two different designers wrote two halves of the form.

**Recommendations:**
1. **Extend the schema**: have `get_params_schema()` return `label` (localized display string) and `description` (tooltip copy) alongside `type`, `default`, and `enum`. Frontend renders the label instead of the key. Example:
   ```json
   "condition_on_previous_text": {
     "type": "boolean",
     "label": "條件於前文",
     "description": "讓 Whisper 參考前一句嘅 context，準但會放大錯誤",
     "default": true
   }
   ```
2. **Render booleans as toggle switches** (`.switch` component with left/right states), not dropdowns.
3. **Hide `language_config_id` or rename + describe it** as `語言預設檔 (自動)` with a tooltip: "揀返語言時自動選擇對應 tuning preset"; consider making it read-only once language is chosen.
4. **Default markers**: add a subtle `(預設)` badge next to the default option inside each dropdown, and a trailing `↺` "重設" icon button to each row that snaps the value back to the schema default.
5. **Model size tradeoff strip**: under `MODEL SIZE` render a small horizontal scale like `tiny · small · medium · large · large-v3` with `⚡ 快` on the left and `🎯 準` on the right.
6. **Introduce field groups**: wrap `language` + `language_config_id` in a `<fieldset>` with a small group header `語言`; wrap quality params in `<fieldset>` labelled `品質`.
7. **Improve dropdown chevron**: use a larger, higher-contrast `▾` via an icon font or inline SVG so the affordance is visible at a glance.
8. **Normalise all labels to Traditional Chinese title case**. All caps English stays only when the schema key is genuinely an identifier (and even then, render it dim as auxiliary text under the humanized label).

**Estimated impact:** high — ASR params directly control output quality; the current surface is hostile to non-experts
**Estimated effort:** M — coordinated backend schema change + frontend rendering update; no DB / migration work

---

### Area 8: Profile form — Translation engine dropdown (local/cloud optgroup)

**Screenshot:** `screenshots/08_profile-form-translation-engine.png`

**What works:**
- The new `is_cloud`-grouped dropdown and `✓ / ⚠` availability prefix from the `feature/ollama-cloud-models` merge are visible and functional
- `● 可用` availability indicator sits beside the engine dropdown — immediate at-a-glance state
- A dedicated `☁ Ollama Cloud 登入` button sits inline next to the selector, contextually placed
- `Model: <tag> ✓ 已載入` line gives the underlying Ollama model tag, useful for reproducibility
- `詞彙表` lives inside the same section so the user can wire glossary during engine setup
- Section header is collapsible, matching the ASR section pattern

**Issues observed:**
- [P1] **Engine dropdown text is truncated.** `✓ gpt-oss-1...` shows only 10 visible characters before cutoff. The full key `gpt-oss-120b-cloud` is 18 chars — with the `✓` prefix it cannot fit in the current narrow layout. The dropdown shares its row with the availability dot and the "Ollama Cloud 登入" button, so there is no room to breathe.
- [P1] **`Model: qwen2.5:3b ✓ 已載入` is a real bug, not just a UI quirk.** The active engine is `gpt-oss-120b-cloud`, yet the label shows `qwen2.5:3b`. The root cause is in `onTranslationEngineChange()` (and the parallel logic on form open): it reads `modelsData.models[0]` and prints that entry unconditionally. Because `OllamaTranslationEngine.get_models()` iterates `ENGINE_TO_MODEL` in insertion order, `models[0]` is always `qwen2.5:3b`. Fix is one line in the frontend (`models.find(x => x.engine === trEngine)`) or the backend endpoint should return only the matching engine's model.
- [P1] **Parameter labels are the raw ALL-CAPS schema keys again**: `BATCH SIZE`, `CONTEXT WINDOW`, `STYLE`, `TEMPERATURE`. Same issue as Area 7 — the schema-driven renderer drops localization and humanization.
- [P2] **`TEMPERATURE` is a plain text input** for a bounded `0 → 2` float. A slider with markers at 0 / 0.5 / 1 / 2 would make the semantics (deterministic vs creative) legible at a glance and avoid invalid values.
- [P2] **`BATCH SIZE` is a plain text input** with no visible min/max. The schema declares `minimum: 1, maximum: 50` but the control does not enforce or surface those bounds.
- [P2] **`STYLE` renders as a dropdown** despite having only two options (`formal` / `cantonese`). A segmented control (`書面語 | 粵語`) would show both options at once with zero click cost.
- [P2] **`Ollama Cloud 登入` button is visually quiet** — it's a small outlined pill next to the availability dot. First-time users facing a `⚠` cloud model may not spot it as the fix path.
- [P2] **`引擎參數` sub-header is the same weak styling as ASR**, so the eye cannot distinguish the params block from the engine-selection block above it.
- [P3] **`詞彙表` sits inside `翻譯設定`** but feels detached from the translation params above it — no divider, no mini header.
- [P3] **No test-translation affordance.** For cloud engines that depend on `ollama signin`, the user has no way to verify the model actually works before committing to a full 57-segment translation run.
- [P3] **Dropdown chevron contrast is low**, same as the ASR section.

**Recommendations:**
1. **Give the engine dropdown the full row width** so the full engine key is visible. Move `● 可用` + `Ollama Cloud 登入` to a secondary row below the dropdown.
2. **Fix the `Model:` label bug** (one-line frontend fix or tighten the `/models` endpoint):
   ```js
   // Before
   const m = models[0];
   // After
   const m = models.find(x => x.engine === trEngine) || models[0];
   ```
3. **Humanize param labels** via the schema-metadata approach proposed in Area 7: `batch_size` → `批次大小`, `temperature` → `溫度`, `style` → `翻譯風格`, `context_window` → `上下文視窗`.
4. **Render `temperature` as a slider** with markers at 0 / 0.5 / 1 / 2 and tooltip: "0 = 穩定 · 1 = 平衡 · 2 = 創意". Live numeric readout on the right.
5. **Render `batch_size` as a stepper** (`− 10 +`) or at least `<input type="number" min="1" max="50">`.
6. **Render `style` as a segmented toggle** (`[書面語] [粵語]`) — two options shown at once, single click to pick, no hidden state.
7. **Promote the `Ollama Cloud 登入` button** when a cloud engine is selected and `available === false`: upgrade it to a primary-outline CTA, show it on its own row with a subtitle ("一次登入，雲端模型即可使用"), and hide it when local engines are selected.
8. **Add a `🧪 試譯` button** at the bottom of the translation section that POSTs a fixed English sample ("Good evening, welcome to the news.") to `/api/translate` with the current unsaved config and inlines the output. Immediate feedback = trust.
9. **Separate `詞彙表`** with a thin rule divider and a mini header `詞彙表注入` so it reads as a distinct "plug this glossary into every translate call" toggle.

**Estimated impact:** high — translation controls are consulted on every transcription run, and the section currently contains an actual incorrect status label
**Estimated effort:** M — bug fix + `renderParamField` upgrades (slider, stepper, segmented) + row layout rework; no backend changes beyond the optional `/models` tightening

---

### Area 9: Profile form — Font configuration section

**Screenshot:** `screenshots/09_profile-form-font.png`

**What works:**
- Range hints are baked into the labels: `FONT SIZE (12-120)`, `OUTLINE WIDTH (0-10)`, `MARGIN BOTTOM (0-200)`. Users know the valid range before typing.
- Native `<input type="color">` for fill and outline — zero dependencies, works everywhere
- `POSITION` is a dropdown (likely Top / Middle / Bottom) — appropriate control for an enumeration
- Numeric fields use `<input type="number">` with `min`/`max` attributes, so browser validation fires automatically
- Section is collapsible to stay out of the way when the user isn't styling

**Issues observed:**
- [P1] **No live preview anywhere.** This is the single biggest gap. A user configuring font family, size, colour, outline and position has no visual feedback until they save the profile, run a transcription, and render the output. That is a 5-minute feedback loop for a visual decision.
- [P1] **ALL-CAPS English labels** (`FONT FAMILY`, `FONT SIZE`, `COLOR`, `OUTLINE COLOR`, `OUTLINE WIDTH`, `POSITION`, `MARGIN BOTTOM`) against a Chinese section header (`字型設定`). Same schema-key leakage as Areas 7 and 8, but more glaring here because these are properties users directly perceive on the final output.
- [P1] **`FONT FAMILY` is free text.** A user can type `Comic Sans MS` or `Noto Sans CJK` and the form accepts it. FFmpeg / fontconfig will silently pick a fallback when rendering if the font isn't installed. No validation, no warning, just a surprise at render time.
- [P2] **Colour pickers are thin horizontal bars** with no hex readout next to them. User cannot tell what `#ffffff` vs `#fafafa` looks like — both read as "white". No alpha channel support, so semi-transparent or anti-banding subtitles cannot be configured.
- [P2] **`COLOR` and `OUTLINE COLOR` are visually indistinguishable** at a glance — both render as identical horizontal colour bars. Only the label tells them apart. Grouping and iconography would help.
- [P2] **`POSITION` as a dropdown** for a 2-3 option enumeration wastes a click. Segmented toggle (`[⬆ 頂] [⟷ 中] [⬇ 底]`) would show all options at once.
- [P2] **`MARGIN BOTTOM` unit is unspecified.** Is 40 in pixels? Percent? The label says `(0-200)` but users cannot infer that 200 means "200 pixels from the bottom of the video frame".
- [P2] **No reset-to-default.** If a user experiments and gets lost, they must remember the original broadcast defaults or reload the form.
- [P3] **No field grouping.** Colours should cluster; size/outline should cluster; position/margin should cluster. Seven flat fields force the eye to scan linearly.
- [P3] **No preview of what "Noto Sans TC" actually looks like** in a Chinese font picker — users who don't know the name have to guess.

**Recommendations:**
1. **Add a live preview strip** at the top of the 字型設定 section: a small dark rectangle (~240 × 60 px) simulating a video frame, with a sample subtitle ("🎬 各位晚上好 · preview") that re-renders on every change to any font field. Pure CSS — no FFmpeg invocation needed. This alone eliminates 80% of the friction.
2. **Humanize all labels in Traditional Chinese**: `字體`, `字號`, `字體顏色`, `描邊顏色`, `描邊粗度`, `位置`, `底部邊距 (px)`. Put the original schema key as a tiny auxiliary label underneath only when debugging.
3. **Replace the free-text `FONT FAMILY` input** with a searchable dropdown populated from a new backend endpoint `/api/fonts` that queries `fc-list` or `ffmpeg -f lavfi -i fontfile=...`. Include a text fallback for advanced users.
4. **Upgrade colour pickers**: larger swatches, a hex-code readout inline, and an alpha slider for semi-transparent support (useful for karaoke-style or lower-third styling).
5. **Render `POSITION` as a segmented control** with icons and labels: `[⬆ 頂部] [⟷ 中] [⬇ 底部]`.
6. **Add unit suffixes** directly to the numeric inputs: `底部邊距` field should show "40 px" with the unit as an `<span class="input-suffix">`.
7. **Add `↺ 還原預設` button** in the section footer that snaps all seven fields to broadcast defaults (`Noto Sans TC`, 48, white, black, 2, bottom, 40).
8. **Introduce sub-groupings with thin dividers**: [字體 + 字號] / [字體顏色 + 描邊顏色 + 描邊粗度] / [位置 + 底部邊距]. Group headers can be small caps in `--text-dim`.
9. **Include a sample char-set preview** next to the font family dropdown: show `繁體中文 abc 123` in the selected font so users can visually confirm before saving.

**Estimated impact:** high — subtitle appearance is the user-visible output of the whole pipeline; the current form is a "save, render, wait, repeat" feedback loop
**Estimated effort:** M — preview strip is small CSS/JS work; label humanization is trivial; font dropdown is the only new backend hook

---

### Area 10: Transcription progress bar + ETA

**Screenshot:** `screenshots/10_progress-bar.png`
*Captured with a simulated `.file-card-progress` block injected into the DOM (the registry has no live transcription at review time).*

**What works:**
- Triple-metric info row is genuinely useful: `processed / total` audio time, percentage, and estimated remaining time — a user can answer "how long until it's done" without doing arithmetic
- Orange/amber `轉錄中` pill is distinct from the green `完成` badge, so lifecycle states are colour-coded
- Progress bar fill uses the brand purple, matching the rest of the accent language
- ETA (`預計剩餘 02:23`) is computed from the segment stream rate — reasonable use of live data
- The active card shows a brighter purple border, giving a "you are here" cue when there are multiple cards

**Issues observed:**
- [P1] **Progress bar is very thin (~4-5 px).** On a 1440-wide card it reads as a hairline. A user scanning multiple cards will easily miss which one is mid-run, especially if the card is below the fold.
- [P1] **No cancel affordance.** Once transcription starts there is no stop button, no keyboard shortcut, no way to abort — the user has to wait or close the tab. For a 10-minute cloud run this is genuinely painful.
- [P1] **The progress info row mixes three priorities but does not rank them.** Percent is centered and bold; ETA is right-aligned in smaller text. For most users "when will this finish" is more important than "what fraction is done". The hierarchy is inverted.
- [P2] **No stage indicator.** The pipeline has multiple phases: audio extract → Whisper ASR → auto-translate. The single progress bar shows "overall" progress but provides no visibility into which phase is running. A user at 42% cannot tell whether translation is about to start or has already finished.
- [P2] **`轉錄中` pill has no motion cue.** It is a static orange block. A subtle pulse or leading spinner would reinforce "this is actively working" vs a stale-looking label.
- [P2] **No provenance metadata during progress**: which ASR engine, which translation model, which profile. If the user is watching multiple cards they have to remember which profile each one was started with.
- [P2] **If cloud translation hits a retry**, the user has no visual signal. The stderr `[ollama] retry` line we added in the feature branch is backend-only; the frontend card does not surface it. A sudden slowdown looks like a hang.
- [P3] **No running segment count** (e.g. `已生成 18 段`). For long videos this gives confidence the stream is producing output.
- [P3] **Progress info elements compete for the same row**; on narrow viewports they may wrap unpredictably.
- [P3] **The delete-button slot is empty but not visibly disabled** during transcription — a user hunting for "stop" may look there and find nothing.

**Recommendations:**
1. **Thicken the progress bar** from ~4 px to 8-10 px and add a subtle gradient (`linear-gradient(to right, var(--accent), var(--accent2))`) so it reads as a solid "this is working" ribbon.
2. **Add a cancel button**: a small `⊘ 取消` text link on the right end of the progress row, with a confirm dialog. Backend needs a `POST /api/files/<id>/cancel` endpoint but the immediate frontend win is enabling the affordance.
3. **Reverse the hierarchy of the info row**: ETA becomes the largest bold element (`預計 02:23 後完成`), percent becomes a subdued auxiliary number, processed/total is tertiary.
4. **Stage strip above the progress bar**: three small pills in a row `[🎤 音訊 → 📝 轉譯 → 🌐 翻譯]` with the current phase highlighted and the next two dimmed. This makes the multi-phase pipeline legible.
5. **Animate the `轉錄中` pill**: CSS `@keyframes` pulsing background opacity, or a leading spinner glyph `⟳`.
6. **Surface provenance during progress**: under the filename, show `· mlx-whisper medium · gpt-oss-120b-cloud · cantonese` in dim text.
7. **Surface cloud retries**: when the frontend receives a socket event `ollama_retry` (to be added), show a small `⚠ 雲端延遲，已自動重試` chip near the ETA with a tooltip.
8. **Add a live segment counter**: `已生成 18 段` under the progress bar, appended as each `subtitle_segment` event comes in.
9. **Explicitly disable or hide the delete-button slot during `transcribing`**: render a disabled `⊘` with `title="處理中無法刪除"` so the affordance status is visible.

**Estimated impact:** high — users stare at this component while waiting for the core pipeline; friction here is highly visible
**Estimated effort:** M — CSS changes + cancel endpoint + stage tracking in the frontend socket handler + a few minor socket events

---

### Area 11: Real-time subtitle segment display during transcription

**Screenshot:** `screenshots/11_subtitle-segments.png`
*Captured by injecting a six-segment mock into `#transcriptList` since no live transcription was running at review time.*

**What works:**
- Each segment is its own card with clear visual separation — easy to parse
- Timestamps are in a dedicated column with monospace font, so the eye can scan the time progression cleanly
- Purple accent on timestamps matches the rest of the brand vocabulary
- Generous line-height on the text keeps long sentences readable
- `#segmentCount` in the panel header reflects live count (`6 段` in the mock)
- Empty state with a friendly icon and copy handles the zero-segment case

**Issues observed:**
- [P1] **No auto-scroll management**. When a new segment arrives during a live run, the panel does not announce scrolling behaviour: if the user has scrolled up to read an earlier segment, do they get pulled back down? If so, that's disruptive. If not, they may miss new content. Neither strategy is visibly chosen.
- [P1] **Timestamps are raw seconds (`0.0s`, `14.5s`)** regardless of video length. A 45-minute broadcast would show `1823.7s` — unreadable. MM:SS (or HH:MM:SS for very long videos) is standard.
- [P1] **No click-to-seek affordance.** The segments look read-only. If the underlying logic supports click-to-jump, it is invisible (no cursor, no hover, no underline). If it does not, that's a missing first-class feature — jumping to a specific spoken line is the primary reason users open the dashboard.
- [P2] **No "currently playing" segment highlight.** During video playback the row whose time range matches the current playhead should glow. This is standard subtitle-editor UX, and its absence makes the transcript feel disconnected from the video.
- [P2] **No per-segment duration** (e.g. a subtle `2.5s` badge). Users debugging "why is this subtitle too fast" cannot see segment duration without arithmetic.
- [P2] **No edit affordance on the dashboard list.** Fix-a-typo requires opening the proofread editor. The transcript list could support inline light edits.
- [P2] **No copy-to-clipboard** on individual rows. Quoting a segment requires manual selection.
- [P3] **New segments pop in abruptly** during live runs — no slide-in or fade-in animation. A live transcript should feel alive.
- [P3] **No paragraph grouping** between sentences with long silence gaps. A 5-second gap and a 0.2-second gap render identically.
- [P3] **Timestamp widths vary** because the raw second format does not left-pad. On long videos `1:23:45` next to `0:01` produces a jagged left column.

**Recommendations:**
1. **Auto-scroll with pause-on-user-interaction**: hook into `#transcriptList` wheel/scroll events. If the user scrolls up, stop auto-scrolling and show a floating `↓ 跳到最新 (3)` button that also acts as a "new segments" counter. Click to resume.
2. **Humanize timestamps**: use `mm:ss` for videos ≤ 1 hour, `h:mm:ss` otherwise. Keep monospace so alignment stays true. Format via a `formatTimestamp(seconds)` helper.
3. **Make segments click-to-seek**: `cursor: pointer`, background tint on hover, `onclick` sets the video player `currentTime = segment.start`. Add `role="button"` + `tabindex="0"` + keyboard handler for accessibility.
4. **Highlight current segment during playback**: use the video element's `timeupdate` event to add `.transcript-item.playing` class to the segment whose range contains `currentTime`. Purple left border + brighter background.
5. **Show per-segment duration**: small right-aligned badge `${duration.toFixed(1)}s`, tinted red when `duration < 1` or `duration > 8`, giving a visual hint for problematic segments.
6. **Inline edit on double-click**: double-click a segment to turn the text span into a `contenteditable` field; `Enter` commits via `PATCH /api/files/<id>/segments/<sid>`.
7. **Copy-on-hover**: small `📋` icon that appears on row hover, copies plain text to clipboard with a toast confirmation.
8. **Slide-in animation** for new segments (respecting `prefers-reduced-motion`).
9. **Paragraph gap detection**: when `(segment.start - previous.end) > 2`, render an 8px margin-top on the new row so paragraphs visually breathe.
10. **Left-pad the timestamp column to a fixed width** based on the longest timestamp in the list — no alignment jitter.

**Estimated impact:** high — the transcript list is the second-most-scanned surface during active work; unlocking click-to-seek alone turns it into a real editor
**Estimated effort:** M — independent sub-features (~5 features × ~1 hour each); no backend changes needed

---
