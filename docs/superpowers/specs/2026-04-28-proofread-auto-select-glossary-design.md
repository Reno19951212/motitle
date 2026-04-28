# Proofread — Auto-Select Pipeline Glossary on Load

**Date:** 2026-04-28
**Status:** Approved

---

## Problem

When a user opens the Proofread page, the glossary dropdown is empty. To use the "套用" (apply glossary) feature, the user must manually pick the same glossary that the active Profile already has configured under `translation.glossary_id`. This is a redundant step — the Pipeline already knows which glossary applies.

---

## Goal

On Proofread page load, pre-select the glossary configured in the active Profile so the user can act on it immediately (套用 / edit / 刪除) without an extra dropdown click.

---

## Non-Goals

- No dynamic re-sync when the active Profile changes mid-session — load-time only (sync mode A from brainstorming).
- No backend changes — `profile.translation.glossary_id` already exists.
- No UI indicator showing "from Pipeline" — keep it transparent.

---

## Design

### Data Flow

```
proofread.html load
  → initGlossaryPanel()
    1. GET /api/glossaries → populate <select id="glossarySelect"> options
    2. GET /api/profiles/active → read profile.translation.glossary_id
    3. If glossary_id is truthy AND matches an option in the dropdown:
         set dropdown.value = glossary_id
         await onGlossarySelect()   // loads entries + enables buttons
       Else: leave dropdown at default empty state (existing behaviour)
```

### Implementation

Single function change in `frontend/proofread.html` — `initGlossaryPanel()`:

```js
async function initGlossaryPanel() {
  try {
    const r = await fetch(`${API_BASE}/api/glossaries`);
    if (!r.ok) return;
    const data = await r.json();
    const sel = document.getElementById('glossarySelect');
    (data.glossaries || []).forEach(g => {
      const opt = document.createElement('option');
      opt.value = g.id;
      opt.textContent = g.name;
      sel.appendChild(opt);
    });

    // Auto-select the glossary configured in the active Profile.
    // Sync mode A: load-time only — no listener for later profile_updated events.
    try {
      const pr = await fetch(`${API_BASE}/api/profiles/active`);
      if (!pr.ok) return;
      const pd = await pr.json();
      const pipelineGlossaryId = pd.profile?.translation?.glossary_id;
      if (pipelineGlossaryId &&
          Array.from(sel.options).some(o => o.value === pipelineGlossaryId)) {
        sel.value = pipelineGlossaryId;
        await onGlossarySelect();
      }
    } catch (e) { /* keep dropdown at default */ }
  } catch (e) { /* silent — panel stays in placeholder state */ }
}
```

### Edge Cases

| Scenario | Behaviour |
|---|---|
| Profile has no `glossary_id` | Dropdown stays at default empty option (no change from current) |
| `glossary_id` references a deleted glossary | `Array.some()` check fails → dropdown stays empty |
| `/api/profiles/active` fails or returns no profile | inner catch → dropdown stays empty |
| `/api/glossaries` fails | outer catch → dropdown empty (existing behaviour) |
| User deletes the auto-selected glossary via 🗑 | Already handled by `deleteCurrentGlossary()` — clears state and rebuilds dropdown |
| User manually changes dropdown after auto-select | `onGlossarySelect()` runs again normally — no special handling needed |

### Race Conditions

The two API calls run sequentially, not in parallel. We must populate the dropdown options first; otherwise setting `.value = pipelineGlossaryId` would silently fail because the option doesn't exist yet. Sequential ordering is intentional and the small extra latency (one round-trip) is acceptable for a page-load operation.

---

## Testing

- **Manual:** open Proofread with active Profile that has `translation.glossary_id: "broadcast-news"` → dropdown auto-shows "Broadcast News", entries panel populated, 套用 / 🗑 buttons enabled
- **Manual:** active Profile with no `glossary_id` → dropdown empty, panel shows placeholder
- **Manual:** active Profile with stale `glossary_id` (e.g., user deleted that glossary in Dashboard) → dropdown empty, no error
- **Playwright smoke:** mock both endpoints, verify `sel.value` equals expected id and `glossaryEntries` is populated

---

## Out of Scope (future work)

- Listening for `profile_updated` socket events to re-sync glossary selection mid-session (sync mode B/C from brainstorming).
- Visual indicator (badge / tooltip) on the dropdown showing the source is the active Profile.
- Persisting user's manual override across page reloads.
