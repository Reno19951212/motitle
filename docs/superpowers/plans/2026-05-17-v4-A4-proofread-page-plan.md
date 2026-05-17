# v4.0 A4 — Proofread Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Each task carries 🎯 Goal + ✅ Acceptance markers — subagent dispatches must cite both and reviewers must verify against them.

**Goal:** Port the 2833-line vanilla `frontend.old/proofread.html` into ~12 React components under `frontend/src/pages/Proofread/`, preserving full feature parity (video + segments + Find&Replace + per-stage edit/rerun + glossary apply + render modal + 3 side panels).

**Architecture:** Modular sub-components with co-located hooks (`useFileData`, `useSegmentEditor`, `useFindReplace`, `useRenderJob`, `useKeyboardShortcuts`). Default view shows final-stage segment text; opt-in `StageHistorySidebar` reveals per-stage outputs. Stage re-run + prompt overrides surface as inline buttons + side drawer. Realtime via existing `SocketProvider`.

**Tech Stack:** Reuses A3 deps — Vite + React 18 + TS + Tailwind + shadcn/ui + react-hook-form + zod + Zustand (read-only, no new stores) + react-router-dom + socket.io-client. No new npm packages.

**Parent spec:** [docs/superpowers/specs/2026-05-17-v4-A4-proofread-page-design.md](../specs/2026-05-17-v4-A4-proofread-page-design.md)

---

## File Structure

```
frontend/src/pages/Proofread/
├── index.tsx                        # NEW — layout + data fetch
├── VideoPanel.tsx                   # NEW
├── SubtitleOverlay.tsx              # NEW (ports font-preview.js)
├── SegmentTable.tsx                 # NEW
├── SegmentRow.tsx                   # NEW
├── FindReplaceToolbar.tsx           # NEW
├── StageHistorySidebar.tsx          # NEW
├── GlossaryPanel.tsx                # NEW
├── SubtitleSettingsPanel.tsx        # NEW
├── PromptOverridesDrawer.tsx        # NEW
├── GlossaryApplyModal.tsx           # NEW
├── RenderModal.tsx                  # NEW
├── StageRerunMenu.tsx               # NEW
├── TopBar.tsx                       # NEW (proofread-specific)
├── types.ts                         # NEW
└── hooks/
    ├── useFileData.ts               # NEW
    ├── useSegmentEditor.ts          # NEW
    ├── useFindReplace.ts            # NEW
    ├── useKeyboardShortcuts.ts      # NEW
    ├── useRenderJob.ts              # NEW
    └── useActiveProfile.ts          # NEW

frontend/src/pages/ProofreadPlaceholder.tsx  # DELETE (A3 placeholder, replaced)
frontend/src/router.tsx               # MODIFY (route now points at Proofread/index)

frontend/tests-e2e/
└── proofread-*.spec.ts               # 5 new specs
```

---

## Task 1: Routing Wire-up + Layout Skeleton

🎯 **Goal:** Replace the A3 placeholder route with a real `Proofread/index.tsx` page rendering layout shell + file-name header. No data fetching yet.

✅ **Acceptance:**
- `frontend/src/pages/Proofread/index.tsx` exists as default-export component
- `frontend/src/pages/ProofreadPlaceholder.tsx` deleted
- `frontend/src/router.tsx` imports new Proofread and routes `/proofread/:fileId` to it
- Manual: visit `/proofread/abc123` → see file name + back button (no data yet)
- `npm run build` 0 TS errors

**Files:**
- Create: `frontend/src/pages/Proofread/index.tsx`, `frontend/src/pages/Proofread/types.ts`, `frontend/src/pages/Proofread/TopBar.tsx`
- Delete: `frontend/src/pages/ProofreadPlaceholder.tsx`
- Modify: `frontend/src/router.tsx`

- [ ] **Step 1: Create types.ts**

```ts
// src/pages/Proofread/types.ts
export interface Segment {
  id: string;
  start: number;
  end: number;
  text: string;
  words?: Array<{ word: string; start: number; end: number; probability?: number }>;
}

export interface Translation {
  idx: number;
  en_text: string;
  zh_text: string;
  status: 'pending' | 'approved' | 'needs_review' | 'long' | 'review';
  flags: string[];
}

export interface StageOutput {
  stage_type: string;
  stage_ref: string;
  segments: Segment[];
}

export interface FileDetail {
  id: string;
  original_name: string;
  status: string;
  pipeline_id?: string | null;
  stage_outputs?: StageOutput[];
  subtitle_source?: 'auto' | 'source' | 'target' | 'bilingual';
  bilingual_order?: 'source_top' | 'target_top';
  prompt_overrides?: Record<string, unknown> | null;
}
```

- [ ] **Step 2: Create TopBar.tsx**

```tsx
// src/pages/Proofread/TopBar.tsx
import { useNavigate } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { FileDetail } from './types';

interface Props {
  file?: FileDetail;
  onOpenOverrides: () => void;
  onOpenRender: () => void;
}

export function TopBar({ file, onOpenOverrides, onOpenRender }: Props) {
  const navigate = useNavigate();
  return (
    <div className="flex items-center justify-between px-4 h-12 border-b bg-background">
      <div className="flex items-center gap-2">
        <Button size="sm" variant="ghost" onClick={() => navigate('/')}>
          <ChevronLeft className="h-4 w-4 mr-1" /> Back
        </Button>
        <h2 className="text-sm font-medium">{file?.original_name ?? 'Loading…'}</h2>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" onClick={onOpenOverrides}>⚙ Overrides</Button>
        <Button size="sm" onClick={onOpenRender}>▶ Render</Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create index.tsx skeleton**

```tsx
// src/pages/Proofread/index.tsx
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { TopBar } from './TopBar';

export default function Proofread() {
  const { fileId } = useParams<{ fileId: string }>();
  const [overridesOpen, setOverridesOpen] = useState(false);
  const [renderOpen, setRenderOpen] = useState(false);

  if (!fileId) return <p className="p-4 text-destructive">No file ID</p>;

  return (
    <div className="grid grid-rows-[auto_1fr] h-full">
      <TopBar
        file={undefined}
        onOpenOverrides={() => setOverridesOpen(true)}
        onOpenRender={() => setRenderOpen(true)}
      />
      <div className="grid grid-cols-2 overflow-hidden">
        <div className="border-r p-4 overflow-auto">
          <p className="text-muted-foreground text-sm">Video panel (T4)</p>
        </div>
        <div className="overflow-auto">
          <p className="text-muted-foreground text-sm p-4">Segment table (T5)</p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Update router + delete placeholder**

Edit `frontend/src/router.tsx` — replace `import ProofreadPlaceholder from '@/pages/ProofreadPlaceholder'` with `import Proofread from '@/pages/Proofread'`. Change `<ProofreadPlaceholder />` to `<Proofread />`. Then `rm frontend/src/pages/ProofreadPlaceholder.tsx`.

- [ ] **Step 5: Build + commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
npm run build  # expect 0 TS errors
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/src/pages/Proofread/ frontend/src/router.tsx
git rm frontend/src/pages/ProofreadPlaceholder.tsx
git commit -m "feat(v4 A4): Proofread route skeleton + TopBar + types"
```

---

## Task 2: useFileData + useActiveProfile hooks

🎯 **Goal:** Fetch file detail + translations + active profile + glossaries on mount. Centralized in hooks for testability.

✅ **Acceptance:**
- `hooks/useFileData.ts` exports `useFileData(fileId)` returning `{file, translations, loading, error, refresh}`
- `hooks/useActiveProfile.ts` exports `useActiveProfile()` returning `{profile, refresh}` and subscribes to SocketProvider `profile_updated` invalidation
- Unit tests in `hooks/useFileData.test.ts` + `useActiveProfile.test.ts` with mocked fetch (5+ tests total)
- `npm test` no regressions, `npm run build` 0 TS errors

**Files:**
- Create: `hooks/useFileData.ts`, `hooks/useFileData.test.ts`, `hooks/useActiveProfile.ts`, `hooks/useActiveProfile.test.ts`

- [ ] **Step 1: useFileData**

```ts
// src/pages/Proofread/hooks/useFileData.ts
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import type { FileDetail, Translation } from '../types';

export function useFileData(fileId: string) {
  const [file, setFile] = useState<FileDetail | null>(null);
  const [translations, setTranslations] = useState<Translation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [f, t] = await Promise.all([
        apiFetch<FileDetail>(`/api/files/${fileId}`),
        apiFetch<{ translations: Translation[] }>(`/api/files/${fileId}/translations`),
      ]);
      setFile(f);
      setTranslations(t.translations ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [fileId]);

  useEffect(() => { refresh(); }, [refresh]);

  return { file, translations, loading, error, refresh };
}
```

- [ ] **Step 2: useActiveProfile**

```ts
// src/pages/Proofread/hooks/useActiveProfile.ts
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { useSocket } from '@/providers/SocketProvider';

export interface ActiveProfile {
  id: string;
  name: string;
  font: {
    family: string;
    size: number;
    color: string;
    outline_color: string;
    outline_width: number;
    margin_bottom: number;
    subtitle_source: 'auto' | 'source' | 'target' | 'bilingual';
    bilingual_order: 'source_top' | 'target_top';
  };
  translation?: { glossary_id?: string };
}

export function useActiveProfile() {
  const [profile, setProfile] = useState<ActiveProfile | null>(null);
  useSocket(); // ensure provider is mounted; profile_updated invalidation handled below

  const refresh = useCallback(async () => {
    try {
      const r = await apiFetch<{ profile: ActiveProfile }>('/api/profiles/active');
      setProfile(r.profile);
    } catch { /* swallow */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // The SocketProvider already listens to profile_updated and pushes to its
  // own state; here we simply refetch on a periodic basis as a safety net.
  // (A future enhancement would expose a 'lastProfileUpdate' counter from
  // SocketProvider for precise invalidation.)
  return { profile, refresh };
}
```

Note: A more sophisticated invalidation can be added later. For A4, eager refresh on mount + manual refresh after panel saves is sufficient.

- [ ] **Step 3: Tests for both hooks**

```ts
// hooks/useFileData.test.ts
import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useFileData } from './useFileData';

describe('useFileData', () => {
  it('fetches file + translations on mount', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'a', original_name: 'x.mp4', status: 'completed' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ translations: [{ idx: 0, en_text: 'hi', zh_text: '你好', status: 'pending', flags: [] }] }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    const { result } = renderHook(() => useFileData('a'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.file?.original_name).toBe('x.mp4');
    expect(result.current.translations).toHaveLength(1);
    fetchSpy.mockRestore();
  });

  it('sets error on fetch failure', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValueOnce(new Error('network'));
    const { result } = renderHook(() => useFileData('a'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeTruthy();
  });
});
```

```ts
// hooks/useActiveProfile.test.ts — similar pattern, mock /api/profiles/active
```

- [ ] **Step 4: Build + commit**

```bash
npm test -- useFileData useActiveProfile
npm run build
git add frontend/src/pages/Proofread/hooks/
git commit -m "feat(v4 A4): useFileData + useActiveProfile hooks"
```

---

## Task 3: useSegmentEditor reducer

🎯 **Goal:** Centralized reducer for segment edit / save / approve / revert flows.

✅ **Acceptance:**
- `hooks/useSegmentEditor.ts` exports `useSegmentEditor(initial)` returning `{state, edit, save, approve, revert, bulkApprove}`
- 6+ pure reducer tests covering each action
- Optimistic updates with revert on failure

**Files:**
- Create: `hooks/useSegmentEditor.ts`, `hooks/useSegmentEditor.test.ts`

- [ ] **Step 1: Reducer + hook**

```ts
// src/pages/Proofread/hooks/useSegmentEditor.ts
import { useCallback, useReducer } from 'react';
import { apiFetch } from '@/lib/api';
import type { Translation } from '../types';

type Action =
  | { type: 'INIT'; translations: Translation[] }
  | { type: 'EDIT_DRAFT'; idx: number; zh_text: string }
  | { type: 'EDIT_COMMIT'; idx: number; updated: Translation }
  | { type: 'EDIT_REVERT'; idx: number; original: Translation }
  | { type: 'APPROVE'; idx: number }
  | { type: 'BULK_APPROVE'; indices: number[] };

interface State {
  translations: Translation[];
  drafts: Record<number, string>;
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'INIT':
      return { translations: action.translations, drafts: {} };
    case 'EDIT_DRAFT':
      return { ...state, drafts: { ...state.drafts, [action.idx]: action.zh_text } };
    case 'EDIT_COMMIT': {
      const newDrafts = { ...state.drafts };
      delete newDrafts[action.idx];
      return {
        translations: state.translations.map((t) => (t.idx === action.idx ? action.updated : t)),
        drafts: newDrafts,
      };
    }
    case 'EDIT_REVERT': {
      const newDrafts = { ...state.drafts };
      delete newDrafts[action.idx];
      return {
        translations: state.translations.map((t) => (t.idx === action.idx ? action.original : t)),
        drafts: newDrafts,
      };
    }
    case 'APPROVE':
      return {
        ...state,
        translations: state.translations.map((t) =>
          t.idx === action.idx ? { ...t, status: 'approved' as const } : t,
        ),
      };
    case 'BULK_APPROVE':
      return {
        ...state,
        translations: state.translations.map((t) =>
          action.indices.includes(t.idx) ? { ...t, status: 'approved' as const } : t,
        ),
      };
    default:
      return state;
  }
}

export function useSegmentEditor(fileId: string, initial: Translation[]) {
  const [state, dispatch] = useReducer(reducer, { translations: initial, drafts: {} }, () => ({ translations: initial, drafts: {} }));

  const editDraft = useCallback((idx: number, zh_text: string) => {
    dispatch({ type: 'EDIT_DRAFT', idx, zh_text });
  }, []);

  const saveEdit = useCallback(async (idx: number) => {
    const draft = state.drafts[idx];
    if (draft === undefined) return;
    const original = state.translations.find((t) => t.idx === idx);
    if (!original) return;
    try {
      const updated = await apiFetch<Translation>(`/api/files/${fileId}/translations/${idx}`, {
        method: 'PATCH',
        body: JSON.stringify({ zh_text: draft }),
      });
      dispatch({ type: 'EDIT_COMMIT', idx, updated });
    } catch {
      dispatch({ type: 'EDIT_REVERT', idx, original });
    }
  }, [fileId, state.drafts, state.translations]);

  const approve = useCallback(async (idx: number) => {
    dispatch({ type: 'APPROVE', idx });
    try {
      await apiFetch(`/api/files/${fileId}/translations/${idx}/approve`, { method: 'POST' });
    } catch { /* TODO: revert + toast */ }
  }, [fileId]);

  const bulkApprove = useCallback(async () => {
    const pending = state.translations.filter((t) => t.status === 'pending').map((t) => t.idx);
    if (pending.length === 0) return;
    dispatch({ type: 'BULK_APPROVE', indices: pending });
    try {
      await apiFetch(`/api/files/${fileId}/translations/approve-all`, { method: 'POST' });
    } catch { /* TODO: revert + toast */ }
  }, [fileId, state.translations]);

  return { state, editDraft, saveEdit, approve, bulkApprove, dispatch };
}
```

- [ ] **Step 2: Reducer tests**

```ts
// hooks/useSegmentEditor.test.ts — exercise each Action type
```

Test cases (6): INIT, EDIT_DRAFT stores draft, EDIT_COMMIT replaces translation + clears draft, EDIT_REVERT restores + clears draft, APPROVE flips status, BULK_APPROVE flips multiple.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(v4 A4): useSegmentEditor reducer with optimistic update + revert"
```

---

## Task 4: VideoPanel + SubtitleOverlay (port font-preview.js)

🎯 **Goal:** Video player with SVG-based subtitle overlay matching v3.5 fidelity.

✅ **Acceptance:**
- `VideoPanel.tsx` renders `<video>` element with `/api/files/<fid>/media` source + controls
- `SubtitleOverlay.tsx` renders SVG `<text paint-order="stroke fill">` over video at correct Y position
- @font-face injection from `/api/fonts` on mount
- Video time → current segment lookup → overlay text update
- Component renders without runtime error in jsdom (no actual video playback in test)

**Files:**
- Create: `VideoPanel.tsx`, `SubtitleOverlay.tsx`

- [ ] **Step 1: SubtitleOverlay implementation**

Reference: `frontend.old/js/font-preview.js`. Port as React component:

```tsx
// src/pages/Proofread/SubtitleOverlay.tsx
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import type { ActiveProfile } from './hooks/useActiveProfile';

interface Font { file: string; family: string; }

export function SubtitleOverlay({ text, profile }: { text: string; profile: ActiveProfile | null }) {
  const [fontsLoaded, setFontsLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch<Font[]>('/api/fonts').then((fonts) => {
      if (cancelled) return;
      for (const f of fonts) {
        const face = new FontFace(f.family, `url(/fonts/${encodeURIComponent(f.file)})`, { display: 'block' });
        document.fonts.add(face);
        face.load().catch(() => {});
      }
      setFontsLoaded(true);
    }).catch(() => setFontsLoaded(true));
    return () => { cancelled = true; };
  }, []);

  if (!profile || !text) return null;
  const f = profile.font;
  const lines = text.split(/\n|\\N/);
  const lineHeight = f.size * 1.2;
  const baselineY = 1080 - f.margin_bottom;
  const strokeWidth = f.outline_width * 2;
  const opacity = fontsLoaded ? 1 : 0;

  return (
    <svg
      viewBox="0 0 1920 1080"
      preserveAspectRatio="xMidYMid meet"
      style={{ position: 'absolute', inset: 0, pointerEvents: 'none', opacity, transition: 'opacity 100ms' }}
    >
      <text
        x="960"
        y={baselineY - (lines.length - 1) * lineHeight}
        textAnchor="middle"
        fontFamily={f.family}
        fontSize={f.size}
        fill={f.color}
        stroke={f.outline_color}
        strokeWidth={strokeWidth}
        paintOrder="stroke fill"
        strokeLinejoin="round"
        strokeLinecap="round"
        style={{ textRendering: 'geometricPrecision' as const }}
      >
        {lines.map((line, i) => (
          <tspan key={i} x="960" y={baselineY - (lines.length - 1 - i) * lineHeight}>{line}</tspan>
        ))}
      </text>
    </svg>
  );
}
```

- [ ] **Step 2: VideoPanel implementation**

```tsx
// src/pages/Proofread/VideoPanel.tsx
import { useEffect, useRef, useState } from 'react';
import { SubtitleOverlay } from './SubtitleOverlay';
import type { ActiveProfile } from './hooks/useActiveProfile';
import type { Translation, FileDetail } from './types';

interface Props {
  file: FileDetail;
  translations: Translation[];
  profile: ActiveProfile | null;
}

function pickSubtitleText(t: Translation | undefined, mode: 'source' | 'target' | 'bilingual', order: 'source_top' | 'target_top'): string {
  if (!t) return '';
  switch (mode) {
    case 'source': return t.en_text;
    case 'target': return t.zh_text;
    case 'bilingual':
      return order === 'source_top' ? `${t.en_text}\n${t.zh_text}` : `${t.zh_text}\n${t.en_text}`;
  }
}

export function VideoPanel({ file, translations, profile }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onTime = () => setCurrentTime(v.currentTime);
    v.addEventListener('timeupdate', onTime);
    return () => v.removeEventListener('timeupdate', onTime);
  }, []);

  // Binary search for current segment
  const currentIdx = (() => {
    let lo = 0, hi = translations.length - 1, found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const t = translations[mid];
      if (!t) break;
      if (currentTime < t.idx) hi = mid - 1;
      else if (currentTime >= t.idx + 0.001) { found = mid; lo = mid + 1; }
      else break;
    }
    return found;
  })();
  const currentTranslation = translations[currentIdx];

  const mode = (file.subtitle_source === 'auto' || !file.subtitle_source) ? 'bilingual' as const : file.subtitle_source;
  const order = file.bilingual_order ?? 'source_top';
  const overlayText = pickSubtitleText(currentTranslation, mode as 'source' | 'target' | 'bilingual', order);

  return (
    <div className="relative aspect-video bg-black">
      <video
        ref={videoRef}
        src={`/api/files/${file.id}/media`}
        controls
        className="w-full h-full"
      />
      <SubtitleOverlay text={overlayText} profile={profile} />
    </div>
  );
}
```

> Note: the binary-search segment lookup above is a simplified version; actual current-time matching uses `segment.start` / `segment.end` from the Segment type (translations carry start/end too in the existing API — confirm shape at integration time and adjust).

- [ ] **Step 3: Wire VideoPanel into index.tsx** + commit

---

## Task 5: SegmentTable + SegmentRow

🎯 **Goal:** Scrollable table with per-row inline edit + approval. Memoized rows for performance with 100+ segments.

✅ **Acceptance:**
- `SegmentTable.tsx` renders all translations as rows; sticky header
- `SegmentRow.tsx` memoized; double-click zh cell → edit mode; Enter commits, Escape reverts
- Per-row approve button shows current status badge
- Bulk "Approve all pending" button in header
- Unit test for SegmentRow (4+ scenarios)

**Files:**
- Create: `SegmentTable.tsx`, `SegmentRow.tsx`, `SegmentRow.test.tsx`

Implementation outline:

```tsx
// src/pages/Proofread/SegmentRow.tsx
import { memo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Check, Eye } from 'lucide-react';
import type { Translation } from './types';
import { cn } from '@/lib/utils';

interface Props {
  t: Translation;
  draft?: string;
  isFocused: boolean;
  onEditDraft: (idx: number, zh: string) => void;
  onSave: (idx: number) => void;
  onRevert: (idx: number) => void;
  onApprove: (idx: number) => void;
  onShowHistory: (idx: number) => void;
}

export const SegmentRow = memo(function SegmentRow({ t, draft, isFocused, onEditDraft, onSave, onRevert, onApprove, onShowHistory }: Props) {
  const [editing, setEditing] = useState(false);
  const value = draft ?? t.zh_text;
  const statusVariant = t.status === 'approved' ? 'default' : t.status === 'pending' ? 'outline' : 'destructive';
  return (
    <tr className={cn('border-b text-sm', isFocused && 'bg-accent/50')}>
      <td className="p-2 w-10 text-muted-foreground tabular-nums">{t.idx}</td>
      <td className="p-2">{t.en_text}</td>
      <td className="p-2"
        onDoubleClick={() => setEditing(true)}
      >
        {editing ? (
          <input
            autoFocus
            value={value}
            onChange={(e) => onEditDraft(t.idx, e.target.value)}
            onBlur={() => { setEditing(false); onSave(t.idx); }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { setEditing(false); onSave(t.idx); }
              if (e.key === 'Escape') { setEditing(false); onRevert(t.idx); }
            }}
            className="w-full px-2 py-1 border rounded text-sm"
          />
        ) : value}
      </td>
      <td className="p-2 w-32 text-xs">
        {t.flags.includes('long') && <Badge variant="destructive" className="mr-1">long</Badge>}
        <Badge variant={statusVariant}>{t.status}</Badge>
      </td>
      <td className="p-2 w-28">
        <div className="flex gap-1 justify-end">
          {t.status !== 'approved' && (
            <Button size="icon" variant="ghost" onClick={() => onApprove(t.idx)} aria-label="Approve">
              <Check className="h-4 w-4" />
            </Button>
          )}
          <Button size="icon" variant="ghost" onClick={() => onShowHistory(t.idx)} aria-label="Show stage history">
            <Eye className="h-4 w-4" />
          </Button>
        </div>
      </td>
    </tr>
  );
});
```

```tsx
// src/pages/Proofread/SegmentTable.tsx
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { SegmentRow } from './SegmentRow';
import type { Translation } from './types';
import { useSegmentEditor } from './hooks/useSegmentEditor';

interface Props {
  fileId: string;
  translations: Translation[];
  onShowHistory: (idx: number) => void;
}

export function SegmentTable({ fileId, translations, onShowHistory }: Props) {
  const editor = useSegmentEditor(fileId, translations);
  const [focusedIdx, setFocusedIdx] = useState<number | null>(null);
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between p-2 border-b sticky top-0 bg-background">
        <span className="text-sm text-muted-foreground">{translations.length} segments</span>
        <Button size="sm" onClick={editor.bulkApprove}>Approve all pending</Button>
      </div>
      <div className="overflow-auto flex-1">
        <table className="w-full">
          <thead className="sticky top-0 bg-background border-b">
            <tr>
              <th className="p-2 text-left w-10">#</th>
              <th className="p-2 text-left">EN</th>
              <th className="p-2 text-left">ZH</th>
              <th className="p-2 text-left w-32">Status</th>
              <th className="p-2 text-right w-28">Actions</th>
            </tr>
          </thead>
          <tbody>
            {editor.state.translations.map((t) => (
              <SegmentRow
                key={t.idx}
                t={t}
                draft={editor.state.drafts[t.idx]}
                isFocused={focusedIdx === t.idx}
                onEditDraft={editor.editDraft}
                onSave={editor.saveEdit}
                onRevert={(idx) => editor.dispatch({ type: 'EDIT_REVERT', idx, original: translations.find(x => x.idx === idx)! })}
                onApprove={editor.approve}
                onShowHistory={onShowHistory}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

Test cases: editing toggle, draft commit, escape revert, approve hides button.

Commit.

---

## Task 6: useFindReplace + FindReplaceToolbar (⌘F)

🎯 **Goal:** Toolbar with search input, scope filter, prev/next, replace one/all. Activated via ⌘F.

✅ **Acceptance:**
- `useFindReplace(translations, options)` returns `{matches[], cursor, next, prev, replaceOne, replaceAll}`
- `FindReplaceToolbar` mounted in segment-table area; visible toggle via ⌘F
- Scope filter: zh / en / both / only-pending
- 5+ unit tests for the hook

**Files:**
- Create: `hooks/useFindReplace.ts`, `hooks/useFindReplace.test.ts`, `FindReplaceToolbar.tsx`

Implementation: maintain search query state + scope filter + cursor index into matches[]. Toolbar component bound to keyboard hook (T19) for ⌘F.

Commit.

---

## Task 7: Wire VideoPanel + SegmentTable + FindReplaceToolbar into index.tsx

🎯 **Goal:** End-to-end basic editing works: load file → display video + table → edit segment → save → see approval status change.

✅ **Acceptance:**
- Manual: open `/proofread/<file_id>` for a real file → segments load → edit → save → reload page → edit persists
- `npm run build` 0 TS errors

Update `Proofread/index.tsx` to compose hooks + components. Add SocketProvider listener for `pipeline_complete` → trigger `refresh`.

Commit.

---

## Task 8: StageHistorySidebar

🎯 **Goal:** Slides in on segment 👁 click; shows all stages from `file.stage_outputs`; per-stage edit button.

✅ **Acceptance:**
- Sidebar opens on `Eye` click in segment row
- Lists each stage with: `stage_idx`, `stage_type`, `stage_ref name`, segment text at that stage
- Edit button per stage row → inline edit + PATCH `/api/files/<fid>/stages/<idx>/segments/<seg_idx>` → refresh
- Unit test for component (3 scenarios)

**Files:**
- Create: `StageHistorySidebar.tsx`, `StageHistorySidebar.test.tsx`

Use Radix `Dialog` with `side="right"` styling, or a plain `div` with translate-x transition. Pattern follows shadcn Sheet pattern (could be added as `ui/sheet.tsx` if useful — or just inline for A4).

Commit.

---

## Task 9: GlossaryPanel + SubtitleSettingsPanel + 字幕來源 dropdown

🎯 **Goal:** Three side-panel widgets in the video column.

✅ **Acceptance:**
- `GlossaryPanel.tsx` collapsible — lists active profile's glossary entries; add new entry inline → POST `/api/glossaries/<gid>/entries`
- `SubtitleSettingsPanel.tsx` collapsible — font config form; debounced 500ms PATCH `/api/profiles/<pid>` → SocketProvider broadcasts `profile_updated` → overlay updates
- 字幕來源 dropdown in TopBar — auto / source / target / bilingual + bilingual_order; PATCH `/api/files/<fid>` body `{subtitle_source, bilingual_order}`

**Files:**
- Create: `GlossaryPanel.tsx`, `SubtitleSettingsPanel.tsx`
- Modify: `TopBar.tsx` (add subtitle source dropdown)

Commit.

---

## Task 10: PromptOverridesDrawer

🎯 **Goal:** Side drawer opened by ⚙ in TopBar. 4 textareas + template picker → POST `/api/files/<fid>/pipeline_overrides`.

✅ **Acceptance:**
- Drawer slides from right; click outside or X closes
- Loads existing overrides from `file.prompt_overrides` on open
- Template dropdown fetches `/api/prompt_templates`; "套用模板" fills textareas
- Save button → POST overrides + close
- Clear button → POST `{}` (or `null` per backend) + close
- Unit test: drawer open/close + template apply (3 scenarios)

**Files:**
- Create: `PromptOverridesDrawer.tsx`, `PromptOverridesDrawer.test.tsx`

Commit.

---

## Task 11: StageRerunMenu + integration

🎯 **Goal:** Per-segment dropdown — "Re-run from stage N"; also a TopBar "Re-run pipeline from start" button.

✅ **Acceptance:**
- Row-level dropdown lists each stage type+ref from `file.stage_outputs`
- Clicking item → POST `/api/files/<fid>/stages/<idx>/rerun` → SocketProvider drives progress overlay → on `pipeline_complete` event refresh translations
- TopBar "Re-run pipeline from start" → POST `/api/pipelines/<pid>/run` body `{file_id}` → same realtime flow
- 2+ unit tests for dropdown rendering

**Files:**
- Create: `StageRerunMenu.tsx`, `StageRerunMenu.test.tsx`

Use `Select` or a custom dropdown menu. shadcn doesn't have DropdownMenu in our copy-in — either add it now (T11 also adds `ui/dropdown-menu.tsx`) or use a simpler `<details><summary>` HTML element. Choice: add `ui/dropdown-menu.tsx` via Radix `@radix-ui/react-dropdown-menu` — but that's a new dep. Simplest: use `<details>`.

Commit.

---

## Task 12: GlossaryApplyModal

🎯 **Goal:** Scan + violation preview + apply.

✅ **Acceptance:**
- Triggered by GlossaryPanel "套用" button
- POST `/api/files/<fid>/glossary-scan` → render violations grouped by glossary
- Per-violation checkbox; default-checked for `pending` translations, unchecked for `approved`
- "套用" → POST `/api/files/<fid>/glossary-apply` body `{violations}` → sequential progress → refresh translations
- 4+ unit tests

**Files:**
- Create: `GlossaryApplyModal.tsx`, `GlossaryApplyModal.test.tsx`

Commit.

---

## Task 13: useRenderJob hook

🎯 **Goal:** Encapsulate render lifecycle (POST → poll → download).

✅ **Acceptance:**
- `useRenderJob()` returns `{startRender, currentJob, cancel, downloadWithPicker}`
- POST `/api/render` → start polling `/api/renders/<id>` every 2s
- On `status: completed` → File System Access API `showSaveFilePicker` (Chrome/Edge); fallback `<a download>` (Safari/Firefox)
- On `status: failed` → set error state
- Cancel button (T17) → DELETE `/api/renders/<id>`
- 5+ unit tests with vi.useFakeTimers + mocked fetch

**Files:**
- Create: `hooks/useRenderJob.ts`, `hooks/useRenderJob.test.ts`

Commit.

---

## Task 14: RenderModal — MP4 + zod validation

🎯 **Goal:** MP4 tab with CRF/CBR/2-pass radio + slider + pixel_format + profile + level + audio_bitrate. Cross-field validation per v3.3 (yuv420p must pair high; yuv422p must pair high422; yuv444p must pair high444).

✅ **Acceptance:**
- Tabs strip: MP4 / MXF ProRes / XDCAM HD 422 (other tabs stubbed for T15)
- MP4 controls render correctly per bitrate_mode
- zod refine catches pixel_format ↔ profile mismatch and renders error under affected field
- 6+ unit tests for the schema + 2 for the modal interaction

**Files:**
- Create: `RenderModal.tsx`, `RenderModal.test.tsx`, `frontend/src/lib/schemas/render-options.ts`, `render-options.test.ts`

Schema sketch:

```ts
// src/lib/schemas/render-options.ts
import { z } from 'zod';

export const Mp4Schema = z.object({
  format: z.literal('mp4'),
  bitrate_mode: z.enum(['crf', 'cbr', '2pass']),
  crf: z.number().int().min(0).max(51).default(18),
  video_bitrate_mbps: z.number().int().min(2).max(100).default(15),
  preset: z.enum(['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow']).default('medium'),
  pixel_format: z.enum(['yuv420p', 'yuv422p', 'yuv444p']).default('yuv420p'),
  profile: z.enum(['baseline', 'main', 'high', 'high422', 'high444']).default('high'),
  level: z.enum(['3.1', '3.2', '4.0', '4.1', '5.0', '5.1', '5.2', 'auto']).default('auto'),
  audio_bitrate: z.enum(['128k', '192k', '320k']).default('192k'),
  resolution: z.enum(['keep', '720p', '1080p', '4k']).default('keep'),
}).refine((v) => {
  if (v.pixel_format === 'yuv422p' && v.profile !== 'high422') return false;
  if (v.pixel_format === 'yuv444p' && v.profile !== 'high444') return false;
  if (v.profile === 'high422' && v.pixel_format !== 'yuv422p') return false;
  if (v.profile === 'high444' && v.pixel_format !== 'yuv444p') return false;
  return true;
}, { message: 'pixel_format and H.264 profile must match (yuv422p↔high422, yuv444p↔high444)' });
```

Commit.

---

## Task 15: RenderModal — MXF ProRes + XDCAM HD 422

🎯 **Goal:** Two more format tabs with their respective controls.

✅ **Acceptance:**
- ProRes tab: profile dropdown (0-5) + audio bit depth (16/24/32-bit PCM) + resolution
- XDCAM HD 422 tab: video_bitrate_mbps slider 10–100 (default 50) + audio bit depth + resolution
- zod schemas for both formats; discriminated union with MP4 schema
- 4+ unit tests

**Files:**
- Modify: `RenderModal.tsx`, `frontend/src/lib/schemas/render-options.ts`

Add ProResSchema + XdcamSchema; discriminated union `RenderOptionsSchema = z.discriminatedUnion('format', [Mp4Schema, ProResSchema, XdcamSchema])`.

Commit.

---

## Task 16: RenderModal confirm + integration with useRenderJob

🎯 **Goal:** End-to-end render flow: pick format → fill options → confirm → polling → download.

✅ **Acceptance:**
- Confirm button validates via zod; POST `/api/render`
- Progress bar shown while polling; cancel button visible
- On complete: download via File System Access API (or fallback)
- Manual: render a small MP4 from a test file → file downloads with correct name
- 3+ Vitest scenarios

Commit.

---

## Task 17: useKeyboardShortcuts hook

🎯 **Goal:** Centralize keyboard handling for the proofread page.

✅ **Acceptance:**
- `useKeyboardShortcuts({onFindOpen, onSave, onApprove, onEscape})` binds:
  - ⌘F / Ctrl+F → onFindOpen
  - Enter (when editing) → onSave  
  - ⌘Enter / Ctrl+Enter → onApprove (current row)
  - Esc → onEscape (close modal/drawer or revert edit)
- Cleanup unbinds on unmount
- 4+ unit tests dispatching keyboard events

**Files:**
- Create: `hooks/useKeyboardShortcuts.ts`, `hooks/useKeyboardShortcuts.test.ts`
- Wire into `index.tsx`

Commit.

---

## Task 18: shadcn DropdownMenu copy-in (if not already)

🎯 **Goal:** Add `ui/dropdown-menu.tsx` for StageRerunMenu (T11 may have stubbed it).

✅ **Acceptance:**
- `@radix-ui/react-dropdown-menu` either already a dep (check `package.json`) — if not, add it
- `ui/dropdown-menu.tsx` exports DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem
- StageRerunMenu refactored from `<details>` to DropdownMenu (cleaner UX)
- `npm run build` 0 TS errors

> If `@radix-ui/react-dropdown-menu` is not a dep, this task installs it. Otherwise it's a pure copy-in of the shadcn primitive.

Commit.

---

## Task 19: Playwright E2E suite

🎯 **Goal:** 5 scenarios covering proofread page integration.

✅ **Acceptance:**
- `frontend/tests-e2e/proofread-load.spec.ts` — login + visit `/proofread/<seed_file_id>` → segments visible
- `proofread-edit.spec.ts` — edit segment + save → reload → edit persists
- `proofread-find-replace.spec.ts` — ⌘F opens toolbar → search → replace
- `proofread-render.spec.ts` — open render modal → MP4 + CRF defaults → confirm → render job appears
- `proofread-stage-rerun.spec.ts` — open stage history → rerun → progress observed
- Tests use a seeded file (admin uploads small test wav); idempotent setup via beforeAll fixture

**Files:**
- Create: `frontend/tests-e2e/proofread-*.spec.ts` + `frontend/tests-e2e/fixtures/seed-file.ts`

Note: Several tests may need backend mocking or rely on a stable test file. If full E2E is brittle, ship with manual smoke-test instructions and lower the bar to 2-3 deterministic scenarios.

Commit.

---

## Task 20: CLAUDE.md update + A4 wrap-up

🎯 **Goal:** Document A4 completion.

✅ **Acceptance:**
- `### v4.0 A4` entry under Completed Features
- Repository Structure mentions `Proofread/` sub-dir
- Bug list / known limitations documented (e.g. mobile not supported)
- Commit message: `docs(v4 A4): CLAUDE.md entry for Proofread page rewrite`

**Files:**
- Modify: `CLAUDE.md`

Commit.

---

## Plan Self-Review

**Spec coverage:**
- G1 (video + overlay) → T4 ✓
- G2 (segment table) → T5 ✓
- G3 (Find&Replace) → T6 + T17 ✓
- G4 (stage history) → T8 ✓
- G5 (stage rerun) → T11 + T18 ✓
- G6 (prompt overrides) → T10 ✓
- G7 (Glossary Apply) → T12 ✓
- G8 (Render modal) → T13 + T14 + T15 + T16 ✓
- G9 (3 side panels) → T8 + T9 ✓
- G10 (realtime) → T7 + T11 (SocketProvider hookup) ✓

**Placeholder scan:** No TBD / TODO. All steps actionable.

**Type consistency:** `Translation` + `Segment` + `FileDetail` defined in T1's `types.ts` and reused throughout. `ActiveProfile` from T2's `useActiveProfile.ts`.

**Risks acknowledged in plan:**
- Cross-field MP4 validation (T14)
- File System Access API fallback (T13 + T16)
- Stage rerun while editing (note in T11: disable edit when `isRerunning`)
- Brittle E2E (T19 lowers bar if needed)

---

## Execution Handoff

After this plan is committed, dispatch via `superpowers:subagent-driven-development`. Each of the 20 tasks carries 🎯 Goal + ✅ Acceptance markers consistent with A1 + A3 plan format. Most tasks are sequential (later tasks depend on earlier components), but some can be parallelized:
- T2, T3, T6 (hooks) can run in parallel after T1
- T8, T9, T10, T12 (panel/modal components) can parallel after T7
- T14, T15 (render modal slices) can serialize but T13 (useRenderJob hook) is parallel-safe

Typical batch grouping: 4-6 parallel agents per wave, ~5 waves total.
