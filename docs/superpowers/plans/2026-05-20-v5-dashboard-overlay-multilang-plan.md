# v5 Dashboard Overlay Multi-Lang Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dashboard live subtitle overlay + Inspector transcript preview switch from reading raw `asr_primary` segments (`/api/files/<id>/segments`) to reading the verifier-corrected + refined per-lang text from v5 `by_lang` (`/api/files/<id>/translations?shape=v5`), with a lang picker so the user can choose which lang to display.

**Architecture:** Factor the existing Proofread `TargetLangTabs` into a shared `LangPicker` under `frontend/src/components/`. Add a `useDashboardTranslations(fileId)` hook that fetches v5 translations in parallel with `/api/files/<id>/segments`, derives a per-lang `SegmentPreview[]` for the active lang (with verifier/refiner output as `text`), and falls back to the raw segments endpoint when v5 translations are empty (v4 pipelines, ASR-only files, or files that haven't been re-run on v5). Dashboard.tsx swaps its local `segments` state + fetch effect for the hook, adds an `activeLang` state, and renders `<LangPicker>` in the workbench above the video. Both `<VideoSubtitleOverlay>` and `<InspectorTranscriptPreview>` keep their existing `SegmentPreview[]` interface unchanged — the hook performs the boundary adaptation so consumers stay decoupled from the v5 shape.

**Tech Stack:** React 18 + TypeScript strict (`noUncheckedIndexedAccess: true`); Vitest 2.1 unit tests; existing `apiFetch` + `lib/api/v5.ts` API client; existing motitle-bold CSS classes (no new styling work).

**Parent context:** v5-A3 ([docs/superpowers/plans/2026-05-20-v5-A3-frontend-multilang-plan.md](2026-05-20-v5-A3-frontend-multilang-plan.md)) shipped the Proofread page's multi-lang consumption pattern (T9: `useFileData` hook + `TargetLangTabs`). This plan ports that pattern to the Dashboard's video preview overlay. Closes the "Dashboard overlay doesn't reflect v5 improvements" known gap identified in the v5-A3 final review.

**Branch:** continue on `feat/frontend-redesign` (v5-A3 already landed there — 16 commits).

---

## File Structure

### New files (created by this plan)

| Path | Responsibility |
|---|---|
| `frontend/src/components/LangPicker.tsx` | Shared lang-tab strip (renamed + relocated from `Proofread/TargetLangTabs.tsx`) |
| `frontend/src/hooks/useDashboardTranslations.ts` | Fetches v5 translations + falls back to `/segments`, derives `SegmentPreview[]` for active lang, exposes `availableLangs` + `sourceLang` |
| `frontend/src/hooks/useDashboardTranslations.test.ts` | Vitest unit tests for the hook (v5 path / fallback path / empty path / lang switch) |

### Modified files

| Path | Change |
|---|---|
| `frontend/src/pages/Proofread/TargetLangTabs.tsx` | Replace body with a 2-line re-export shim (`export { LangPicker as TargetLangTabs } from '@/components/LangPicker';`) — preserves existing Proofread imports so v5-A3 work isn't broken |
| `frontend/src/pages/Dashboard.tsx` | Replace local `segments` state + fetch effect (lines ~2049-2063) with `useDashboardTranslations`; add `activeLang` state; render `<LangPicker>` above the `<video>`; pass derived segments to `<VideoSubtitleOverlay>` + `<InspectorTranscriptPreview>` (interface unchanged) |
| `CLAUDE.md` | Add a "v5-A3 follow-up" sub-entry below the v5-A3 main entry documenting the dashboard overlay fix |

### Files NOT touched

- Backend (`pipeline_runner.py`, `routes/files.py`, `_bridge_stage_outputs_into_entry`) — translations endpoint already returns `by_lang` via `?shape=v5`, no schema change needed
- `frontend/src/pages/Proofread/hooks/useFileData.ts` — already uses the v5 pattern, not changed
- `frontend/src/lib/api/v5.ts` — `getTranslations(fileId)` already does what we need
- `<VideoSubtitleOverlay>` + `<InspectorTranscriptPreview>` component bodies — their `SegmentPreview[]` interface is preserved (boundary adaptation lives in the hook)

---

## Task index

| # | Task | Phase |
|---|---|---|
| T1 | Extract `LangPicker` to `components/` + shim `TargetLangTabs` | 1 — Refactor |
| T2 | Create `useDashboardTranslations` hook + tests | 2 — Hook |
| T3 | Wire Dashboard.tsx (replace fetch + add lang picker UI + activeLang state) | 3 — Integration |
| T4 | Final verification + CLAUDE.md entry | 4 — Wrap-up |

---

## Phase 1 — Refactor

### Task 1: Extract `LangPicker` to shared location

**Files:**
- Create: `frontend/src/components/LangPicker.tsx`
- Modify: `frontend/src/pages/Proofread/TargetLangTabs.tsx` (replace body with re-export shim)

The existing `TargetLangTabs` component (25 lines, lives under `Proofread/`) is generic — it accepts an array of lang strings and an active one. We need the identical UI on the Dashboard. Move it to `components/` and rename to `LangPicker`. Keep `TargetLangTabs` as a 2-line re-export shim so existing Proofread imports (`./TargetLangTabs`) don't break.

- [ ] **Step 1: Create `frontend/src/components/LangPicker.tsx`**

```typescript
// src/components/LangPicker.tsx
// Shared lang-tab strip — switches between by_lang keys. Used by both the
// Proofread page (TargetLangTabs re-export) and the Dashboard live overlay.
interface Props {
  availableLangs: string[];
  activeLang: string;
  onSelect: (lang: string) => void;
}

export function LangPicker({ availableLangs, activeLang, onSelect }: Props) {
  if (availableLangs.length === 0) return null;
  return (
    <div className="lang-tabs" style={{ display: 'flex', gap: 4, padding: '4px 8px' }}>
      {availableLangs.map((l) => (
        <button
          key={l}
          type="button"
          className={`lang-tab action-chip ${l === activeLang ? 'primary' : ''}`}
          onClick={() => onSelect(l)}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Replace `frontend/src/pages/Proofread/TargetLangTabs.tsx` body with re-export shim**

```typescript
// src/pages/Proofread/TargetLangTabs.tsx
// Re-export shim — actual component moved to shared @/components/LangPicker
// during the v5 dashboard-overlay multilang fix.
export { LangPicker as TargetLangTabs } from '@/components/LangPicker';
```

- [ ] **Step 3: Run existing Proofread tests to verify the shim works**

Run: `cd frontend && npm run test -- src/pages/Proofread/ 2>&1 | tail -10`
Expected: PASS for all 36+ Proofread tests. The shim should compile + the `import { TargetLangTabs } from './TargetLangTabs'` in `Proofread/index.tsx` should resolve transparently.

- [ ] **Step 4: TypeScript check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -10`
Expected: clean (zero errors).

- [ ] **Step 5: Commit T1**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/src/components/LangPicker.tsx frontend/src/pages/Proofread/TargetLangTabs.tsx
git commit -m "refactor(v5): extract LangPicker to components/ for shared use

Move the 25-line TargetLangTabs body from Proofread/ to a shared
components/LangPicker.tsx so the Dashboard live overlay can reuse it
without duplication. Preserves the Proofread import path via a 2-line
re-export shim — zero behavior change on Proofread."
```

---

## Phase 2 — Hook

### Task 2: Create `useDashboardTranslations` hook + tests

**Files:**
- Create: `frontend/src/hooks/useDashboardTranslations.ts`
- Create: `frontend/src/hooks/useDashboardTranslations.test.ts`

This hook is the boundary adapter. It performs two parallel fetches, then derives a `SegmentPreview[]` for the active lang. Critical contracts:

1. **v5 file with by_lang data (e.g., zh source + zh refined + en translated):**
   - `availableLangs` = sorted union of all `by_lang` keys across rows
   - `sourceLang` = `translations[0].source_lang`
   - For each row, `segments[i].text` = `by_lang[activeLang]?.text || source_text`
   - `segments[i].start` / `.end` = from translation row's `start` / `end`

2. **v4 file (no v5 yet) or v5 file before pipeline run:** `?shape=v5` returns empty list. Fall back to the raw `/api/files/<id>/segments` endpoint — same data dashboard reads today. `availableLangs = []`, `sourceLang = null`.

3. **ASR-only file (segments exist but no MT):** Same as case 2 — translations empty, use raw segments.

4. **No file selected (`fileId === null`):** Return empty everything; do not fetch.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/hooks/useDashboardTranslations.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useDashboardTranslations } from './useDashboardTranslations';

describe('useDashboardTranslations', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockTranslationsResponse(translations: unknown[]) {
    return {
      ok: true,
      status: 200,
      json: async () => ({ translations, file_id: 'f1' }),
    };
  }

  function mockSegmentsResponse(segments: unknown[]) {
    return {
      ok: true,
      status: 200,
      json: async () => ({ id: 'f1', status: 'done', segments, text: '' }),
    };
  }

  it('returns empty state when fileId is null', () => {
    const { result } = renderHook(() => useDashboardTranslations(null, 'zh'));
    expect(result.current.segments).toEqual([]);
    expect(result.current.availableLangs).toEqual([]);
    expect(result.current.sourceLang).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('derives segments per active lang from v5 by_lang', async () => {
    fetchMock
      .mockResolvedValueOnce(
        mockTranslationsResponse([
          {
            idx: 0, start: 0, end: 1.5,
            source_lang: 'zh', source_text: '中文原文',
            by_lang: {
              zh: { text: '潤色中文', status: 'pending', flags: [] },
              en: { text: 'english', status: 'pending', flags: [] },
            },
          },
          {
            idx: 1, start: 1.5, end: 3,
            source_lang: 'zh', source_text: '第二句',
            by_lang: {
              zh: { text: '潤色第二', status: 'pending', flags: [] },
              en: { text: 'second', status: 'pending', flags: [] },
            },
          },
        ]),
      )
      .mockResolvedValueOnce(mockSegmentsResponse([]));

    const { result } = renderHook(() => useDashboardTranslations('f1', 'zh'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.segments).toEqual([
      { start: 0, end: 1.5, text: '潤色中文' },
      { start: 1.5, end: 3, text: '潤色第二' },
    ]);
    expect(result.current.availableLangs).toEqual(['en', 'zh']);
    expect(result.current.sourceLang).toBe('zh');
  });

  it('re-derives when activeLang changes', async () => {
    fetchMock
      .mockResolvedValueOnce(
        mockTranslationsResponse([
          {
            idx: 0, start: 0, end: 1,
            source_lang: 'zh', source_text: '原',
            by_lang: {
              zh: { text: '中', status: 'pending', flags: [] },
              en: { text: 'EN', status: 'pending', flags: [] },
            },
          },
        ]),
      )
      .mockResolvedValueOnce(mockSegmentsResponse([]));

    const { result, rerender } = renderHook(
      ({ lang }) => useDashboardTranslations('f1', lang),
      { initialProps: { lang: 'zh' } },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.segments[0]?.text).toBe('中');

    rerender({ lang: 'en' });
    expect(result.current.segments[0]?.text).toBe('EN');
  });

  it('falls back to source_text when activeLang has no by_lang entry', async () => {
    fetchMock
      .mockResolvedValueOnce(
        mockTranslationsResponse([
          {
            idx: 0, start: 0, end: 1,
            source_lang: 'zh', source_text: '中文原文',
            by_lang: {
              en: { text: 'english only', status: 'pending', flags: [] },
            },
          },
        ]),
      )
      .mockResolvedValueOnce(mockSegmentsResponse([]));

    const { result } = renderHook(() => useDashboardTranslations('f1', 'ja'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.segments[0]?.text).toBe('中文原文');
  });

  it('falls back to /segments endpoint when translations are empty (v4 ASR-only)', async () => {
    fetchMock
      .mockResolvedValueOnce(mockTranslationsResponse([]))
      .mockResolvedValueOnce(
        mockSegmentsResponse([
          { start: 0, end: 2, text: 'raw asr line' },
        ]),
      );

    const { result } = renderHook(() => useDashboardTranslations('f1', 'zh'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.segments).toEqual([
      { start: 0, end: 2, text: 'raw asr line' },
    ]);
    expect(result.current.availableLangs).toEqual([]);
    expect(result.current.sourceLang).toBeNull();
  });

  it('returns empty segments when both endpoints return empty (no transcription yet)', async () => {
    fetchMock
      .mockResolvedValueOnce(mockTranslationsResponse([]))
      .mockResolvedValueOnce(mockSegmentsResponse([]));

    const { result } = renderHook(() => useDashboardTranslations('f1', 'zh'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.segments).toEqual([]);
  });

  it('exposes loading=true during fetch and false after', async () => {
    let resolveTr: (v: unknown) => void = () => {};
    let resolveSeg: (v: unknown) => void = () => {};
    fetchMock
      .mockReturnValueOnce(new Promise((res) => { resolveTr = res; }))
      .mockReturnValueOnce(new Promise((res) => { resolveSeg = res; }));

    const { result } = renderHook(() => useDashboardTranslations('f1', 'zh'));
    expect(result.current.loading).toBe(true);

    await act(async () => {
      resolveTr(mockTranslationsResponse([]));
      resolveSeg(mockSegmentsResponse([]));
      // Let the microtask queue drain
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(result.current.loading).toBe(false);
  });

  it('refetches when fileId changes', async () => {
    fetchMock
      .mockResolvedValueOnce(mockTranslationsResponse([]))
      .mockResolvedValueOnce(mockSegmentsResponse([{ start: 0, end: 1, text: 'A' }]))
      .mockResolvedValueOnce(mockTranslationsResponse([]))
      .mockResolvedValueOnce(mockSegmentsResponse([{ start: 0, end: 1, text: 'B' }]));

    const { result, rerender } = renderHook(
      ({ id }) => useDashboardTranslations(id, 'zh'),
      { initialProps: { id: 'f1' as string | null } },
    );
    await waitFor(() => expect(result.current.segments[0]?.text).toBe('A'));

    rerender({ id: 'f2' });
    await waitFor(() => expect(result.current.segments[0]?.text).toBe('B'));
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test -- src/hooks/useDashboardTranslations.test.ts 2>&1 | tail -10`
Expected: FAIL with `Cannot find module './useDashboardTranslations'`.

- [ ] **Step 3: Implement the hook**

Create `frontend/src/hooks/useDashboardTranslations.ts`:

```typescript
// src/hooks/useDashboardTranslations.ts
// Boundary adapter that powers the Dashboard live overlay + inspector preview.
// Fetches v5 by_lang translations and falls back to the raw /segments endpoint
// when translations are empty (v4 files, ASR-only files, files not re-run).
import { useEffect, useMemo, useState } from 'react';
import { apiFetch } from '@/lib/api';
import * as v5 from '@/lib/api/v5';
import type { V5Translation } from '@/lib/api/v5';

export interface SegmentPreview {
  start: number;
  end: number;
  text: string;
}

interface SegmentsResponse {
  id: string;
  status: string;
  segments: SegmentPreview[];
  text: string;
}

interface HookResult {
  segments: SegmentPreview[];
  availableLangs: string[];
  sourceLang: string | null;
  loading: boolean;
}

const EMPTY_RESULT: HookResult = {
  segments: [],
  availableLangs: [],
  sourceLang: null,
  loading: false,
};

function deriveForLang(rows: V5Translation[], activeLang: string): SegmentPreview[] {
  return rows.map((r) => ({
    start: r.start,
    end: r.end,
    text: r.by_lang[activeLang]?.text || r.source_text,
  }));
}

export function useDashboardTranslations(
  fileId: string | null,
  activeLang: string,
): HookResult {
  const [v5rows, setV5rows] = useState<V5Translation[]>([]);
  const [rawSegments, setRawSegments] = useState<SegmentPreview[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!fileId) {
      setV5rows([]);
      setRawSegments([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all([
      v5.getTranslations(fileId).catch(() => [] as V5Translation[]),
      apiFetch<SegmentsResponse>(`/api/files/${fileId}/segments`).catch(
        () => ({ id: fileId, status: '', segments: [], text: '' } as SegmentsResponse),
      ),
    ]).then(([translations, segmentsResp]) => {
      if (cancelled) return;
      setV5rows(translations ?? []);
      setRawSegments(segmentsResp.segments ?? []);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [fileId]);

  const availableLangs = useMemo(() => {
    const set = new Set<string>();
    for (const r of v5rows) for (const k of Object.keys(r.by_lang)) set.add(k);
    return Array.from(set).sort();
  }, [v5rows]);

  const sourceLang = v5rows[0]?.source_lang ?? null;

  const segments = useMemo(() => {
    if (v5rows.length > 0) return deriveForLang(v5rows, activeLang);
    return rawSegments;
  }, [v5rows, rawSegments, activeLang]);

  if (!fileId) return EMPTY_RESULT;
  return { segments, availableLangs, sourceLang, loading };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test -- src/hooks/useDashboardTranslations.test.ts 2>&1 | tail -15`
Expected: PASS (8 tests).

- [ ] **Step 5: TypeScript strict check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep useDashboardTranslations | head -5`
Expected: zero errors. If any appear, fix them before committing — typically narrow array access with `?.` or annotate types explicitly.

- [ ] **Step 6: Commit T2**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/src/hooks/useDashboardTranslations.ts frontend/src/hooks/useDashboardTranslations.test.ts
git commit -m "feat(v5): useDashboardTranslations hook — boundary adapter for live overlay

Parallel-fetches v5 by_lang translations + raw /segments. Derives a
SegmentPreview[] per active lang with verifier/refiner output as text;
falls back to raw segments when translations are empty (v4 files,
ASR-only files, files not re-run on v5).

Exposes availableLangs + sourceLang for the dashboard lang picker.

8 vitest cases cover: null fileId, v5 derive, lang switch re-derive,
missing-lang source_text fallback, v4 fallback to /segments, both-empty,
loading state, fileId change refetch."
```

---

## Phase 3 — Integration

### Task 3: Wire Dashboard.tsx (replace fetch + add lang picker + activeLang state)

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

The current dashboard maintains its own `segments` state via direct fetch (lines ~2049-2063). We replace that with the hook + add lang picker rendering near the video. Two consumers downstream (`<VideoSubtitleOverlay>` + `<InspectorTranscriptPreview>`) accept `SegmentPreview[]` — that interface is preserved.

Three integration concerns:

1. **`SegmentPreview` interface collision**: Dashboard.tsx defines its own `SegmentPreview` at line 923 with the same shape as the hook's. After this task, the local definition stays — both definitions are structurally identical, so no consumer breaks. (Removing the local definition is a follow-up.)
2. **`activeLang` default**: Resolve to `sourceLang` when available, else first lang in `availableLangs`, else `'zh'` as a stable default. Reset on file change.
3. **`<LangPicker>` placement**: Render in the workbench above the `<video>`. Only show when `availableLangs.length >= 1` (single-lang case is fine to show, hides automatically on v4 files).

- [ ] **Step 1: Read the current Dashboard.tsx workbench code**

Run: `cd frontend && sed -n '2044,2080p' src/pages/Dashboard.tsx`
Note the structure:
- Local state: `const [currentTime, setCurrentTime] = useState(0);` (line 2047)
- Local state: `const [segments, setSegments] = useState<SegmentPreview[]>([]);` (line 2049)
- Effect that fetches `/api/files/<id>/segments` and writes to `segments` (lines 2050-2063)
- Both `<VideoSubtitleOverlay segments={segments} ... />` (line 1197) and `<InspectorTranscriptPreview segments={segments} ... />` (line 1838) read this state via prop drilling

- [ ] **Step 2: Add imports near the top of Dashboard.tsx**

Find the existing import block at the top of `frontend/src/pages/Dashboard.tsx`. Add two new lines after the existing `@/lib/api` and motitle-bold imports:

```typescript
import { useDashboardTranslations } from '@/hooks/useDashboardTranslations';
import { LangPicker } from '@/components/LangPicker';
```

- [ ] **Step 3: Replace the local segments state + fetch effect**

Find these lines (approximately 2049-2063):

```typescript
  const [segments, setSegments] = useState<SegmentPreview[]>([]);
  useEffect(() => {
    setCurrentTime(0);
    setSegments([]);
    if (!selectedFileId) return;
    let cancelled = false;
    apiFetch<{ segments: SegmentPreview[] }>(`/api/files/${selectedFileId}/segments`)
      .then((r) => {
        if (!cancelled) setSegments(r.segments ?? []);
      })
      .catch(() => {
        if (!cancelled) setSegments([]);
      });
    return () => { cancelled = true; };
  }, [selectedFileId]);
```

Replace with:

```typescript
  // Lang picker state — defaults to the file's source_lang once the hook
  // resolves; we reset on file change so old lang doesn't bleed across files.
  const [activeLang, setActiveLang] = useState<string>('zh');
  useEffect(() => {
    setCurrentTime(0);
    setActiveLang('zh');
  }, [selectedFileId]);

  // Replaces the legacy /api/files/<id>/segments fetch. The hook now sources
  // the live overlay from v5 by_lang (verifier-corrected + refined text) and
  // falls back to /segments only when translations are empty.
  const {
    segments,
    availableLangs,
    sourceLang,
  } = useDashboardTranslations(selectedFileId ?? null, activeLang);

  // Promote source_lang to activeLang once the hook discovers it, so the
  // first paint after a file change picks the right lang automatically.
  useEffect(() => {
    if (sourceLang && availableLangs.includes(sourceLang)) {
      setActiveLang(sourceLang);
    } else if (availableLangs.length > 0 && !availableLangs.includes(activeLang)) {
      const first = availableLangs[0];
      if (first) setActiveLang(first);
    }
    // Intentionally exclude activeLang to avoid resetting after the user picks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceLang, availableLangs.join('|')]);
```

- [ ] **Step 4: Render `<LangPicker>` in the workbench above the video**

Find the `<VideoSubtitleOverlay segments={segments} currentTime={currentTime} />` line (around 1197). The `<video>` element + overlay sit inside a container. Insert the lang picker JUST ABOVE the video container — find the parent that wraps the `<video>` (typically the element that has `position: relative` so the overlay can absolutely-position inside). The picker should sit OUTSIDE the video container so it doesn't interfere with the overlay's absolute positioning.

The cleanest insertion point is inside the workbench JSX returned by `BoldWorkbench`. Look for the wrapping element near the `<video>` and insert the picker before it. The most common pattern in this codebase is the video container has a class like `video-area` or similar styling — search for `<video` in the file and find the immediate parent `<div>`.

Insert this snippet immediately before the `<video>` element's wrapping div (e.g., inside the workbench's main content, before the video region):

```typescript
{availableLangs.length >= 1 && (
  <LangPicker
    availableLangs={availableLangs}
    activeLang={activeLang}
    onSelect={setActiveLang}
  />
)}
```

Implementer judgment call: if the structure of `BoldWorkbench` makes "directly above the video" awkward (e.g., the video is in a sub-component), insert the LangPicker as a new prop into `BoldWorkbench`'s render output above the playback bar / waveform. The visible result must be: a small row of lang chips visible above or below the video player, only when there's at least one available lang.

- [ ] **Step 5: TypeScript + build check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep Dashboard | head -10`
Expected: zero new errors. The local `SegmentPreview` definition (line 923) and the hook's exported `SegmentPreview` are structurally identical, so the type inference at `useDashboardTranslations(...)` should resolve cleanly. If there's a clash, alias the hook's type at import: `import { useDashboardTranslations, type SegmentPreview as HookSegmentPreview } from '@/hooks/useDashboardTranslations';`

Run: `cd frontend && npm run build 2>&1 | tail -5`
Expected: Vite build succeeds.

- [ ] **Step 6: Run full frontend test suite**

Run: `cd frontend && npm run test 2>&1 | tail -10`
Expected: All previous tests still pass + 8 new useDashboardTranslations tests pass. Total around 240 tests.

- [ ] **Step 7: Commit T3**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(v5): Dashboard live overlay reads v5 by_lang + lang picker

Replaces the local /api/files/<id>/segments fetch on the dashboard with
useDashboardTranslations, which sources subtitle text from the
verifier-corrected + refined per-lang output (via ?shape=v5). A small
LangPicker now sits above the video; for v4 files / ASR-only files,
the hook silently falls back to raw segments and the picker hides.

VideoSubtitleOverlay + InspectorTranscriptPreview keep their existing
SegmentPreview[] prop — the boundary adaptation lives entirely in the
hook, so neither component required changes.

Closes the 'dashboard overlay doesn't reflect v5 improvements' known
gap from the v5-A3 final review."
```

---

## Phase 4 — Wrap-up

### Task 4: Final verification + CLAUDE.md entry

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run all checks together**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
cd frontend && npx tsc --noEmit 2>&1 | tail -5
cd frontend && npm run test 2>&1 | tail -5
cd frontend && npm run build 2>&1 | tail -5
```

Expected output for each:
- `tsc` — empty (no errors)
- `npm run test` — passes total (~240 tests across 37+ files)
- `npm run build` — `✓ built in <time>` with no errors

- [ ] **Step 2: Manual smoke (optional, if dev servers running)**

If `npm run dev` is running:

```bash
curl -s -X POST http://localhost:5001/login -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"AdminPass1!"}'
```

Then in the browser at http://localhost:5173/:
- Select a v5-pipeline file from the file list
- Verify the lang picker appears above the video
- Click between langs and confirm the overlay text changes
- Select a v4 file (or no-pipeline file) and confirm the picker hides + the overlay still shows raw ASR

If the dev servers aren't running, skip this step — automated tests + tsc + build are authoritative.

- [ ] **Step 3: Update CLAUDE.md**

Open `CLAUDE.md`. Find the v5-A3 entry (starts `### v5-A3 — Frontend Multi-Lang UI (in progress on \`feat/frontend-redesign\`)`). Below the existing "Out of A3 scope" bullet, append a NEW bullet:

```markdown
- **v5-A3 follow-up — Dashboard overlay multilang** ([docs/superpowers/plans/2026-05-20-v5-dashboard-overlay-multilang-plan.md](docs/superpowers/plans/2026-05-20-v5-dashboard-overlay-multilang-plan.md)): Dashboard live subtitle overlay + inspector transcript preview now read from `entry['translations'][].by_lang[activeLang].text` (verifier-corrected canonical + refiner-polished output) instead of `entry['segments']` (raw asr_primary). New shared `components/LangPicker.tsx` (lifted from Proofread's `TargetLangTabs`). New `hooks/useDashboardTranslations.ts` boundary adapter fetches `?shape=v5` in parallel with `/segments` and falls back to raw segments for v4 / ASR-only files. Closes the "dashboard overlay doesn't reflect v5 improvements" gap from v5-A3 final review.
```

- [ ] **Step 4: Commit T4**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add CLAUDE.md
git commit -m "docs(v5): CLAUDE.md entry for dashboard overlay multilang follow-up"
```

- [ ] **Step 5: Final git log review**

Run: `git log --oneline c421131..HEAD | head -20`

Expected: 4 new v5 dashboard-overlay commits land cleanly on top of the existing v5-A3 commits. Branch ready to push (or to merge into main as part of the v5 deliverable).

---

## Self-review notes

**1. Spec coverage:**
- ✅ Dashboard overlay reads `translations[].by_lang[activeLang].text` — covered by T2 hook + T3 wiring
- ✅ Lang picker UI (matches Proofread `TargetLangTabs`) — covered by T1 (extract) + T3 (render)
- ✅ v4 / ASR-only backward compat — covered by T2 fallback path + T2 test cases
- ✅ Empty translations fallback — covered by T2 test "falls back to /segments endpoint when translations are empty"
- ✅ No backend changes — explicitly out of scope, verified by "Files NOT touched" list
- ✅ Match Proofread's adapt-at-boundary pattern — T2 hook mirrors `useFileData` shape

**2. Placeholder scan:** Zero "TBD" / "TODO" / "fill in" / "similar to" / "add appropriate". Every code step has full code; every command has expected output. Step 4 in Task 3 ("Render `<LangPicker>` in the workbench") gives explicit JSX but defers exact placement to implementer judgment with a clear constraint ("must be visible above or below the video"); this is intentional — the workbench's JSX is nuanced and the implementer should make the placement call locally.

**3. Type consistency:**
- `SegmentPreview` interface (start/end/text) — consistent in hook + Dashboard (note in T3 Step 5 that the two structurally identical definitions don't clash)
- `V5Translation` — imported from `@/lib/api/v5` consistently (matches v5-A3 T2)
- `HookResult` shape returned in same key order: `segments` / `availableLangs` / `sourceLang` / `loading` — destructured the same way in T3 Step 3
- `useDashboardTranslations(fileId: string | null, activeLang: string)` signature — same arg order in T2 tests + T3 callsite

**4. TDD discipline:** T2 is the only task with real new logic; it follows full RED → GREEN per the writing-plans skill (Step 1 writes failing tests, Step 2 verifies failure, Step 3 implements, Step 4 verifies pass). T1 is pure refactor (delegate to existing tests). T3 is integration wiring (delegate to existing test suite for regression). T4 is docs.

**5. Files touched:** 3 new + 3 modified (1 of which is just a 2-line shim). Within YAGNI bounds.

---

**End of plan.**
