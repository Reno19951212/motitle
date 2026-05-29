# V6 Frontend Audit — Mode-Aware Proofread + Dashboard Design Spec

**Date:** 2026-05-29
**Branch:** `dev` HEAD `f3804f3` (V6 graft + Sprint 1+2+3 cleanup + test isolation fix)
**Status:** DESIGN READY — awaiting implementation

---

## 1. Problem Motivation

Sprint 1 of the v3.19 V6 graft cleanup (commit `5269a08`) fixed the **backend** field-shape drift — V6 file translations now expose `zh_text` mirrored from `by_lang.zh.text`, and `/api/files` per-row carries `active_kind`. Sprint 1's explicit mandate excluded frontend changes.

Operator validation (file `d159d9dbd309` — 賽馬娛樂新聞 25-min, uploaded 2026-05-29 14:16) confirms the **backend half of v3.19 BLOCKER 1 works**:

- Full V6 DAG ran end-to-end (28 VAD → 1066 Qwen3 chars → 92 mlx → 83 merged → 83 refined zh segments)
- Entity names from Qwen3 context recognized: 「布浩穎同埋見習騎師袁幸堯啊」
- `GET /api/files/<id>/translations` returns 83 rows with `zh_text` populated + `by_lang.zh.text` aligned

But the user sees **nothing** on Proofread page and **no subtitle overlay** on Dashboard video preview. Diagnosis (Phase 1 systematic debugging) traced the symptom to three V6-blind frontend sites that read `entry["segments"]` as the primary source:

| Site | File:Line | Symptom |
|---|---|---|
| Proofread `loadSegments()` | `proofread.html:2008-2052` | `segs[] = []` → table empty + overlay empty + Find&Replace empty + approve buttons absent |
| Proofread `saveEnIfDirty()` | `proofread.html:2454` | PATCHes `/segments/<idx>` which V6 doesn't expose; would 404 on edit |
| Dashboard `loadFileSegments()` | `index.html:4150-4180` | Inspector body empty + video preview overlay empty + 「only when ASR is done」UX disabled |

Phase A 2026-05-28 validation surfaced part of this as BLOCKER 1; the fix description had two halves — backend (Sprint 1 shipped) and frontend (this spec).

This design closes the frontend half: make `loadSegments()` and its dashboard sibling dispatch on `active_kind`, reusing the existing `segs[]` shape with V6-specific field semantics.

---

## 2. Scope

**In scope:**
- Mode-aware `loadSegments()` in `proofread.html`
- Mode-aware `loadFileSegments()` in `index.html`
- Read-only EN column in V6 mode (Qwen3 source displayed but immutable)
- `saveEnIfDirty()` no-op for V6 mode
- Playwright coverage of the 4 happy-path scenarios
- Profile mode regression bar: existing flows unchanged byte-for-byte

**Out of scope:**
- Backend changes (Sprint 1+2+3 already shipped all required API surface)
- New UI components (no new modals / columns / tabs)
- Find&Replace / glossary scan / export / render — these read from `segs[]` or hit endpoints that already work for V6 after the above
- CSS / visual redesign — V6 column 2 just shows refined Cantonese same widget as Profile ZH
- 1-column V6 UI variant — explicitly rejected during brainstorming (2-column for QA parity preferred)

---

## 3. Architecture

```
                          ┌─────────────────────────────┐
                          │ /api/files (Sprint 1)        │
                          │   per-row includes           │
                          │   active_kind: "profile"     │
                          │                | "pipeline_v6"│
                          └──────────────┬──────────────┘
                                         │
                                         ▼
                          ┌──────────────────────────────┐
                          │ fileInfo cached on dashboard  │
                          │ AND on proofread (via         │
                          │ ?file=<id> URL → fetch)       │
                          └──────────────┬───────────────┘
                                         │
                  ┌──────────────────────┴────────────────────┐
                  ▼                                            ▼
       ┌────────────────────┐                       ┌─────────────────────┐
       │ Profile path       │                       │ V6 path             │
       │ (existing)         │                       │ (NEW)               │
       │                    │                       │                     │
       │ GET /segments      │                       │ GET /translations   │
       │ GET /translations  │                       │ (no /segments call) │
       │ join on i          │                       │ map directly        │
       │   → segs[]         │                       │   → segs[]          │
       │                    │                       │                     │
       │ segs[i].en =       │                       │ segs[i].en =        │
       │   segments[i].text │                       │   trans[i].         │
       │   (ASR English)    │                       │     source_text     │
       │                    │                       │   (Qwen3 Cantonese, │
       │ segs[i].zh =       │                       │   READ-ONLY)        │
       │   trans[i].zh_text │                       │                     │
       │   (MT Chinese)     │                       │ segs[i].zh =        │
       │                    │                       │   trans[i].zh_text  │
       │ EN column editable │                       │   (Stage 3 refined) │
       └────────────────────┘                       └─────────────────────┘
                  │                                            │
                  └──────────────┬─────────────────────────────┘
                                 ▼
                  ┌────────────────────────────────┐
                  │ Downstream code reads segs[]   │
                  │ — subtitle overlay             │
                  │ — Find&Replace                 │
                  │ — approve/unapprove            │
                  │ — flags / CPS / speaker        │
                  │ — render / export              │
                  │ — keyboard shortcuts           │
                  │ (transparent — zero changes)   │
                  └────────────────────────────────┘
```

**Single dispatch point per surface** — `loadSegments()` (proofread) and `loadFileSegments()` (dashboard). Downstream consumers of `segs[]` and the existing edit/approve PATCH endpoints already work for V6 after Sprint 1's backend mirror.

---

## 4. Data Mapping

`segs[i]` schema is shared between modes. Field semantics shift per `active_kind`:

| `segs[i]` field | Profile mode source | V6 mode source |
|---|---|---|
| `idx` | `segments[i].idx` (or `i`) | `translations[i].idx` |
| `id` | `i + 1` | `i + 1` |
| `in` / `out` | `segments[i].start/end * 1000` | `translations[i].start/end * 1000` |
| `tsIn` / `tsOut` / `duration` | derived from in/out | derived from in/out |
| `en` | `segments[i].text` (ASR English, editable) | `translations[i].source_text` (Qwen3 raw, **read-only**) |
| `zh` | `translations[i].zh_text` (MT Chinese, editable) | `translations[i].zh_text` (Stage 3 refined, editable) |
| `cps` | `zh.length / duration` (cap 12) | same |
| `approved` | `translations[i].status === 'approved'` | same (Sprint 1 mirrored) |
| `edited` | `translations[i].edited === true` | same |
| `flags` | `translations[i].flags + parseTranslationFlags(zh)` | same |
| `speaker` | `translations[i].speaker \|\| null` | `null` (V6 doesn't expose) |
| `candidates` / `glossary` / `asr` / `mt` | `[]` / `[]` / `null` / `null` | same |

**Semantic invariant**: schema is mode-agnostic; only the data SOURCE differs. Downstream code that reads `segs[]` cannot tell the difference.

---

## 5. File-by-File Changes

### 5.1 `frontend/proofread.html`

#### Change A — `loadSegments()` dispatch (line 2008-2052, ~25 LOC delta)

Current behavior fetches BOTH `/segments` and `/translations`, builds `segs[]` by iterating `segments` as primary. Replace with:

```javascript
async function loadSegments() {
  const isV6 = fileInfo && fileInfo.active_kind === 'pipeline_v6';

  if (isV6) {
    // V6 path: translations is the canonical source (no /segments to fetch)
    const tResp = await fetch(`${API_BASE}/api/files/${fileId}/translations`).then(r => r.json());
    const translations = tResp.translations || [];
    segs = translations.map((t, i) => {
      const rawZh = t.zh_text || (t.by_lang?.zh?.text) || '';
      const { clean, flags: prefixFlags } = parseTranslationFlags(rawZh);
      const zh = clean;
      const apiFlags = Array.isArray(t.flags) ? t.flags : [];
      const inMs = Math.round((t.start ?? 0) * 1000);
      const outMs = Math.round((t.end ?? 0) * 1000);
      const durSec = (outMs - inMs) / 1000;
      const cps = durSec > 0 ? Math.round((zh.length / durSec) * 10) / 10 : 0;
      const flags = qaFlagsFromBackend(apiFlags, prefixFlags);
      if (cps > 12) flags.push({ type: 'cps', msg: `CPS ${cps}（上限 12）` });
      return {
        idx: t.idx ?? i,
        id: i + 1,
        in: inMs, out: outMs,
        tsIn: fmtMs(inMs), tsOut: fmtMs(outMs),
        duration: durSec.toFixed(1),
        en: t.source_text || '',   // Qwen3 raw Cantonese, read-only
        zh,
        cps,
        approved: t.status === 'approved' || t.approved === true,
        edited: t.edited === true,
        flags,
        speaker: null,             // V6 doesn't expose
        candidates: [],
        glossary: [],
        asr: null,
        mt: null,
      };
    });
  } else {
    // Profile path: existing implementation, unchanged
    const sResp = await fetch(`${API_BASE}/api/files/${fileId}/segments`).then(r => r.json());
    const rawSegs = sResp.segments || [];
    let translations = [];
    try {
      const tResp = await fetch(`${API_BASE}/api/files/${fileId}/translations`).then(r => r.json());
      translations = tResp.translations || [];
    } catch (e) {}
    segs = rawSegs.map((s, i) => {
      // ... existing Profile mapping body — copy verbatim ...
    });
  }

  // Overall duration fallback from last segment (shared)
  if (segs.length) {
    totalMs = Math.max(totalMs, segs[segs.length - 1].out + 2000);
  }
}
```

#### Change B — `saveEnIfDirty()` no-op for V6 (line 2454, +3 LOC)

```javascript
async function saveEnIfDirty() {
  const ta = document.getElementById('enInput');
  if (!ta || !enDirty) return true;
  // V6: EN is Qwen3 source (read-only); skip PATCH
  if (fileInfo && fileInfo.active_kind === 'pipeline_v6') {
    enDirty = false;
    ta.classList.remove('dirty');
    return true;
  }
  // ... existing Profile flow unchanged ...
}
```

#### Change C — `enInput` textarea read-only attribute (line 2224, +1 LOC)

```javascript
// inside the segment-row render template — adapt the textarea string:
<textarea id="enInput" rows="2"
  ${fileInfo && fileInfo.active_kind === 'pipeline_v6' ? 'readonly' : ''}
  title="${fileInfo && fileInfo.active_kind === 'pipeline_v6' ? 'Qwen3 ASR 原文（V6 mode read-only）' : ''}"
>${escapeHtml(s.en)}</textarea>
```

#### Change D — CSS hint for read-only EN (~5 LOC, appended to existing stylesheet)

```css
#enInput[readonly] {
  background: var(--surface-2);
  color: var(--text-mid);
  cursor: default;
}
#enInput[readonly]:focus {
  border-color: var(--border);
  box-shadow: none;
}
```

### 5.2 `frontend/index.html`

#### Change E — `loadFileSegments()` dispatch (line 4150-4180, ~30 LOC delta)

Current fetches `/segments` first, then joins translations. Replace with:

```javascript
async function loadFileSegments(id) {
  try {
    const fileInfo = uploadedFiles[id] || {};
    const isV6 = fileInfo.active_kind === 'pipeline_v6';
    const isDone = (fileInfo.status === 'done');

    if (isV6) {
      const tResp = await fetch(`${API_BASE}/api/files/${id}/translations`);
      if (!tResp.ok) return;
      const tData = await tResp.json();
      const trans = tData.translations || [];
      if (isDone && trans.length) {
        segments = trans.map((t, i) => ({
          start: t.start,
          end: t.end,
          text: t.source_text || '',          // dashboard-internal "ASR text" slot
          zh_text: t.zh_text || '',           // refined ZH for overlay
          _en_text: t.source_text || '',
          _approved: t.status === 'approved' || t.approved === true,
          _edited: t.edited === true,
        }));
        renderInspectorBody();
        const v = document.getElementById('videoPlayer');
        if (v) updateSubtitleOverlay(v.currentTime || 0);
        applySubtitleStyle();
      }
    } else {
      // existing Profile path — unchanged verbatim
      const resp = await fetch(`${API_BASE}/api/files/${id}/segments`);
      // ... existing body ...
    }
  } catch (e) {}
}
```

The overlay `updateSubtitleOverlay()` reads `segments[].zh_text` first, fallback to `text` — already V6-compatible after the mapping above.

---

## 6. Acceptance Gate

4 Playwright cases (new file: `frontend/tests/test_v6_frontend_audit.spec.js`):

| Test | Verifies |
|---|---|
| `proofread_v6_file_renders_segments_and_overlay` | Open `proofread.html?file=<v6-fid>` → 83 segment rows visible → SVG overlay shows `下個月有新騎師登場，就係澳洲好手` at t=4s |
| `proofread_v6_en_textarea_is_readonly` | Inspect `#enInput` → `readOnly === true`; type attempt does not modify value; tooltip text matches |
| `proofread_v6_zh_edit_patches_translations` | Modify ZH textarea → blur → PATCH request goes to `/translations/<idx>` (not `/segments/<idx>`); response 200 |
| `dashboard_v6_file_inspector_and_overlay_populated` | Open dashboard with V6 file selected → inspector body has rows → seek video to 4s → SVG overlay shows refined ZH |

**Pass = all 4 PASS + existing Phase A spec (`test_v3_19_happy_path.spec.js`) still 24/24** (Profile mode regression bar).

---

## 7. Risks + Mitigations

| Risk | Mitigation |
|---|---|
| `fileInfo` undefined when proofread loads before file fetch resolves | Race already handled by existing code waiting for fileInfo before calling `loadSegments`. Verify in test 1. |
| `t.idx` ordering vs natural order on Sprint 1 mirrored data | `trans[].idx` is set by `_persist_by_lang` (sequential `range(n)`). Safe to use directly. |
| Search index breaks for V6 EN column (Find&Replace EN finds Qwen3 raw, surprising users) | Documented behavior. `_en_text` semantics shift per mode is OK because both modes have "source-language text" in EN slot. |
| Keyboard shortcut `Cmd+Enter` on V6 EN textarea | `saveEnIfDirty()` early-returns for V6 → no-op → falls through to approve flow. Tested. |
| User uploads V6 file via old browser cache where `fileInfo.active_kind` is stale `undefined` | Falls into Profile path, segments empty, same UX as today's bug. Cache invalidation pre-existing concern. Not blocking. |
| Future "V5 dual-ASR" pipeline_type | `isV6 = active_kind === 'pipeline_v6'` exact match; future modes follow same dispatch pattern. |

---

## 8. Implementation Plan Summary

| Phase | Action | Files | LOC | Tests |
|---|---|---|---|---|
| 1 | Proofread loadSegments dispatch | `proofread.html:2008-2052` | ~25 | 1 |
| 2 | Proofread EN read-only | `proofread.html:2224, 2454` + CSS | ~10 | 1 |
| 3 | Dashboard loadFileSegments dispatch | `index.html:4150-4180` | ~30 | 1 |
| 4 | Playwright spec | `frontend/tests/test_v6_frontend_audit.spec.js` | ~150 | 4 |
| 5 | Manual smoke on file `d159d9dbd309` | — | — | — |
| 6 | Update CLAUDE.md v3.19 entry | `CLAUDE.md` | ~30 | — |
| | Total | 2 source files + 1 test file + docs | ~215 | 4 cases |

Estimated wall time: 2-3 hours for one Sonnet subagent under subagent-driven-development.

---

## 9. Out-of-Scope Items (deferred / known boundaries)

- **V6 stage rerun UI**: `POST /api/files/<fid>/stages/<idx>/rerun` endpoint exists (Sprint 2 B-1 fix) but no frontend button. Future Sprint 4 candidate.
- **V6 segment delete**: No DELETE on V6 translations. V6 backend doesn't support it. Acceptable.
- **V6 per-segment Qwen3-context override**: Per-segment context tuning. Future power-user feature, not part of this spec.
- **V6 source_text edit**: Editing Qwen3 raw would require re-running stages 2 + 3 which is expensive. Read-only is the right call.
- **V6 visualization of stage_outputs in UI**: Stage outputs already persisted; an "inspector" tab showing 「Stage 0 VAD region count」 / 「Stage 1A entity hits」 would be useful but out of immediate scope.

---

## 10. References

- Backend Sprint 1 commit: `5269a08` — mirror `by_lang.<lang>.*` to top-level legacy fields
- Backend `/api/files` `active_kind` exposure: commit `8fabf9c`
- Phase A original BLOCKER 1 finding: [`v3.19-phase-a-happy-path.md`](v3.19-phase-a-happy-path.md) §Findings
- Comprehensive validation report: [`v3.19-comprehensive-validation-report.md`](v3.19-comprehensive-validation-report.md)
- Reproducer file (verified V6 backend output): registry entry `d159d9dbd309` — 賽馬娛樂新聞 25-min Cantonese
