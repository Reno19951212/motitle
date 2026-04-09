# Frontend UI Integration Design

## Purpose

Connect the backend Language Config, Glossary, and Translation APIs to the frontend dashboard. Add collapsible settings panels and a re-translate button on file cards.

## Scope

All changes in `frontend/index.html`. No new files. No backend changes.

## Changes

### 1. Language Config Panel (collapsible, right sidebar)

Position: after Profile selector, before Transcript panel. Default: collapsed.

**HTML:** A collapsible section with:
- Header row: "🌐 語言配置" + expand/collapse toggle arrow
- Language selector dropdown (populated from `GET /api/languages`)
- Four input fields:
  - 每句最大字數 (`max_words_per_segment`, type number)
  - 每句最大時長 (`max_segment_duration`, type number, step 0.5)
  - Batch Size (`batch_size`, type number)
  - Temperature (`temperature`, type number, step 0.05)
- Save button

**JS:**
- `loadLanguages()` — fetch `GET /api/languages`, populate dropdown
- `loadLanguageConfig(langId)` — fetch `GET /api/languages/:id`, fill input values
- `saveLanguageConfig()` — collect input values, `PATCH /api/languages/:id`, show toast
- Toggle expand/collapse via click on header

**Expand/collapse CSS:** `.collapsible-body { max-height: 0; overflow: hidden; transition: max-height 0.3s; }` `.collapsible-body.open { max-height: 500px; }`

### 2. Glossary Panel (collapsible, right sidebar)

Position: after Language Config panel, before Transcript panel. Default: collapsed.

**HTML:** A collapsible section with:
- Header row: "📖 術語表" + expand/collapse toggle arrow
- Glossary selector dropdown (populated from `GET /api/glossaries`)
- Entry table: EN | 中文 | delete button per row
- Add entry row: two inputs + "新增" button
- CSV import button (file input, reads text, `POST /api/glossaries/:id/import`)

**JS:**
- `loadGlossaries()` — fetch `GET /api/glossaries`, populate dropdown
- `loadGlossaryEntries(id)` — fetch `GET /api/glossaries/:id`, render table
- `addGlossaryEntry()` — collect EN/ZH inputs, `POST /api/glossaries/:id/entries`
- `deleteGlossaryEntry(entryId)` — `DELETE /api/glossaries/:id/entries/:eid`
- `importGlossaryCSV()` — read file, `POST /api/glossaries/:id/import`
- Toggle expand/collapse via click on header

### 3. File Card: Translation Status + Re-translate Button

**Changes to file card rendering (`renderFileList`):**

When `isDone` (transcription complete):
- Show translation status badge:
  - `translation_status === 'done'` → green badge "翻譯完成"
  - `translation_status === null` → yellow badge "翻譯中..." (auto-translate running)
  - No translation → grey badge "待翻譯"
- Show "🔄 重新翻譯" button (visible when `translation_status === 'done'`)
  - Click → `POST /api/translate` with file_id
  - During translation: button disabled, shows "翻譯中..."
  - On completion: refresh file list, reload translations

**Changes to `file_updated` socket handler:**
- When `translation_status` changes, update badge and button state
- When translation completes, auto-reload translations for active file

### 4. Collapsible Panel CSS

Shared CSS for both panels:
```css
.collapsible-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding: 8px 0;
  user-select: none;
}
.collapsible-header .arrow {
  transition: transform 0.3s;
}
.collapsible-header.open .arrow {
  transform: rotate(90deg);
}
.collapsible-body {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease;
}
.collapsible-body.open {
  max-height: 600px;
}
```

### 5. Initialization

On page load, add to init sequence:
```javascript
loadLanguages();
loadGlossaries();
```

## API Calls Summary

| Function | Method | Endpoint |
|---|---|---|
| loadLanguages | GET | /api/languages |
| loadLanguageConfig | GET | /api/languages/:id |
| saveLanguageConfig | PATCH | /api/languages/:id |
| loadGlossaries | GET | /api/glossaries |
| loadGlossaryEntries | GET | /api/glossaries/:id |
| addGlossaryEntry | POST | /api/glossaries/:id/entries |
| deleteGlossaryEntry | DELETE | /api/glossaries/:id/entries/:eid |
| importGlossaryCSV | POST | /api/glossaries/:id/import |
| reTranslateFile | POST | /api/translate |

All endpoints already exist in backend. No backend changes needed.

## Testing

Manual testing only (no automated frontend tests):
- Expand/collapse Language Config panel
- Select language, verify values load
- Change a value, save, verify toast + persistence
- Expand Glossary panel, select glossary, verify entries display
- Add entry, verify it appears
- Delete entry, verify it disappears
- Import CSV, verify entries added
- Upload file → verify auto-translate runs → status badge updates
- Click "重新翻譯" → verify translation re-runs

## What Does NOT Change

- Backend API (all endpoints already exist)
- proofread.html
- Profile selector (already works)
- Transcript display
- Video player
