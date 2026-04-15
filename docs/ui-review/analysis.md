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
- [x] 12. Translation status badge + re-translate button flow
- [x] 13. Language config panel
- [x] 14. Glossary management panel
- [x] 15. Proofread editor — video player controls
- [x] 16. Proofread editor — segment table editing UX
- [x] 17. Proofread editor — approval buttons (per-segment + bulk)
- [x] 18. Proofread editor — keyboard shortcuts discoverability
- [x] 19. Error states (upload/API/translation failures)
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

### Area 12: Translation status badge + re-translate button flow

**Screenshot:** `screenshots/12_translation-status-flow.png`
*Three synthetic cards injected into the file list to show all lifecycle states side-by-side: `待翻譯`, `翻譯中...`, `翻譯完成`.*

**What works:**
- The three states use distinct colour families (grey → orange → green), making the lifecycle scannable
- The primary action button adapts its label: `▶ 翻譯` when idle, disabled during processing, `🔄 重新翻譯` when done — semantically correct
- `校對` (proofread) stays visible in all three states, so the user is never blocked from reviewing transcripts regardless of translation state
- Translation engine chip (`qwen3.5-397b-cloud`, `gpt-oss-120b-cloud`) records which engine produced each file
- Active card border (purple) marks the file currently being translated, consistent with the transcription progress pattern

**Issues observed:**
- [P1] **Two "done" badges on the same card** (`完成` top-right for transcription, `翻譯完成` row 2 for translation) share the same green pill styling. Re-flagged from Area 3 — this remains a core visual ambiguity.
- [P1] **No translation progress indicator.** Transcription has a progress bar + ETA; translation has only a static text pill `翻譯中...`. For cloud translations that take 5-10 minutes the user has no sense of where they are. This is the single biggest gap in the translation flow.
- [P1] **`翻譯中...` pill is static** — the ellipsis suggests motion but no CSS animation fires. Users cannot tell live progress from a hung state.
- [P2] **Disabled state on `▶ 翻譯` during processing is visually weak.** It dims only slightly. A user may still click expecting a no-op; clearer `opacity: 0.4 + cursor: not-allowed + tooltip` would be unambiguous.
- [P2] **Icon vocabulary mismatch:** `▶` (play) for initial translation, `🔄` (refresh) for re-translate. Same action (start a translate run), two different icons. Users have to relearn per state.
- [P2] **No abort affordance** during `翻譯中`. Same problem as transcription (Area 10) — a wrong-profile run cannot be stopped.
- [P2] **Error state is invisible.** If translation fails (all retries exhausted, cloud signin lost, network dead), there is no red badge, no `翻譯失敗` pill, no inline error message. The frontend shows errors as transient toasts that vanish after a few seconds — the card reverts to the previous state with no persistent trail.
- [P2] **`[TRANSLATION MISSING]` partial failures are not surfaced.** The backend PostProcessor may leave placeholder strings in the output when retries don't fix everything. The UI shows a full green `翻譯完成` badge even when 3 of 41 segments are broken — silent data quality loss.
- [P3] **No "last run" metadata.** User cannot tell when the translation finished (5 min ago? yesterday?) or how long it took.
- [P3] **No per-file prompt override.** If the user wants to tweak translation style for one file only (e.g. more casual for an interview), they must create a new profile.

**Recommendations:**
1. **Disambiguate the two completion badges** per Area 3 rec #1: outlined `轉譯 ✓` vs filled `翻譯 ✓`.
2. **Add a translation progress bar + ETA**: reuse the existing `.file-card-progress` component during `translation_status === 'translating'`. Backend should emit a `translation_progress` socket event per batch (`{ batch: 3, total: 12, eta_seconds: 180 }`).
3. **Animate `翻譯中...`**: pulse the orange background via `@keyframes` or add a leading spinner `⟳ 翻譯中`.
4. **Stronger disabled state**: `.btn[disabled] { opacity: 0.35; cursor: not-allowed; }` + tooltip `title="翻譯進行中，請稍候"`.
5. **Unify icon vocabulary**: use `🌐` for "start translation" in both idle and done states; keep `🔄` for explicit retry-after-failure only.
6. **Cancel control**: `⊘ 取消翻譯` link adjacent to the progress bar during `翻譯中`. Needs a backend `POST /api/files/<id>/translation/cancel` endpoint.
7. **Error badge and inline error panel**: on translation failure, set badge to red `翻譯失敗` and add a small error detail tooltip showing the last backend error. Include a `重試` button with the same styling as `🌐 翻譯`.
8. **Partial-failure badge**: if any segment has `[TRANSLATION MISSING]`, render amber `翻譯完成 · N 段異常` with a `檢視` action that jumps to the proofread editor filtered to problem segments.
9. **Last-run metadata** in the chip row: `gpt-oss-120b-cloud · 14:32 · 5 分鐘`.
10. **Per-file override** as an overflow menu item: `⋯ → 調整翻譯風格 (此檔案)` opens a mini modal with temperature + style sliders.

**Estimated impact:** high — translation is half of the product; missing progress + error visibility is a top-3 friction
**Estimated effort:** M — frontend progress reuse + a couple of new socket events + small cancel endpoint + error state rendering

---

### Area 13: Language config panel

**Screenshot:** `screenshots/13_language-config.png`

**What works:**
- Clear panel header `🌐 語言配置` with a globe icon and arrow-based collapse affordance
- Native `<select>` for language picks; shows the localized label `English (en)`
- Four parameters cover both sides of the pipeline (ASR segmentation + translation tuning) that are genuinely language-specific
- Unit disclosed in the label: `每句最大時長 (秒)` — explicit seconds
- Save button is a prominent full-width purple primary action
- Collapsible so the panel doesn't dominate the sidebar when unused

**Issues observed:**
- [P1] **Three different label casing conventions inside one panel**: `LANGUAGE` (ALL CAPS English), `每句最大字數` (Chinese), `翻譯 BATCH SIZE` (Chinese prefix + ALL CAPS English suffix). Looks like two different authors wrote the labels.
- [P1] **No explanation of what these parameters do.** The panel is a config dump with zero guidance: why would a user change `max_words_per_segment` from 25 to 40? When does `temperature` matter? New users cannot safely tune these without reading the source code.
- [P1] **No dirty-state indicator and no "unsaved changes" protection.** A user can change `batch_size` from 8 to 20, forget to click save, collapse the panel, and lose the change with no warning or visual cue.
- [P2] **No reset-to-default control.** A user who experiments into a broken state cannot easily recover without remembering or looking up the original numbers.
- [P2] **Temperature is a plain `<input type="number">`** for a bounded `0 → 2` range — same pain point as Area 8. A slider would be more discoverable and bound-respecting.
- [P2] **Save scope is ambiguous.** Does saving affect all profiles currently using `en`? Does it affect already-transcribed files? The button label `儲存語言配置` does not answer.
- [P2] **No way to add a new language.** The dropdown is populated from backend; if a user wants `ja` or `ko`, there is no path to create the config file.
- [P2] **Fields are flat-stacked.** ASR segmentation params (max_words, max_duration) and translation params (batch_size, temperature) belong to two different phases but are visually identical rows in a single list.
- [P3] **No hint about "normal" values.** A user seeing `每句最大字數 = 25` has no idea whether that's aggressive, typical, or loose. A tiny range hint (`5 - 200, typical: 20-40`) would orient them.
- [P3] **Save button is inside the collapsible body.** On smaller viewports it may fall below the fold.
- [P3] **Save feedback is a transient toast** — easy to miss. A persistent "Last saved at HH:MM" indicator would be clearer.

**Recommendations:**
1. **Normalize all labels to Traditional Chinese title case**: `語言`, `每句最多字數`, `每句最長時間 (秒)`, `翻譯批次大小`, `翻譯溫度`. Drop ALL CAPS English entirely.
2. **Add per-field helper copy** (dim small text under each input). Examples:
   - `每句最多字數`: "超過就會自動切句。太細會切得碎，太大會有過長字幕。典型值 20–40。"
   - `翻譯溫度`: "0 = 穩定一致, 1 = 平衡, 2 = 創意。翻譯新聞保留 0.1。"
3. **Track dirty state**: hook `input` events on all fields; set a `● 未儲存` chip next to the panel header and near the save button. Add a `beforeunload` / collapse guard that asks "捨棄變更？".
4. **Add a `↺ 還原預設` ghost button** next to save, which repopulates the fields from the backend default (a new `GET /api/languages/<id>/default` endpoint or embed defaults in the same response).
5. **Render temperature as a slider** (0–2, step 0.1) with markers at 0 / 0.5 / 1 / 2 and a live readout.
6. **Clarify save scope**: rename button to `儲存 (影響所有使用 English 的 Profile)` or add an `ℹ` info icon with tooltip: "更新後, 新嘅轉譯會用新設定; 已完成嘅檔案唔會動。"
7. **Sub-groups with headers**: wrap `max_words` + `max_duration` under `<fieldset><legend>ASR 分段</legend>` and `batch_size` + `temperature` under `<fieldset><legend>翻譯參數</legend>`.
8. **Add "新增語言" flow** as a trailing link in the language dropdown (`+ 新增語言...`) that opens a mini form for creating a new language-config file.
9. **Persistent save feedback**: replace the toast with an inline `✓ 已儲存於 14:32:05` line adjacent to the save button, fading to 40% opacity after 5 s.
10. **Show delta vs default** inline: if a user has overridden `max_words` from default 20 to 25, render `25 (預設 20)` in the placeholder space.

**Estimated impact:** medium-high — language config is where users tune pipeline quality; currently it's an opaque config dump
**Estimated effort:** S-M — mostly copy/CSS/attribute changes + dirty-state tracking + slider component

---

### Area 14: Glossary management panel

**Screenshot:** `screenshots/14_glossary-panel.png`

**What works:**
- Two-column `EN / 中文` layout matches the underlying data model 1:1
- Entry count is surfaced in the dropdown label (`Broadcast News (1 entries)`) — immediate data-size awareness
- Inline add row: two inputs + `新增` button on a single line, no modal gymnastics
- Per-row delete `×` rendered in red — destructive action is colour-coded
- `📥 匯入 CSV` link for bulk loading
- Collapsible section keeps the panel out of the way when not in use

**Issues observed:**
- [P1] **Existing entry shows `Micahel → 23468`** — typoed English ("Micahel" instead of "Michael") and a purely numeric "Chinese" translation. The UI accepted both without validation. No format check for the English side, no CJK-presence check for the Chinese side. This is a direct data-quality regression into the translation prompt.
- [P1] **Delete `×` has no confirmation.** Single-click permanent delete on an already-persisted entry, adjacent to live data. High mis-click risk with zero recovery.
- [P1] **No edit affordance on existing rows.** To fix `Micahel → Michael`, the user must delete the bad row and recreate it. Inline-edit on click/double-click is the expected behaviour for a tabular glossary.
- [P2] **`1 entries` is ungrammatical** — should be `1 entry` in English or `1 條` / `1 項` in Chinese. Affects singular case in all copies.
- [P2] **No search or filter.** With more than ~20 entries the panel becomes an unusable scroll.
- [P2] **No sort controls.** Entries appear in insertion order; no header click to sort A → Z or reverse.
- [P2] **`新增` button is always enabled**, even when both input fields are empty. Clicking with empty fields produces either a silent no-op or an error toast — neither discoverable from the idle state.
- [P2] **No CSV export** shown in this panel. Import is visible but export is not — asymmetric and confusing when users want to back up their glossary.
- [P2] **No purpose description** anywhere. A first-time user cannot tell whether terms are regex-matched, whole-word, case-sensitive, or inserted into the LLM prompt as examples. The absence of an explainer leads to misuse.
- [P3] **`GLOSSARY` label is ALL CAPS English** — same pattern leak as Area 7 and Area 13, inconsistent with the panel header `術語表`.
- [P3] **Single glossary dropdown** has no `+ 新增詞彙表` option. Creating new glossaries requires an unexplained path.
- [P3] **No hint about what counts as "good"**: should glossaries contain proper nouns only? Multi-word phrases? Regex? Case variants?

**Recommendations:**
1. **Input validation**:
   - English field: reject empty, warn on non-ASCII/CJK, minimum 1 letter
   - Chinese field: require at least one CJK character; warn on "pure number" / "pure ASCII" input
   - Disable `新增` until both pass validation; show inline red error under the offending field
2. **Confirm dialog on delete**: a native `confirm("確定刪除 'Michael → 邁克爾'？")` or a small modal. Include the entry pair in the question.
3. **Inline edit on double-click**: turn cells into `contenteditable` spans; `Enter` commits via `PATCH /api/glossaries/<id>/entries/<eid>`; `Escape` cancels.
4. **Fix the i18n count string**: `${n} ${n === 1 ? 'entry' : 'entries'}` or fully Chinese `${n} 條`.
5. **Add a search input** above the entry list with live client-side filtering; `🔍 搜尋術語` placeholder.
6. **Add sortable headers** — click `EN` to sort by English A-Z / Z-A; click `中文` similarly.
7. **Disable `新增` when invalid**: `opacity: 0.35; pointer-events: none;` with tooltip explaining why.
8. **Add `📤 匯出 CSV`** link adjacent to `📥 匯入 CSV` at the panel footer.
9. **Humanize all labels**: `GLOSSARY` → `詞彙表`, column headers `EN` / `中文` → `原文` / `翻譯`.
10. **Add `+ 新增詞彙表`** option at the top of the glossary dropdown, opening a small inline name+save flow.
11. **Add a purpose explainer** under the header: "術語表會注入到翻譯 prompt 做 few-shot examples, 確保專有名詞一致。建議每個 Profile 綁一個相關嘅 glossary。"
12. **Move `×` into an overflow menu** `⋯` with explicit label "刪除此詞彙" and the confirm dialog.

**Estimated impact:** medium — direct impact on translation quality via the prompt; current "Micahel → 23468" shows the validation gap is already producing bad data
**Estimated effort:** S-M — frontend work + basic validation; inline edit adds the most value for effort

---

### Area 15: Proofread editor — video player controls

**Screenshot:** `screenshots/15_proofread-video-player.png`
*Loaded with `file_id=e00d4db3c61c` (41-segment interview clip, translation done).*

**What works:**
- Native HTML5 `<video>` element + native browser controls: zero dependencies, works in every browser
- Total duration is visible in the corner (`0:00 / 1:43`) so the user knows the clip length up front
- `← 返回主頁` navigation link is top-left — standard pattern for a detail page
- **Keyboard shortcut hints are rendered directly below the player**: `Space` 播放/暫停, `↑` 上一段, `↓` 下一段, `←` 往前 5 秒, `→` 往後 5 秒, `Enter` 確認核對, `Esc` 取消. Excellent discoverability of the proofread-specific hotkeys.
- Shortcut labels are localized in Traditional Chinese
- The `字幕校對 ▾` heading acts as a file-context marker

**Issues observed:**
- [P1] **No subtitle overlay on the video.** The user is proofreading translations but the video plays with no rendered captions at all — the Cantonese output is only visible in the side table. There is no way to answer "what will the final rendered output look like?" without running `/api/render` and downloading an MP4.
- [P1] **Native browser controls break visual consistency.** On macOS Safari the controls are grey-gradient; on Chrome they are dark with white; on Firefox they are flat. The rest of the app uses a specific dark-purple design language, and the video bar stands out.
- [P2] **Keyboard hints are below the native control bar**, which means they compete with the scrubber for vertical space and are the last thing in the visual scan. Users who don't know about them will miss them until they scroll to the bottom of the viewport.
- [P2] **No playback speed control**. For proofreading dense speech, 0.5x / 0.75x are essential. The native `<video>` API supports this but via right-click menu only, which is not discoverable.
- [P2] **No loop-current-segment** button. Standard proofread workflow is "play this segment again". The only way to do this currently is manually scrubbing back each time.
- [P2] **No visible "jump N seconds" buttons** in the UI — only the keyboard shortcuts. Touch/mouse users are stranded.
- [P2] **`字幕校對 ▾` arrow** suggests a dropdown but does not visibly open anything; the affordance is unclear.
- [P3] **No source captions track** (original English) available in the player. Proofreading against the source would be faster if both the source and target were visible simultaneously.
- [P3] **No scrubber tick marks** showing segment boundaries — every segment requires a round-trip to the side table to jump.
- [P3] **No thumbnail preview** on scrubber hover (YouTube-style).
- [P3] **`← 返回主頁`** loses dashboard scroll position and file-selection state.

**Recommendations:**
1. **Overlay translated subtitles** on the video. Generate a WebVTT file from the current translations at page load (client-side, from the segments array) and wire it as `<track kind="subtitles" default>`. Style via CSS `::cue { ... }` using the profile's font config. The user now sees a live preview of the final output while proofreading.
2. **Replace native controls with custom player chrome** matching the app dark theme: play/pause, scrubber, volume, speed, fullscreen, loop-segment, jump-5s, segment counter. `<video controls={false}>` plus a thin controls bar component.
3. **Lift the keyboard hints** into a collapsible panel on the right, or a `?` help button that reveals them on click. Their current position is too easy to miss.
4. **Add speed dropdown** in the player chrome: `0.5x · 0.75x · 1x · 1.25x · 1.5x · 2x`, default 1x.
5. **Add loop-current-segment toggle** `⟲`: when active, video loops between `segment.start` and `segment.end` of the currently-focused segment.
6. **Add visible jump buttons**: `⏪ -5s` / `+5s ⏩` icons directly in the player chrome, duplicating the keyboard shortcut affordance for mouse users.
7. **Clarify `字幕校對 ▾`**: if it is intended as a file switcher, wire the dropdown to show other translated files; if not, remove the arrow.
8. **Add English captions as a secondary track** with a toggle button in the player chrome (`EN | 中 | off`).
9. **Render segment boundary ticks** as tiny vertical lines over the scrubber so users can see segment density and jump visually.
10. **Preserve dashboard state** on back: use `history.back()` when referrer is the dashboard; otherwise fall back to `index.html`.

**Estimated impact:** high — the proofread editor is where the user spends the most time per file; live subtitle preview alone eliminates the main feedback loop
**Estimated effort:** M-L — custom player chrome is the expensive piece; subtitle overlay via WebVTT is a few hours of work

---

### Area 16: Proofread editor — segment table editing UX

**Screenshot:** `screenshots/16_proofread-segment-table.png`

**What works:**
- Three-column layout `時間 | 原文 | 中文翻譯` + approval column matches the mental model of a translation table
- `已核准 0/41` counter in the header gives live approval progress
- Time cells use `mm:ss` format, concise and scannable
- The currently-focused segment is highlighted with a purple row background — "you are here" is clear
- Rows are compact enough to fit many segments in one viewport
- Cantonese translations are visible and reasonable quality (`呢場比賽壓力好大` / `氣勢全由我哋掌握`)
- Approval column on the far right gives a single-click binary toggle per segment
- Bottom action bar surfaces the format picker and "儲存並產生字幕" primary CTA

**Issues observed:**
- [P1] **No visible edit affordance on the 中文翻譯 cells.** Looking at the screenshot, users cannot tell which cells are editable, which are read-only, and how to trigger an edit. No pencil icon, no `cursor: text` hint, no hover state. The core action of the proofread editor is opaque.
- [P1] **No save-state feedback** after editing. If the user types a correction, there is no visible confirmation that the change was persisted via `PATCH /api/files/.../segments/<id>`. Silent save = user anxiety.
- [P1] **No visual differentiation between segment states.** An edited-but-unapproved row, a machine-only-untouched row, and an approved row all look nearly identical (only the purple row is "focused", not "state"). Scanning 41 rows for "which are still pending" is manual.
- [P2] **No segment number column.** For a 41-segment clip the user has no way to reference "segment 17 is wrong" without counting by hand.
- [P2] **No segment duration visible** inside the time cell. A subtitle longer than 8 seconds or shorter than 1 second is a red flag, but nothing surfaces it.
- [P2] **No search / filter** within the segment list. For a 5-minute broadcast with 100+ segments, finding "the one about the typhoon" requires scrolling and visually scanning.
- [P2] **No bulk-find-and-replace** despite the common broadcast need to enforce a term globally (e.g. every "Harry Kane" → "哈里·簡").
- [P2] **No diff vs original**. After editing, the user cannot see what the AI originally produced — no audit trail for why a change was made.
- [P3] **No quick-copy buttons** for EN or ZH text. Verifying with a colleague or quoting requires manual select + Cmd+C.
- [P3] **No "next unapproved" keyboard shortcut** visible in the hint strip. The hints mention `↓ 下一段` but not "skip to next un-approved".
- [P3] **Row height varies with wrapped text**. Long Cantonese lines wrap, making the table un-rhythmic.

**Recommendations:**
1. **Make `中文翻譯` cells explicitly editable**: `<div contenteditable="true">` or `<input>` with `cursor: text` and a subtle hover underline. On focus, show a tiny `Cmd+Enter 儲存 · Esc 取消` hint below the cell.
2. **Save feedback**: after each successful PATCH, flash the row background green for 300 ms and display a transient `✓ 已儲存` pill at the top of the table. On error, flash red + toast.
3. **Visual state system** with a left-border accent:
   - Default (untouched): no accent
   - Edited, pending approval: 3 px amber left border
   - Approved: 3 px green left border + cell text dimmed slightly
   - Contains `[TRANSLATION MISSING]`: 3 px red left border + warning icon
4. **Add `#` segment-number column**: width 40 px, right-aligned, monospace. Sticky to the leftmost so users can reference segments.
5. **Enrich the time cell**: show `mm:ss` on line 1 and `2.3s` duration on line 2 in dimmer text. Colour duration red for < 1 s or > 8 s.
6. **Search bar above the table**: single input that live-filters rows where EN or ZH contains the query. Keyboard shortcut `Cmd+K` to focus.
7. **Bulk find-replace dialog** (`Cmd+Shift+F`): modal with Find / Replace fields, scope toggle (`中文 only / 原文 only / 兩者`), and a "Preview" button showing affected segments before committing.
8. **Diff vs AI original**: store `zh_text_original` on each segment; render a subtle `↺` icon next to the current translation when it differs, with a hover tooltip showing the original.
9. **Copy-on-hover buttons**: two small icons on row hover — copy EN, copy ZH.
10. **Add keyboard shortcut `N` → next unapproved**: cycles through unapproved rows only, skipping approved ones. Add to the hint strip: `N 下一段未核准`.
11. **Normalize row height** with `max-height` + `text-overflow: ellipsis` + an expand-on-hover affordance. Or give each row a stable 2-line slot.

**Estimated impact:** high — this is the core editing surface of the app; any user doing real proofreading work will benefit
**Estimated effort:** M — inline edit + visual states + search are independent incremental wins; bulk replace is the most involved

---

### Area 17: Proofread editor — approval buttons (per-segment + bulk)

**Screenshot:** `screenshots/17_proofread-approvals.png`
*Captured with the first three segments toggled to approved via `.status-btn` clicks.*

**What works:**
- Clear binary visual state: green `✓` (approved) vs empty `○` (unapproved)
- Approval state updates immediately on click — no page reload or confirmation delay
- `已核准 X / 41` counter in the header provides live approval progress
- Separate `轉換編輯進度 7%` progress strip at the bottom left — approval completeness is tracked as its own metric
- Bulk-approve button `批核所有未改動 (N)` exists and is scoped to "untouched" segments only, so user edits aren't accidentally overwritten
- Per-button tooltips (`title="已核准（點擊取消）"` / `"點擊核准"`) exist
- ARIA labels on buttons (`已核准` / `未核准`) — accessibility win

**Issues observed:**
- [P1] **Bulk button label `批核所有未改動` is ambiguous.** New users may interpret it as "approve everything that isn't currently approved", when it actually means "approve only segments that haven't been edited since the AI produced them". The semantic difference matters: edited-but-unapproved segments are skipped silently. Label must be explicit.
- [P1] **No "approve everything including edited" fallback.** A user who wants to mass-approve the whole file (e.g. after reviewing everything manually) has no single-click option — they must click 41 circles. Missing the other half of the bulk-approve family.
- [P2] **Per-segment approval button is tiny (~20 px circle).** Hard to hit accurately on a trackpad; impossible on touch. Enlarge or convert to a pill.
- [P2] **No keyboard shortcut** for per-segment approval. The keyboard hint strip says `Enter 確認核准` but it's unclear whether Enter approves the currently-focused row or commits a text edit — two completely different actions sharing the same key.
- [P2] **No undo for bulk approval.** Clicking "批核所有未改動" is irreversible without clicking 30+ circles to uncheck.
- [P2] **Approval count in header is static text**, no animation when it changes. A user who just approved 15 segments gets no positive feedback.
- [P2] **No filter "show unapproved only"**, so finding the remaining 3 out of 41 at the end requires visual scanning.
- [P3] **Bulk button sits in the render footer** next to the format picker and `儲存並產生字幕` primary button. This visually groups approval with rendering, but they are distinct concerns. A user might think "bulk approve" is part of the render action.
- [P3] **`(0)` counter suffix** on the bulk button is unexplained. It probably means "0 untouched segments available to approve" — but a user seeing `(0)` may interpret it as "0 approved so far". Disable with explicit reason instead.
- [P3] **No "un-approve all" recovery path.** A user who accidentally approved everything has no easy reset.

**Recommendations:**
1. **Rename the bulk button** to something unambiguous:
   - `✓ 核准未編輯段落 (N)` (what it currently does)
   - Add a sibling action `✓ 核准全部 (N)` with a confirm dialog, for the "I've reviewed everything, just commit" case.
   - Both buttons should show the count of segments they would affect; both should be disabled with a descriptive tooltip when count is 0.
2. **Enlarge the per-segment button** from ~20 px circle to ~28 px pill. Use a capsule shape `[ ✓ ]` with generous padding.
3. **Add a dedicated `A` shortcut** that toggles approval on the currently-focused segment. Add to the keyboard hint strip with label `A 核准 / 取消`. Move `Enter` to "commit text edit" to avoid the dual-purpose conflict.
4. **Add "undo last bulk approval"**: after a bulk action, show a transient `↺ 撤銷` link for 10 seconds at the top of the table that reverts the batch. Implement as a backend snapshot or frontend state stack.
5. **Animate the header count** on change: brief purple glow + scale-bounce on `已核准 X/41` when the number updates.
6. **Add a filter toggle** next to the counter: `[全部] [未核准] [已編輯未核准]`. Clicking filters the table to just that subset.
7. **Relocate the bulk approval button** to the approval summary bar at the top of the table, separating it from the render footer. Keep only `儲存並產生字幕` + format picker in the footer.
8. **Replace disabled `(0)` state with explicit reason**: when no segments match, render the button as `所有段落已改動` with a tooltip explaining why.
9. **Add "重置所有核准"** in an overflow menu on the approval summary for recovery. Needs a confirm dialog and should be visually de-emphasized.

**Estimated impact:** high — approval is the final gate before render, so even small friction compounds
**Estimated effort:** S-M — label fix is trivial; bulk variants + keyboard shortcut + filter are incremental improvements

---

### Area 18: Proofread editor — keyboard shortcuts discoverability

**Screenshot:** `screenshots/18_proofread-shortcuts.png`

**What works:**
- Keys are rendered as small "keycap" pills (`Space`, `↑`, `↓`, `E`, `Enter`, `Esc`), visually distinct from the label text — immediately recognizable as press-these
- Horizontal single-row layout is compact and stays out of the way
- All labels are in Traditional Chinese with clear action verbs (`播放/暫停`, `導覽片段`, `編輯翻譯`, `確認核准`, `取消`)
- Grouping `↑` / `↓` under one combined label is space-efficient
- The 5 shortcuts in the hint strip match the 5 shortcuts in the JavaScript handler exactly — no phantom or missing entries
- Positioned directly below the video player where the user's eye already falls

**Issues observed:**
- [P1] **Hint strip is the bottom-most element of the video column**, so on smaller viewports or when the video occupies full height, it drops below the fold. Users who never scroll to the bottom of the left column will miss it entirely.
- [P1] **No persistent "help" button / overlay.** A user who wants to scan all available shortcuts in one place has no affordance. The strip is the only reference.
- [P1] **`Enter` has dual semantics hidden from the user.** In row-focus mode it toggles approval; inside an active text edit it commits the edit. The hint strip shows only `確認核准`. A user mid-edit may press Enter expecting a newline and get a save instead.
- [P2] **No visual feedback when a shortcut fires.** Pressing `Space` should briefly flash the `Space` keycap; today nothing happens visually.
- [P2] **No shortcuts for saving, rendering, or navigation-by-state.** Broadcast workflow demands: `⌘S` to save, `N` to jump to next unapproved, `R` to open render. None exist.
- [P2] **No `?` help shortcut.** Standard editor convention of "press `?` for help" is missing.
- [P2] **Cross-page inconsistency**: the dashboard (index.html) has its own keyboard hint strip mentioning `← → 往前/往後 5 秒`, but those shortcuts are not in the proofread editor. Mental model leaks between pages.
- [P3] **Low contrast on the keycap pills** — they blend into the dark background and the eye has to work to read them.
- [P3] **No section header** like `⌨ 快速鍵`. Users scanning past the hint row may not recognize it as "this is the keyboard reference".
- [P3] **No accessibility announcement** when a shortcut fires (`aria-live` region) for screen-reader users.

**Recommendations:**
1. **Add a persistent help button** `❓` in the top-right of the proofread editor header. Bind `?` to open a modal listing every keyboard shortcut with Chinese descriptions. Group by category: Navigation / Editing / Approval / Playback / Actions.
2. **Convert the hint strip into a collapsible dock**: a tiny `⌨ 快速鍵` pill in the corner that expands to the full strip on hover/click. Save the user's preferred state in `localStorage`.
3. **Clarify `Enter` dual semantics** in the hint strip with context-aware labels:
   - Default: `Enter 核准` (list-focus mode)
   - While editing: `Enter 儲存 · Shift+Enter 換行`
   Use live JS to swap labels based on `state.editing`.
4. **Visual feedback on keypress**: flash the matching keycap (`transition: background 200ms; background: var(--accent)`) whenever its shortcut fires. Psychologically reinforcing.
5. **Add missing power-user shortcuts** consistent with recommendations elsewhere:
   - `A` — toggle approval (frees `Enter` from dual meaning)
   - `N` — next unapproved
   - `P` — previous unapproved
   - `⌘/Ctrl+K` — focus search
   - `⌘/Ctrl+F` — find/replace
   - `⌘/Ctrl+S` — save without rendering
   - `R` — open render dialog
   - `?` — open shortcut help modal
   Update both the hint strip and the handler together.
6. **Increase keycap contrast**: `background: var(--surface2); border: 1px solid var(--border); color: var(--text-bright);`. Make them visually "pop" against the dark background.
7. **Add a subtle header** `⌨ 快速鍵` (small caps, dim colour) above the strip so the row is self-identifying.
8. **ARIA announcement region**: `<div aria-live="polite" class="sr-only" id="sr-announce"></div>` that receives messages like "已核准段落 18" when shortcuts fire. Screen readers benefit without affecting visual users.
9. **Page consistency**: either add `←` / `→` 5-second-skip to proofread, or remove them from the dashboard hint strip. Pick one mental model.

**Estimated impact:** medium-high — shortcuts multiply productivity but only if discoverable; the current strip is a good start that misses the 3-4 most-wanted power-user actions
**Estimated effort:** S-M — help modal + new shortcuts + contrast fix are independent small wins

---

### Area 19: Error states (upload / API / translation failures)

**Screenshot:** `screenshots/19_error-states.png`
*Captured with a simulated `轉錄失敗` file card injected and an error toast fired via `showToast`.*

**What works:**
- Consistent red colour vocabulary across the error card (border, ⚠ icon, badge, message text) — the danger signal is unambiguous
- Badge `轉錄失敗` is human-readable, not a raw HTTP status code
- Inline error detail (`FFmpeg error: Unsupported codec 'av1'`) is specific to the actual failure, not generic "something went wrong"
- `🔄 重試` button gives an immediate recovery path directly on the failing card
- Error toast appears at the bottom-right without obscuring other UI
- Success and error toasts can coexist without collision (stacked with per-class coloured borders)
- Global `showToast(msg, 'error')` is wired for error surfacing

**Issues observed:**
- [P1] **Error toasts are transient and auto-dismiss.** A user who glances away for 5 seconds misses the notification entirely. Upload failures are high-severity and should not silently disappear.
- [P1] **No error aggregation.** If five uploads fail in quick succession, five toasts stack briefly and then vanish — there is no "recent errors" panel to revisit them.
- [P1] **Error details are raw backend output.** `FFmpeg error: Unsupported codec 'av1'` is actionable to a developer but opaque to a producer. No human translation, no suggested fix, no help link.
- [P2] **Retry button is non-contextual.** For a codec error, clicking retry without changing the input is pointless, yet the button is enabled and gives no hint.
- [P2] **Toast text cannot be copied** while it is visible (transient), and cannot be referenced once it vanishes. Support escalation is hostile — "what exactly did the error say?" goes unanswered.
- [P2] **No global error indicator** in the header. Once the toast is gone and the user has scrolled past the failing card, there is no way to tell "I have N unresolved errors" without manually hunting.
- [P2] **Delete button on error cards** removes both the file and the error context. A safer pattern would be "✓ 標記已處理" which keeps the file but clears the error badge.
- [P2] **No error code / ID**. For support tickets users cannot reference "error #E4892" — they must retype the full message into a bug report.
- [P3] **WCAG contrast on red-on-dark** is unverified. The red-border + red-text combination needs to be measured against AA (4.5:1 minimum for normal text).
- [P3] **Error details are single-line**. Multi-line stack traces or JSON bodies are truncated with no "show more" affordance.
- [P3] **No global JavaScript error boundary**. A runtime exception in frontend code (e.g. undefined function) may leave the app half-broken with only console evidence.

**Recommendations:**
1. **Stratify toast severity**: `info` and `success` use transient auto-dismissing toasts (3 s). `warning` persists 10 s. `error` becomes a persistent banner at the top of the viewport with an explicit `✕ 關閉` button. Never auto-dismiss a critical error.
2. **Build an error aggregation centre**: a `🔔` bell icon in the header with a counter. Clicking opens a sidebar panel listing all recent errors with timestamp, code, detail, and per-error retry/dismiss actions. Persist to `localStorage` across reloads.
3. **Humanize backend errors** through a code → explanation map. Extend the backend error contract to `{ "error_code": "UNSUPPORTED_CODEC", "message": "...", "hint": "呢個格式未支援，請先轉檔成 H.264 或 H.265" }`. Frontend renders the localized hint under the raw message.
4. **Context-aware retry button**: map error codes to whether retry is useful. Disable the button for `UNSUPPORTED_CODEC`, `INVALID_CREDENTIALS`, etc. Label it `🔄 重試` (recoverable) or `⚙ 修正後重試` (needs action) or `ℹ 查看詳情` (non-recoverable).
5. **Copy-error button** on each error card and toast: `📋` icon that copies `<error_code> · <raw_message> · <timestamp>` to clipboard.
6. **Header error indicator** (`🔴 2 個錯誤`) as a red pill next to the connection status when unresolved errors exist. Click to open the aggregation panel.
7. **Separate "dismiss error" from "delete file"**: error cards should have `× 解除警告` (clears the error state but keeps the file) and `🗑 刪除` (destructive, with confirm).
8. **Verify red-on-dark contrast**: `#ff4d4f on #0a0a1a` should be measured; if below AA, shift to `#ff7070` or adjust background.
9. **Expandable detail pane**: truncate multi-line errors to 2 lines with a `↓ 展開` affordance; full error in a collapsible below.
10. **Global JS error boundary**: `window.addEventListener('error', e => showToast(...))` + `unhandledrejection` handler. A friendly fallback modal for runtime failures with a "匯報" / "重新整理" action.

**Estimated impact:** medium-high — errors are recurring in a multi-stage pipeline; current handling loses information quickly and blocks support/debug
**Estimated effort:** M — error-code contract + humanization + aggregation panel are independent but each non-trivial

---
