# Console UX Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 3 remaining ⚠ partial UX gaps in Console (Space play actually controls `<video>`, Render cell wired to live socket events, stage bar shows immediate feedback on enqueue via 4-state lifecycle).

**Architecture:** Three coordinated changes — frontend `VideoControlContext` lifts `<video>` element control out of TransportBar local state; backend `renderer.py` emits `render_*` socket events that frontend reducer consumes for the 4th stage cell + WorkerStatus merge; frontend `stagePhase` state field tracks queued/starting/running per file × stage to drive new cell states (queued + starting with pulse animation).

**Tech Stack:** Frontend Vite + React 18 + TypeScript strict + Vitest 2 + Playwright 1.48; Backend Python 3.11 + Flask + Flask-SocketIO + pytest. No new dependencies.

**Spec source:** `docs/superpowers/specs/2026-05-22-console-ux-completion-design.md`

---

## File structure overview

### Frontend — files created (4)
- `frontend/src/pages/Console/video-control-context.tsx` (Section 1)
- `frontend/src/pages/Console/video-control-context.test.tsx` (Section 1)

### Frontend — files modified (10)
- `frontend/src/pages/Console/VideoPanel.tsx` — register `<video>` ref via context (S1)
- `frontend/src/pages/Console/TransportBar.tsx` — consume context, drop props (S1)
- `frontend/src/pages/Console/Workbench.tsx` — wrap provider, simplify Space hotkey (S1)
- `frontend/src/lib/socket-events.ts` — 3 render event types + 2 render state fields + stagePhase field + STAGE_START action + reducer cases (S2+S3)
- `frontend/src/providers/SocketProvider.tsx` — 3 render listeners + 1 stage_start listener (S2+S3)
- `frontend/src/providers/SocketProvider.test.tsx` — new reducer cases (S2+S3)
- `frontend/src/hooks/useWorkerStatus.ts` — parallel-fetch + render-job merge (S2)
- `frontend/src/pages/Console/derive-stage-cells.ts` — position 3 + lifecycle-aware helper (S2+S3)
- `frontend/src/pages/Console/derive-stage-cells.test.ts` — new test cases (S2+S3)
- `frontend/src/pages/Console/to-console-file.ts` — forward renderStatus/renderProgress/stagePhaseMap (S2+S3)
- `frontend/src/pages/Console/types.ts` — 2 new enum literals (S3)
- `frontend/src/pages/Console/WorkerStatus.tsx` — stage-tag mapping for render (S2)
- `frontend/src/styles/console.css` — pulse keyframes + queued/starting selectors (S3)
- `frontend/tests-e2e/_user-workflow.spec.ts` — sharpened assertions (S1+S3)

### Backend — files created (1)
- `backend/tests/test_render_socket.py` (S2)

### Backend — files modified (2)
- `backend/renderer.py` or `backend/routes/render.py` (wherever `_run_render_job` lives) — emit 3 events (S2)

---

# Phase 1 — VideoControlContext (Bug 1)

## Task 1.1: Scaffold VideoControlContext module + unit tests

**Files:**
- Create: `frontend/src/pages/Console/video-control-context.tsx`
- Create: `frontend/src/pages/Console/video-control-context.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/pages/Console/video-control-context.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, act, screen } from '@testing-library/react';
import { useEffect } from 'react';
import { VideoControlProvider, useVideoControl } from './video-control-context';

function Probe({ onValue }: { onValue: (v: ReturnType<typeof useVideoControl>) => void }) {
  const v = useVideoControl();
  useEffect(() => { onValue(v); }, [v, onValue]);
  return null;
}

describe('VideoControlProvider', () => {
  it('initializes with playing=false, currentTime=0, duration=NaN', () => {
    let captured: ReturnType<typeof useVideoControl> | null = null;
    render(
      <VideoControlProvider>
        <Probe onValue={v => { captured = v; }} />
      </VideoControlProvider>
    );
    expect(captured?.playing).toBe(false);
    expect(captured?.currentTime).toBe(0);
    expect(Number.isNaN(captured?.duration)).toBe(true);
  });

  it('toggle() with no element registered is a no-op (does not throw)', () => {
    let captured: ReturnType<typeof useVideoControl> | null = null;
    render(
      <VideoControlProvider>
        <Probe onValue={v => { captured = v; }} />
      </VideoControlProvider>
    );
    expect(() => captured?.toggle()).not.toThrow();
    expect(captured?.playing).toBe(false);
  });

  it('useVideoControl() outside provider throws', () => {
    // Suppress error log noise from React for this expected throw
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe onValue={() => {}} />)).toThrow(
      /must be used inside <VideoControlProvider>/
    );
    spy.mockRestore();
  });

  it('setVideoEl(el) attaches play/pause listeners; firing play event flips playing=true', () => {
    let captured: ReturnType<typeof useVideoControl> | null = null;
    const Wrapper = () => {
      const v = useVideoControl();
      useEffect(() => { captured = v; }, [v]);
      return null;
    };
    const { container } = render(
      <VideoControlProvider>
        <Wrapper />
      </VideoControlProvider>
    );

    const video = document.createElement('video');
    container.appendChild(video);

    act(() => { captured!.setVideoEl(video); });
    act(() => { video.dispatchEvent(new Event('play')); });
    expect(captured?.playing).toBe(true);

    act(() => { video.dispatchEvent(new Event('pause')); });
    expect(captured?.playing).toBe(false);
  });

  it('setVideoEl(null) detaches listeners and resets state', () => {
    let captured: ReturnType<typeof useVideoControl> | null = null;
    const Wrapper = () => {
      const v = useVideoControl();
      useEffect(() => { captured = v; }, [v]);
      return null;
    };
    const { container } = render(
      <VideoControlProvider>
        <Wrapper />
      </VideoControlProvider>
    );

    const video = document.createElement('video');
    container.appendChild(video);
    act(() => { captured!.setVideoEl(video); });
    act(() => { video.dispatchEvent(new Event('play')); });
    expect(captured?.playing).toBe(true);

    act(() => { captured!.setVideoEl(null); });
    expect(captured?.playing).toBe(false);
    expect(captured?.currentTime).toBe(0);

    // Re-firing play on the detached element should NOT affect state
    act(() => { video.dispatchEvent(new Event('play')); });
    expect(captured?.playing).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/Console/video-control-context.test.tsx`
Expected: FAIL — `Cannot find module './video-control-context'` or similar import error

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/pages/Console/video-control-context.tsx`:

```tsx
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

export type VideoControlValue = {
  playing: boolean;
  currentTime: number;
  duration: number;
  setVideoEl: (el: HTMLVideoElement | null) => void;
  play: () => Promise<void>;
  pause: () => void;
  toggle: () => void;
  seek: (seconds: number) => void;
  seekPercent: (pct: number) => void;
};

const VideoControlCtx = createContext<VideoControlValue | null>(null);

export function useVideoControl(): VideoControlValue {
  const v = useContext(VideoControlCtx);
  if (!v) throw new Error('useVideoControl must be used inside <VideoControlProvider>');
  return v;
}

export type VideoControlProviderProps = {
  children: ReactNode;
};

export function VideoControlProvider({ children }: VideoControlProviderProps) {
  const elRef = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(NaN);

  const setVideoEl = useCallback((el: HTMLVideoElement | null) => {
    // Detach listeners from previous element
    const prev = elRef.current;
    if (prev) {
      prev.removeEventListener('play', handlePlay);
      prev.removeEventListener('pause', handlePause);
      prev.removeEventListener('timeupdate', handleTimeUpdate);
      prev.removeEventListener('loadedmetadata', handleLoadedMetadata);
    }
    elRef.current = el;
    setPlaying(false);
    setCurrentTime(0);
    setDuration(NaN);
    if (el) {
      el.addEventListener('play', handlePlay);
      el.addEventListener('pause', handlePause);
      el.addEventListener('timeupdate', handleTimeUpdate);
      el.addEventListener('loadedmetadata', handleLoadedMetadata);
    }

    function handlePlay() { setPlaying(true); }
    function handlePause() { setPlaying(false); }
    function handleTimeUpdate() { if (elRef.current) setCurrentTime(elRef.current.currentTime); }
    function handleLoadedMetadata() { if (elRef.current) setDuration(elRef.current.duration); }
  }, []);

  const play = useCallback(async () => {
    const el = elRef.current;
    if (!el) return;
    try { await el.play(); }
    catch (e) { console.warn('[VideoControl] play() rejected:', e); }
  }, []);

  const pause = useCallback(() => {
    const el = elRef.current;
    if (el) el.pause();
  }, []);

  const toggle = useCallback(() => {
    const el = elRef.current;
    if (!el) return;
    if (el.paused) void play();
    else pause();
  }, [play, pause]);

  const seek = useCallback((seconds: number) => {
    const el = elRef.current;
    if (!el) return;
    const dur = el.duration;
    const clamped = Math.max(0, isFinite(dur) ? Math.min(seconds, dur) : seconds);
    el.currentTime = clamped;
  }, []);

  const seekPercent = useCallback((pct: number) => {
    const el = elRef.current;
    if (!el || !isFinite(el.duration)) return;
    seek(pct * el.duration);
  }, [seek]);

  const value = useMemo<VideoControlValue>(() => ({
    playing, currentTime, duration, setVideoEl, play, pause, toggle, seek, seekPercent,
  }), [playing, currentTime, duration, setVideoEl, play, pause, toggle, seek, seekPercent]);

  // Cleanup on unmount
  useEffect(() => {
    return () => { setVideoEl(null); };
  }, [setVideoEl]);

  return <VideoControlCtx.Provider value={value}>{children}</VideoControlCtx.Provider>;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/Console/video-control-context.test.tsx`
Expected: 5 passed

- [ ] **Step 5: Verify typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 NEW errors (6 pre-existing v6-pipeline-smoke errors unchanged)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Console/video-control-context.tsx \
        frontend/src/pages/Console/video-control-context.test.tsx
git commit -m "feat(console): VideoControlContext for play/pause/seek over <video> element"
```

---

## Task 1.2: Wire VideoPanel to register element via context

**Files:**
- Modify: `frontend/src/pages/Console/VideoPanel.tsx`

- [ ] **Step 1: Read current VideoPanel**

Run: `cat frontend/src/pages/Console/VideoPanel.tsx`

Confirm current shape: receives `fileId`, `fileName`, `currentSubtitle`, `currentTimecode` props; renders `<video src=...controls/>` when `fileId` truthy.

- [ ] **Step 2: Replace `frontend/src/pages/Console/VideoPanel.tsx` entirely**

```tsx
import { useEffect, useRef } from 'react';
import { useVideoControl } from './video-control-context';

export type VideoPanelProps = {
  fileId?: string | null;
  fileName?: string;
  currentSubtitle?: string;
  currentTimecode?: string;
};

export function VideoPanel({ fileId, fileName, currentSubtitle, currentTimecode }: VideoPanelProps) {
  const ref = useRef<HTMLVideoElement | null>(null);
  const { setVideoEl } = useVideoControl();

  // Register/unregister the <video> element with the context on mount/unmount.
  // Re-runs when fileId changes because <video key={fileId}> forces remount.
  useEffect(() => {
    setVideoEl(ref.current);
    return () => { setVideoEl(null); };
  }, [setVideoEl, fileId]);

  return (
    <div className="con-video" data-testid="video-panel">
      {fileId ? (
        <video
          key={fileId}
          ref={ref}
          className="con-video-element"
          src={`/api/files/${fileId}/media`}
          controls
          preload="metadata"
          data-testid="video-element"
        />
      ) : (
        <div className="safe-grid" />
      )}
      <span className="preview-label">PVW · {fileName ?? '(未揀檔)'}</span>
      <span className="tc">{currentTimecode ?? '00:00:00:00'}</span>
      {currentSubtitle && (
        <div className="live-cap"><div>{currentSubtitle}</div></div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Run vitest for VideoPanel + dependents to confirm no regression**

Run: `cd frontend && npx vitest run src/pages/Console/`
Expected: existing tests pass (Console.test.tsx + others). Note: VideoPanel now requires a `<VideoControlProvider>` ancestor when rendered; if any test renders VideoPanel directly without provider, it will fail. If that happens, wrap in test setup.

If Console.test.tsx fails because Console renders VideoPanel via Workbench but Workbench isn't yet wrapped in provider (Task 1.4): expected — proceed to Task 1.4.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Console/VideoPanel.tsx
git commit -m "feat(console): VideoPanel registers <video> ref with VideoControlContext"
```

---

## Task 1.3: Wire TransportBar to consume context

**Files:**
- Modify: `frontend/src/pages/Console/TransportBar.tsx`

- [ ] **Step 1: Read current TransportBar**

Run: `cat frontend/src/pages/Console/TransportBar.tsx`

Confirm: takes `playing`, `onTogglePlay`, `currentTime`, `totalTime`, `scrubPercent` props. Renders play/pause toggle button, mono time display, scrub bar, volume placeholder, VU meter, settings button.

- [ ] **Step 2: Replace `frontend/src/pages/Console/TransportBar.tsx` entirely**

```tsx
import { useEffect, useState } from 'react';
import { Icon } from '../../lib/motitle-icons';
import { useVideoControl } from './video-control-context';
import { formatDuration } from '../../lib/format';

export type TransportBarProps = Record<string, never>;

function VUMeter() {
  const [heights, setHeights] = useState<number[]>([6, 9, 12, 8, 11, 7]);
  useEffect(() => {
    const t = setInterval(() => {
      setHeights(Array.from({ length: 6 }, () => 6 + Math.floor(Math.random() * 8)));
    }, 200);
    return () => clearInterval(t);
  }, []);
  return (
    <span className="r-vu live" data-testid="vu-meter">
      {heights.map((h, i) => <b key={i} style={{ height: h + 'px' }} />)}
    </span>
  );
}

export function TransportBar(_props: TransportBarProps) {
  const { playing, currentTime, duration, toggle, seekPercent } = useVideoControl();

  const totalTime = isFinite(duration) ? formatDuration(duration) : '—';
  const currentDisplay = formatDuration(currentTime);
  const scrubPercent = isFinite(duration) && duration > 0
    ? Math.max(0, Math.min(100, (currentTime / duration) * 100))
    : 0;

  return (
    <div className="con-transport" data-testid="transport-bar">
      <button
        className="pp"
        onClick={() => toggle()}
        data-testid="transport-toggle"
      >
        <Icon name={playing ? 'pause' : 'play'} size={11} color="var(--bg)" />
      </button>
      <span className="tc">
        {currentDisplay}
        <span className="total"> / {totalTime}</span>
      </span>
      <div
        className="scrub"
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const pct = (e.clientX - rect.left) / rect.width;
          seekPercent(pct);
        }}
        data-testid="transport-scrub"
      >
        <i style={{ width: `${scrubPercent}%` }} />
        <b style={{ left: `${scrubPercent}%` }} />
      </div>
      <span className="vol-toggle">−24 dB</span>
      <VUMeter />
      <button className="btn-icon">
        <Icon name="cog" size={13} />
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Run vitest**

Run: `cd frontend && npx vitest run src/pages/Console/`
Expected: existing Console smoke still passes once Task 1.4 wraps Workbench in provider; if it fails before Task 1.4, that's expected — proceed.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Console/TransportBar.tsx
git commit -m "feat(console): TransportBar consumes VideoControlContext (no more props)"
```

---

## Task 1.4: Wrap Workbench with VideoControlProvider + Space hotkey via context

**Files:**
- Modify: `frontend/src/pages/Console/Workbench.tsx`

- [ ] **Step 1: Read current Workbench**

Run: `cat frontend/src/pages/Console/Workbench.tsx`

Confirm shape: `selectedFile` prop, local `playing` state, useHotkeys Space toggles local state, passes `playing/onTogglePlay/totalTime` to TransportBar, passes `fileName` to VideoPanel.

- [ ] **Step 2: Replace `frontend/src/pages/Console/Workbench.tsx` entirely**

```tsx
import { PresetPills } from './PresetPills';
import { MetricsBar } from './MetricsBar';
import { VideoPanel } from './VideoPanel';
import { TransportBar } from './TransportBar';
import { TranscriptList } from './TranscriptList';
import { Icon } from '../../lib/motitle-icons';
import { useHotkeys } from '../../hooks/useHotkeys';
import { VideoControlProvider, useVideoControl } from './video-control-context';
import type { FileRecord } from '../../lib/socket-events';

export type WorkbenchProps = {
  selectedFile?: FileRecord | null;
};

// Inner component — uses the context so MUST live inside the provider.
function WorkbenchInner({ selectedFile }: WorkbenchProps) {
  const { toggle } = useVideoControl();

  useHotkeys({
    space: (e) => { e.preventDefault(); toggle(); },
  });

  const fileName =
    typeof selectedFile?.original_name === 'string'
      ? selectedFile.original_name
      : undefined;

  return (
    <section className="con-work">
      <div className="con-topbar">
        <PresetPills />
        <div className="con-actions">
          <button className="btn btn-secondary btn-sm">
            <Icon name="cog" size={11} /> 設定
          </button>
          <button className="btn btn-primary btn-sm">
            <Icon name="play" size={11} color="#fff" /> 執行佇列
          </button>
        </div>
      </div>
      <MetricsBar />
      <div className="con-stage">
        <VideoPanel fileId={selectedFile?.id ?? null} fileName={fileName} />
        <TransportBar />
        <div className="con-bottom">
          <TranscriptList fileId={selectedFile?.id ?? null} activeLang="zh" />
        </div>
      </div>
    </section>
  );
}

export function Workbench({ selectedFile = null }: WorkbenchProps) {
  return (
    <VideoControlProvider>
      <WorkbenchInner selectedFile={selectedFile ?? null} />
    </VideoControlProvider>
  );
}
```

- [ ] **Step 3: Run Console smoke test**

Run: `cd frontend && npx vitest run src/pages/Console.test.tsx`
Expected: 1 passed (the 4-columns-render smoke). If FAIL with "useVideoControl must be used inside <VideoControlProvider>", check Workbench is properly wrapping inner component.

- [ ] **Step 4: Run full vitest**

Run: `cd frontend && npx vitest run`
Expected: 278+ passed (depending on how many new context tests landed in Task 1.1 — should be 283 = 278 + 5)

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 NEW errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Console/Workbench.tsx
git commit -m "feat(console): Workbench wraps VideoControlProvider + Space hotkey via context"
```

---

## Task 1.5: Sharpen Playwright Step 14 assertion

**Files:**
- Modify: `frontend/tests-e2e/_user-workflow.spec.ts`

- [ ] **Step 1: Find Step 14 block + replace assertion**

Locate the block starting with `await test.step('14. Space toggles play` in `frontend/tests-e2e/_user-workflow.spec.ts`. Replace its entire body with:

```ts
  await test.step('14. Space toggles real video play/pause', async () => {
    if (!newFileId) {
      record('14. Space play', '— skipped', 'no file');
      return;
    }
    // Ensure focus is on body, not on inputs (useHotkeys filter)
    await page.locator('body').click();
    await page.waitForTimeout(200);

    const videoEl = page.locator('[data-testid="video-element"]');
    const beforePaused = await videoEl.evaluate((v: HTMLVideoElement) => v.paused).catch(() => null);

    await page.keyboard.press('Space');
    // play() is async — give the browser a moment to flip paused state
    await page.waitForTimeout(500);

    const afterPaused = await videoEl.evaluate((v: HTMLVideoElement) => v.paused).catch(() => null);

    if (beforePaused === true && afterPaused === false) {
      record('14. Space play', '✓ works', 'video.paused: true → false after Space');
    } else if (beforePaused === null) {
      record('14. Space play', '— skipped', 'video element not found');
    } else {
      record('14. Space play', '✗ broken', `video.paused before=${beforePaused} after=${afterPaused} (expected true→false)`);
    }
  });
```

- [ ] **Step 2: Run the workflow spec**

Run: `cd frontend && npx playwright test tests-e2e/_user-workflow.spec.ts --reporter=line`

Expected: Step 14 reports `✓ works` (was `⚠ partial` before). Other steps unchanged.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests-e2e/_user-workflow.spec.ts
git commit -m "test(console): sharpen Space play assertion to check video.paused"
```

---

# Phase 2 — Backend render socket events + WorkerStatus integration (Bug 2)

## Task 2.1: Locate render job thread + investigate existing FFmpeg progress parsing

**Files:**
- Read: `backend/renderer.py` and `backend/routes/render.py`

- [ ] **Step 1: Locate `_run_render_job` (or equivalent)**

Run: `grep -n "def _run_render_job\|FFmpeg\|ffmpeg\|subprocess\.Popen\|-progress" backend/renderer.py backend/routes/render.py | head -30`

Determine:
1. Which file has the daemon thread function — note path + function name
2. How FFmpeg progress is currently parsed (look for `-progress pipe:1` or `stderr.readline` loop)
3. Where the job dict (`job['status']`, `job['progress']`) is updated

This is exploration only — no code changes in this task. Capture the file path + line numbers for the next task's spec.

- [ ] **Step 2: Verify `/api/renders/in-progress` endpoint exists + check response shape**

Run: `grep -n "in-progress\|in_progress" backend/routes/render.py | head`

Confirm endpoint exists. Then call it locally:

```bash
curl -s -b /tmp/cookies.txt http://localhost:5001/api/renders/in-progress | python3 -m json.tool | head -20
```

Note the exact response shape — keys per render item, status field, percent field. This shape determines the frontend `RenderInProgress` type in Task 2.5.

- [ ] **Step 3: Record findings**

No commit. Findings:
- `_run_render_job` lives in `<filepath>` at line `<N>`
- FFmpeg progress parsing pattern: `<one of>: -progress pipe / stderr scan / blocking wait`
- `/api/renders/in-progress` response shape: `<JSON shape>`

These inform Tasks 2.2 and 2.5.

---

## Task 2.2: Backend `_emit_render_event` helper + render_start/progress/done emits

**Files:**
- Modify: `backend/renderer.py` OR `backend/routes/render.py` (whichever has `_run_render_job` per Task 2.1)
- Create: `backend/tests/test_render_socket.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_render_socket.py`:

```python
"""Tests for render lifecycle socket events (Bug 2 / Section 2)."""
import json
from unittest.mock import patch, MagicMock

import pytest


def test_emit_render_event_calls_socketio():
    """_emit_render_event should call app.socketio.emit with the given event + payload."""
    # Import via the actual location — adjust per Task 2.1 findings
    try:
        from renderer import _emit_render_event
    except ImportError:
        from routes.render import _emit_render_event

    fake_app = MagicMock()
    with patch.dict('sys.modules', {'app': fake_app}):
        _emit_render_event('render_start', {'render_id': 'r1', 'file_id': 'f1', 'format': 'mp4'})
    fake_app.socketio.emit.assert_called_once_with(
        'render_start',
        {'render_id': 'r1', 'file_id': 'f1', 'format': 'mp4'},
    )


def test_emit_render_event_swallows_exceptions():
    """If socketio is unavailable / throws, the helper must NOT raise."""
    try:
        from renderer import _emit_render_event
    except ImportError:
        from routes.render import _emit_render_event

    fake_app = MagicMock()
    fake_app.socketio.emit.side_effect = RuntimeError('socketio not ready')
    with patch.dict('sys.modules', {'app': fake_app}):
        # Must not raise
        _emit_render_event('render_done', {'render_id': 'r1'})


def test_emit_render_event_event_names_are_strings():
    """Spec-level assertion: callers must use the documented event names.
    
    This test exists so a typo like 'render-progress' (hyphen) vs
    'render_progress' (underscore) doesn't pass review by going unnoticed.
    """
    try:
        from renderer import _emit_render_event  # noqa: F401
        valid = True
    except ImportError:
        try:
            from routes.render import _emit_render_event  # noqa: F401
            valid = True
        except ImportError:
            valid = False
    assert valid, 'Render emit helper must be importable from renderer or routes.render'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && pytest tests/test_render_socket.py -v`
Expected: FAIL — `ImportError: cannot import name '_emit_render_event'`

- [ ] **Step 3: Add helper + 3 emit calls**

In whichever file contains `_run_render_job` (per Task 2.1), add this helper near the top after imports:

```python
def _emit_render_event(event: str, payload: dict) -> None:
    """Emit a render-lifecycle socket event. Swallows errors so the
    render thread never dies because socketio is unavailable.

    Mirrors the pattern in pipeline_runner._socketio_emit().
    """
    try:
        import app as _app
        _app.socketio.emit(event, payload)
    except Exception:
        pass
```

Then locate `_run_render_job` (or whatever the daemon thread function is named). At the entry point of the function — right after the job dict is initialized but before FFmpeg subprocess is launched — add:

```python
_emit_render_event('render_start', {
    'render_id': job_id,
    'file_id': job['file_id'],
    'format': job.get('format'),
    'output_filename': job.get('output_filename'),
})
```

Inside the existing FFmpeg progress loop (find by `for line in process.stdout` or `process.stderr.readline()` pattern), add throttled progress emit. **If progress is currently parsed by reading FFmpeg stderr line-by-line and computing percent**, add right after `job['progress'] = percent`:

```python
# Throttle: only emit when >= 5% delta from last emitted value
if not hasattr(_run_render_job, '_last_emit'):
    _run_render_job._last_emit = {}  # global dict keyed on job_id
_last = _run_render_job._last_emit.get(job_id, -5)
if percent - _last >= 5:
    _emit_render_event('render_progress', {
        'render_id': job_id,
        'file_id': job['file_id'],
        'percent': percent,
    })
    _run_render_job._last_emit[job_id] = percent
```

In the `finally:` block of the function (where `job['status']` gets its final value 'done' / 'failed' / 'cancelled'), add:

```python
_emit_render_event('render_done', {
    'render_id': job_id,
    'file_id': job['file_id'],
    'status': job['status'],
    'output_path': job.get('output_path'),
    'error': job.get('error'),
})
# Cleanup throttle dict
if hasattr(_run_render_job, '_last_emit'):
    _run_render_job._last_emit.pop(job_id, None)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_render_socket.py -v`
Expected: 3 passed

- [ ] **Step 5: Run full backend suite to confirm no regression**

Run: `cd backend && pytest -q --tb=no 2>&1 | tail -3`
Expected: 1050 PASS / 23 failed / 21 skipped (was 1047 + 3 new = 1050)

- [ ] **Step 6: Commit**

```bash
git add backend/renderer.py backend/routes/render.py backend/tests/test_render_socket.py
# (drop renderer.py from add if only routes/render.py was modified, and vice versa)
git commit -m "feat(render): emit render_start/progress/done socket events (Bug 2)"
```

---

## Task 2.3: Frontend socket reducer — render event types + state + reducer cases

**Files:**
- Modify: `frontend/src/lib/socket-events.ts`

- [ ] **Step 1: Read current socket-events.ts**

Run: `cat frontend/src/lib/socket-events.ts | head -100`

Identify:
- `SocketAction` union — where the existing case literals live
- `SocketState` interface — where to add `renderProgress` / `renderStatus`
- `socketReducer` function — where the switch statement on action.type lives

- [ ] **Step 2: Add render types + state + reducer cases**

Add these type definitions near the existing `StageProgressEvent` block in `frontend/src/lib/socket-events.ts`:

```ts
export interface RenderStartEvent {
  render_id: string;
  file_id: string;
  format?: string | null;
  output_filename?: string | null;
}

export interface RenderProgressEvent {
  render_id: string;
  file_id: string;
  percent: number;
}

export interface RenderDoneEvent {
  render_id: string;
  file_id: string;
  status: 'done' | 'failed' | 'cancelled';
  output_path?: string | null;
  error?: string | null;
}
```

Extend the `SocketAction` union with 3 new cases:

```ts
export type SocketAction =
  | { type: 'BULK_FILES'; files: FileRecord[] }
  | { type: 'FILE_ADDED'; file: FileRecord }
  | { type: 'FILE_UPDATED'; file: FileRecord }
  | { type: 'FILE_REMOVED'; file_id: string }
  | { type: 'STAGE_PROGRESS'; ev: StageProgressEvent }
  | { type: 'STAGE_COMPLETE'; ev: StageCompleteEvent }
  | { type: 'PIPELINE_COMPLETE'; ev: PipelineCompleteEvent }
  | { type: 'PIPELINE_FAILED'; ev: PipelineFailedEvent }
  | { type: 'SOCKET_CONNECTED' }
  | { type: 'SOCKET_DISCONNECTED' }
  | { type: 'RENDER_START'; ev: RenderStartEvent }
  | { type: 'RENDER_PROGRESS'; ev: RenderProgressEvent }
  | { type: 'RENDER_DONE'; ev: RenderDoneEvent };
```

Extend `SocketState` interface:

```ts
export interface SocketState {
  files: Record<string, FileRecord>;
  stageProgress: Record<string, Record<number, number>>;
  stageStatus: Record<string, Record<number, StageStatus>>;
  connected: boolean;
  // NEW (Bug 2 — render lifecycle):
  renderProgress: Record<string, number>;
  renderStatus: Record<string, 'running' | 'done' | 'failed' | 'cancelled'>;
}
```

Extend `initialSocketState`:

```ts
export const initialSocketState: SocketState = {
  files: {},
  stageProgress: {},
  stageStatus: {},
  connected: false,
  renderProgress: {},
  renderStatus: {},
};
```

Add 3 cases to the `socketReducer` switch statement (insert before the `default:` case):

```ts
    case 'RENDER_START': {
      const fid = action.ev.file_id;
      return {
        ...state,
        renderStatus: { ...state.renderStatus, [fid]: 'running' },
        renderProgress: { ...state.renderProgress, [fid]: 0 },
      };
    }
    case 'RENDER_PROGRESS': {
      const fid = action.ev.file_id;
      return {
        ...state,
        renderProgress: { ...state.renderProgress, [fid]: action.ev.percent },
      };
    }
    case 'RENDER_DONE': {
      const fid = action.ev.file_id;
      const { status } = action.ev;
      return {
        ...state,
        renderStatus: { ...state.renderStatus, [fid]: status },
        renderProgress: {
          ...state.renderProgress,
          [fid]: status === 'done' ? 100 : (state.renderProgress[fid] ?? 0),
        },
      };
    }
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 NEW errors

- [ ] **Step 4: Run existing vitest to confirm no regression on socket reducer**

Run: `cd frontend && npx vitest run src/providers/SocketProvider.test.tsx`
Expected: existing tests still pass (the type changes are additive)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/socket-events.ts
git commit -m "feat(socket): RenderStart/Progress/Done event types + reducer (Bug 2)"
```

---

## Task 2.4: Frontend reducer test cases for render events

**Files:**
- Modify: `frontend/src/providers/SocketProvider.test.tsx`

- [ ] **Step 1: Read existing test file**

Run: `grep -n "describe\|it(" frontend/src/providers/SocketProvider.test.tsx | head -20`

Note the existing test patterns used to test reducer cases (likely `socketReducer(state, action)` calls).

- [ ] **Step 2: Add render reducer test cases**

Append to `frontend/src/providers/SocketProvider.test.tsx` inside the appropriate describe block (likely `describe('socketReducer', ...)`):

```ts
  it('RENDER_START sets renderStatus running + progress 0', () => {
    const state = { ...initialSocketState };
    const next = socketReducer(state, {
      type: 'RENDER_START',
      ev: { render_id: 'r1', file_id: 'f1', format: 'mp4' },
    });
    expect(next.renderStatus['f1']).toBe('running');
    expect(next.renderProgress['f1']).toBe(0);
  });

  it('RENDER_PROGRESS updates percent (does not change status)', () => {
    const state = {
      ...initialSocketState,
      renderStatus: { f1: 'running' as const },
      renderProgress: { f1: 0 },
    };
    const next = socketReducer(state, {
      type: 'RENDER_PROGRESS',
      ev: { render_id: 'r1', file_id: 'f1', percent: 47 },
    });
    expect(next.renderStatus['f1']).toBe('running');
    expect(next.renderProgress['f1']).toBe(47);
  });

  it('RENDER_DONE with status=done sets status + progress=100', () => {
    const state = {
      ...initialSocketState,
      renderStatus: { f1: 'running' as const },
      renderProgress: { f1: 90 },
    };
    const next = socketReducer(state, {
      type: 'RENDER_DONE',
      ev: { render_id: 'r1', file_id: 'f1', status: 'done' },
    });
    expect(next.renderStatus['f1']).toBe('done');
    expect(next.renderProgress['f1']).toBe(100);
  });

  it('RENDER_DONE with status=failed preserves percent', () => {
    const state = {
      ...initialSocketState,
      renderStatus: { f1: 'running' as const },
      renderProgress: { f1: 32 },
    };
    const next = socketReducer(state, {
      type: 'RENDER_DONE',
      ev: { render_id: 'r1', file_id: 'f1', status: 'failed', error: 'oom' },
    });
    expect(next.renderStatus['f1']).toBe('failed');
    expect(next.renderProgress['f1']).toBe(32);
  });
```

Ensure the imports include `initialSocketState`, `socketReducer`. Add the import if missing:

```ts
import { initialSocketState, socketReducer } from '../lib/socket-events';
```

- [ ] **Step 3: Run tests**

Run: `cd frontend && npx vitest run src/providers/SocketProvider.test.tsx`
Expected: existing tests + 4 new render tests all pass

- [ ] **Step 4: Commit**

```bash
git add frontend/src/providers/SocketProvider.test.tsx
git commit -m "test(socket): cover RENDER_START/PROGRESS/DONE reducer cases"
```

---

## Task 2.5: SocketProvider listens to render socket events

**Files:**
- Modify: `frontend/src/providers/SocketProvider.tsx`

- [ ] **Step 1: Read current provider**

Run: `cat frontend/src/providers/SocketProvider.tsx | head -100`

Locate the `useEffect` that calls `io({path: '/socket.io'})` and sets up `socket.on(...)` listeners.

- [ ] **Step 2: Add 3 listeners**

In `frontend/src/providers/SocketProvider.tsx`, inside the `useEffect` that sets up socket listeners, find the existing `socket.on('pipeline_stage_progress', ...)` block and add 3 new listeners adjacent:

```tsx
    socket.on('render_start', (ev: RenderStartEvent) => {
      dispatch({ type: 'RENDER_START', ev });
    });
    socket.on('render_progress', (ev: RenderProgressEvent) => {
      dispatch({ type: 'RENDER_PROGRESS', ev });
    });
    socket.on('render_done', (ev: RenderDoneEvent) => {
      dispatch({ type: 'RENDER_DONE', ev });
    });
```

Ensure imports at the top include:

```ts
import type {
  RenderStartEvent,
  RenderProgressEvent,
  RenderDoneEvent,
} from '../lib/socket-events';
```

In the cleanup function (return statement of the useEffect), add corresponding `socket.off('render_start')` etc. if the pattern follows the existing listener cleanups.

- [ ] **Step 3: Typecheck + vitest**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: 0 NEW TS errors; vitest unchanged (provider listeners don't have direct unit tests)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/providers/SocketProvider.tsx
git commit -m "feat(socket): listen for render_start/progress/done events"
```

---

## Task 2.6: deriveStageCells position 3 (Render) wired to renderStatus

**Files:**
- Modify: `frontend/src/pages/Console/derive-stage-cells.ts`
- Modify: `frontend/src/pages/Console/derive-stage-cells.test.ts`

- [ ] **Step 1: Read current derive-stage-cells.ts**

Run: `cat frontend/src/pages/Console/derive-stage-cells.ts`

Note the current `DeriveInput` type + the position 3 (Render) block which is currently commented `// MVP: stays idle`.

- [ ] **Step 2: Write failing tests**

Append to `frontend/src/pages/Console/derive-stage-cells.test.ts`:

```ts
  it('Render cell warn when renderStatus=running with percent', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      fileId: 'f1',
      renderStatus: { f1: 'running' },
      renderProgress: { f1: 42 },
    });
    expect(cells[3]).toEqual({ state: 'warn', percent: 42 });
  });

  it('Render cell done when renderStatus=done', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      fileId: 'f1',
      renderStatus: { f1: 'done' },
      renderProgress: { f1: 100 },
    });
    expect(cells[3].state).toBe('done');
  });

  it('Render cell err when renderStatus=failed', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      fileId: 'f1',
      renderStatus: { f1: 'failed' },
      renderProgress: { f1: 30 },
    });
    expect(cells[3].state).toBe('err');
  });

  it('Render cell err when renderStatus=cancelled', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      fileId: 'f1',
      renderStatus: { f1: 'cancelled' },
      renderProgress: { f1: 50 },
    });
    expect(cells[3].state).toBe('err');
  });

  it('Render cell stays idle when no render started', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      fileId: 'f1',
      renderStatus: {},
      renderProgress: {},
    });
    expect(cells[3].state).toBe('idle');
  });
```

- [ ] **Step 3: Run tests to verify FAIL**

Run: `cd frontend && npx vitest run src/pages/Console/derive-stage-cells.test.ts`
Expected: 5 new tests FAIL — `Property 'fileId' does not exist on DeriveInput` or runtime undefined access.

- [ ] **Step 4: Update derive-stage-cells.ts**

In `frontend/src/pages/Console/derive-stage-cells.ts`, extend `DeriveInput`:

```ts
type DeriveInput = {
  status: FileRecord['status'];
  stage_outputs: Array<{ stage_type: string; stage_ref: string }>;
  approved_count: number;
  segment_count: number;
  stageProgressMap: StageProgressMap;
  // NEW (Bug 2):
  fileId?: string;
  renderStatus?: Record<string, 'running' | 'done' | 'failed' | 'cancelled'>;
  renderProgress?: Record<string, number>;
};
```

Replace the position 3 comment-only block with real logic:

```ts
  // Position 3 — Render (Bug 2: wired to render socket events)
  if (input.fileId) {
    const rStatus = input.renderStatus?.[input.fileId];
    const rPercent = input.renderProgress?.[input.fileId];
    if (rStatus === 'failed' || rStatus === 'cancelled') {
      cells[3] = { state: 'err' };
    } else if (rStatus === 'done') {
      cells[3] = { state: 'done' };
    } else if (rStatus === 'running') {
      cells[3] = { state: 'warn', percent: rPercent ?? 0 };
    }
  }
```

- [ ] **Step 5: Run tests to verify PASS**

Run: `cd frontend && npx vitest run src/pages/Console/derive-stage-cells.test.ts`
Expected: 11 PASS (6 original + 5 new)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Console/derive-stage-cells.ts \
        frontend/src/pages/Console/derive-stage-cells.test.ts
git commit -m "feat(console): deriveStageCells position 3 wired to renderStatus (Bug 2)"
```

---

## Task 2.7: to-console-file forwards renderStatus + renderProgress + fileId

**Files:**
- Modify: `frontend/src/pages/Console/to-console-file.ts`

- [ ] **Step 1: Read current implementation**

Run: `cat frontend/src/pages/Console/to-console-file.ts`

- [ ] **Step 2: Extend signature to accept render maps**

Replace `frontend/src/pages/Console/to-console-file.ts` entirely:

```ts
import { formatDuration, formatBytes, formatRelativeTime } from '../../lib/format';
import { deriveStageCells } from './derive-stage-cells';
import type { StageProgressMap } from './derive-stage-cells';
import type { FileRecord } from '../../lib/socket-events';
import type { ConsoleFile } from './types';

export function toConsoleFile(
  file: FileRecord,
  stageProgressMap: StageProgressMap,
  options?: {
    renderStatus?: Record<string, 'running' | 'done' | 'failed' | 'cancelled'>;
    renderProgress?: Record<string, number>;
    nowSeconds?: number;
  },
): ConsoleFile {
  const ext = (file.original_name.match(/\.([^.]+)$/)?.[1] ?? '').toUpperCase();
  return {
    id: file.id,
    name: file.original_name,
    ext: ext || '?',
    durationSeconds: file.duration_seconds ?? null,
    formattedDuration: formatDuration(file.duration_seconds ?? null),
    formattedSize: typeof file.size === 'number' ? formatBytes(file.size) : '—',
    formattedUploaded: typeof file.uploaded_at === 'number'
      ? formatRelativeTime(file.uploaded_at, options?.nowSeconds)
      : '—',
    stageCells: deriveStageCells({
      status: file.status,
      stage_outputs: file.stage_outputs ?? [],
      approved_count: typeof file.approved_count === 'number' ? file.approved_count : 0,
      segment_count: typeof file.segment_count === 'number' ? file.segment_count : 0,
      stageProgressMap,
      fileId: file.id,
      renderStatus: options?.renderStatus,
      renderProgress: options?.renderProgress,
    }),
    errored: file.status === 'failed',
  };
}
```

- [ ] **Step 3: Update QueueColumn to pass render maps**

Edit `frontend/src/pages/Console/QueueColumn.tsx`. Find the `consoleFiles` useMemo and update the `toConsoleFile` call:

```tsx
  const consoleFiles: ConsoleFile[] = useMemo(() => {
    const fileEntries = Object.values(state.files ?? {});
    return fileEntries.map(f =>
      toConsoleFile(f as FileRecord, (state as any).stageProgress?.[(f as any).id] ?? {}, {
        renderStatus: state.renderStatus,
        renderProgress: state.renderProgress,
      })
    );
  }, [state]);
```

- [ ] **Step 4: Run vitest**

Run: `cd frontend && npx vitest run`
Expected: 282+ PASS (no regression; existing toConsoleFile.test.ts may have used the old 3-arg signature — update if so)

If `to-console-file.test.ts` tests break: update the test calls to use the new options-object signature.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Console/to-console-file.ts \
        frontend/src/pages/Console/QueueColumn.tsx
git commit -m "feat(console): toConsoleFile forwards renderStatus/renderProgress maps"
```

---

## Task 2.8: useWorkerStatus parallel-fetch /api/renders/in-progress + merge

**Files:**
- Modify: `frontend/src/hooks/useWorkerStatus.ts`
- Modify: `frontend/src/hooks/useWorkerStatus.test.ts`

- [ ] **Step 1: Write failing test for merge behavior**

Append to `frontend/src/hooks/useWorkerStatus.test.ts`:

```ts
  it('merges /api/renders/in-progress into activeJobs as type=render', async () => {
    // Two parallel mockable URL handlers
    vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
      const u = typeof url === 'string' ? url : url.toString();
      if (u.includes('/api/queue')) {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 'j1', file_id: 'f1', status: 'running', position: 0, file_name: 'a.mp4', owner_username: 'u', eta_seconds: null, type: 'pipeline_run', created_at: 1 },
          ],
        } as Response);
      }
      if (u.includes('/api/renders/in-progress')) {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 'r1', file_id: 'f2', file_name: 'b.mp4', status: 'running', percent: 47, format: 'mp4', started_at: 2 },
          ],
        } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => [] } as Response);
    });

    const { result } = renderHook(() => useWorkerStatus());
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.activeJobs).toHaveLength(2);
    const renderJob = result.current.activeJobs.find(j => j.type === 'render');
    expect(renderJob).toBeDefined();
    expect(renderJob?.file_id).toBe('f2');
    expect(renderJob?.file_name).toBe('b.mp4');
  });

  it('continues working if /api/renders/in-progress 404s', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
      const u = typeof url === 'string' ? url : url.toString();
      if (u.includes('/api/queue')) {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 'j1', file_id: 'f1', status: 'running', position: 0, file_name: 'a.mp4', owner_username: 'u', eta_seconds: null, type: 'pipeline_run', created_at: 1 },
          ],
        } as Response);
      }
      // Render endpoint fails
      return Promise.reject(new Error('404'));
    });

    const { result } = renderHook(() => useWorkerStatus());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.activeJobs).toHaveLength(1);
    expect(result.current.activeJobs[0]?.type).toBe('pipeline_run');
  });
```

- [ ] **Step 2: Run to verify FAIL**

Run: `cd frontend && npx vitest run src/hooks/useWorkerStatus.test.ts`
Expected: 2 new tests FAIL (current hook only fetches /api/queue)

- [ ] **Step 3: Update useWorkerStatus.ts**

Locate the `refresh` callback in `frontend/src/hooks/useWorkerStatus.ts`. Replace its body to do parallel fetch + merge:

```ts
  const refresh = useCallback(async () => {
    try {
      const [queueResp, rendersResp] = await Promise.all([
        fetch('/api/queue', { credentials: 'include' }),
        fetch('/api/renders/in-progress', { credentials: 'include' }).catch(() => null),
      ]);

      if (!queueResp.ok) throw new Error(`${queueResp.status}`);
      const queue: QueueItem[] = await queueResp.json();

      // Renders endpoint shape is { id, file_id, file_name, status, percent, format, started_at }
      // (per CLAUDE.md). Map to QueueItem for unified rendering.
      type RenderInProgress = {
        id: string;
        file_id: string;
        file_name: string | null;
        status: 'running';
        percent: number;
        format: string;
        started_at: number;
      };
      let renders: RenderInProgress[] = [];
      if (rendersResp && rendersResp.ok) {
        renders = await rendersResp.json().catch(() => [] as RenderInProgress[]);
      }
      const renderItems: QueueItem[] = renders.map((r, i) => ({
        id: r.id,
        file_id: r.file_id,
        file_name: r.file_name,
        owner_username: '—',
        status: 'running',
        position: queue.length + i,
        eta_seconds: null,
        type: 'render',
        created_at: r.started_at,
      }));

      setItems([...queue, ...renderItems]);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run src/hooks/useWorkerStatus.test.ts`
Expected: 4 PASS (2 original + 2 new)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useWorkerStatus.ts frontend/src/hooks/useWorkerStatus.test.ts
git commit -m "feat(console): useWorkerStatus merges /api/renders/in-progress (Bug 2)"
```

---

## Task 2.9: WorkerStatus stage-tag mapping for type=render

**Files:**
- Modify: `frontend/src/pages/Console/WorkerStatus.tsx`

- [ ] **Step 1: Read current component**

Run: `grep -n "stage\|j\.type\|燒字" frontend/src/pages/Console/WorkerStatus.tsx | head`

Locate where `j.type` is rendered as the stage tag in the active card.

- [ ] **Step 2: Add tag-friendly mapping**

In `frontend/src/pages/Console/WorkerStatus.tsx`, add a small helper near the top:

```tsx
function stageTagLabel(type: string): string {
  if (type === 'render') return '燒字';
  if (type === 'pipeline_run') return 'pipeline';
  return type;
}
```

Find the `<span className="stage">{j.type}</span>` line and replace with:

```tsx
              <span className="stage">{stageTagLabel(j.type)}</span>
```

- [ ] **Step 3: Smoke test**

Run: `cd frontend && npx vitest run src/pages/Console/`
Expected: existing tests pass

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Console/WorkerStatus.tsx
git commit -m "feat(console): friendly stage-tag mapping (render → 燒字)"
```

---

# Phase 3 — 4-state stage lifecycle (Bug 3)

## Task 3.1: types.ts — add queued + starting enum literals

**Files:**
- Modify: `frontend/src/pages/Console/types.ts`

- [ ] **Step 1: Read current types**

Run: `cat frontend/src/pages/Console/types.ts`

- [ ] **Step 2: Extend ConsoleStageCellState union**

In `frontend/src/pages/Console/types.ts`, change:

```ts
export type ConsoleStageCellState = 'idle' | 'done' | 'warn' | 'err';
```

to:

```ts
export type ConsoleStageCellState =
  | 'idle'      // never ran
  | 'queued'    // job in queue, worker not started — pulse animation
  | 'starting'  // pipeline_stage_start fired, no progress yet — pulse + faint fill hint
  | 'warn'      // running with percent > 0 — solid fill
  | 'done'      // pipeline_stage_done with status='done', or percent === 100
  | 'err';      // pipeline_stage_done with status='failed', or file.status='failed'
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 NEW errors (the additional literals are accepted in any place that took the union)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Console/types.ts
git commit -m "feat(console): add 'queued' + 'starting' to ConsoleStageCellState (Bug 3)"
```

---

## Task 3.2: socket-events.ts — stagePhase field + STAGE_START action + reducer transitions

**Files:**
- Modify: `frontend/src/lib/socket-events.ts`
- Modify: `frontend/src/providers/SocketProvider.test.tsx`

- [ ] **Step 1: Write failing tests**

Append to `frontend/src/providers/SocketProvider.test.tsx`:

```ts
  it('STAGE_START sets stagePhase[fid][idx]=starting', () => {
    const state = { ...initialSocketState };
    const next = socketReducer(state, {
      type: 'STAGE_START',
      ev: { file_id: 'f1', stage_index: 0, stage_type: 'asr_primary' },
    });
    expect(next.stagePhase['f1']?.[0]).toBe('starting');
  });

  it('STAGE_PROGRESS with percent>0 sets stagePhase to running', () => {
    const state = {
      ...initialSocketState,
      stagePhase: { f1: { 0: 'starting' as const } },
    };
    const next = socketReducer(state, {
      type: 'STAGE_PROGRESS',
      ev: { file_id: 'f1', stage_index: 0, percent: 15 },
    });
    expect(next.stagePhase['f1']?.[0]).toBe('running');
  });

  it('FILE_ADDED with status=queued sets stagePhase[fid][0]=queued', () => {
    const state = { ...initialSocketState };
    const next = socketReducer(state, {
      type: 'FILE_ADDED',
      file: {
        id: 'f1', original_name: 'a.mp4', status: 'queued',
        pipeline_id: 'p1',
      } as any,
    });
    expect(next.stagePhase['f1']?.[0]).toBe('queued');
  });

  it('FILE_REMOVED clears stagePhase[fid]', () => {
    const state = {
      ...initialSocketState,
      stagePhase: { f1: { 0: 'running' as const, 1: 'queued' as const } },
    };
    const next = socketReducer(state, { type: 'FILE_REMOVED', file_id: 'f1' });
    expect(next.stagePhase['f1']).toBeUndefined();
  });
```

Also ensure `StageStartEvent` is imported / defined for the test.

- [ ] **Step 2: Run to verify FAIL**

Run: `cd frontend && npx vitest run src/providers/SocketProvider.test.tsx`
Expected: 4 new tests FAIL (no STAGE_START in union, no stagePhase field)

- [ ] **Step 3: Update socket-events.ts**

In `frontend/src/lib/socket-events.ts`:

3a. Add the new event type near `StageProgressEvent`:

```ts
export interface StageStartEvent {
  file_id: string;
  stage_index: number;
  stage_type: string;
  stage_ref?: string;
}
```

3b. Extend the `SocketAction` union:

```ts
  | { type: 'STAGE_START'; ev: StageStartEvent }
```

3c. Extend `SocketState`:

```ts
  stagePhase: Record<string, Record<number, 'queued' | 'starting' | 'running'>>;
```

3d. Extend `initialSocketState`:

```ts
  stagePhase: {},
```

3e. Update reducer:

- In the `FILE_ADDED` case, after the existing `files` update, add:

```ts
      const next: SocketState = { ...state, files: { ...state.files, [action.file.id]: action.file } };
      // Bug 3: New uploads with queued/uploaded status get cell-level pulse.
      const isPending = action.file.status === 'queued' || action.file.status === 'uploaded';
      if (isPending && action.file.pipeline_id) {
        next.stagePhase = {
          ...state.stagePhase,
          [action.file.id]: { 0: 'queued' },
        };
      }
      return next;
```

  (Adapt to whatever the existing case structure is — replace just the return value to also include stagePhase update when applicable.)

- Add a new case `STAGE_START`:

```ts
    case 'STAGE_START': {
      const { file_id, stage_index } = action.ev;
      const prev = state.stagePhase[file_id] ?? {};
      return {
        ...state,
        stagePhase: {
          ...state.stagePhase,
          [file_id]: { ...prev, [stage_index]: 'starting' },
        },
      };
    }
```

- Modify the existing `STAGE_PROGRESS` case to also set `stagePhase[file_id][stage_index] = 'running'` when percent > 0:

```ts
    case 'STAGE_PROGRESS': {
      const { file_id, stage_index, percent } = action.ev;
      const prevProg = state.stageProgress[file_id] ?? {};
      const prevPhase = state.stagePhase[file_id] ?? {};
      return {
        ...state,
        stageProgress: {
          ...state.stageProgress,
          [file_id]: { ...prevProg, [stage_index]: percent },
        },
        stagePhase: percent > 0
          ? { ...state.stagePhase, [file_id]: { ...prevPhase, [stage_index]: 'running' } }
          : state.stagePhase,
      };
    }
```

- Modify `FILE_REMOVED` to also clear stagePhase:

```ts
    case 'FILE_REMOVED': {
      const { [action.file_id]: _f, ...filesRest } = state.files;
      const { [action.file_id]: _p, ...progRest } = state.stageProgress;
      const { [action.file_id]: _s, ...statusRest } = state.stageStatus;
      const { [action.file_id]: _ph, ...phaseRest } = state.stagePhase;
      return {
        ...state,
        files: filesRest,
        stageProgress: progRest,
        stageStatus: statusRest,
        stagePhase: phaseRest,
      };
    }
```

(Adapt to existing case structure — the key point: clear the matching entry from `stagePhase` in addition to whatever else is cleared.)

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run src/providers/SocketProvider.test.tsx`
Expected: 4 new + existing tests all pass

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/socket-events.ts frontend/src/providers/SocketProvider.test.tsx
git commit -m "feat(socket): stagePhase reducer field + STAGE_START action (Bug 3)"
```

---

## Task 3.3: SocketProvider listens for pipeline_stage_start

**Files:**
- Modify: `frontend/src/providers/SocketProvider.tsx`

- [ ] **Step 1: Find existing stage listener**

Run: `grep -n "pipeline_stage_progress\|pipeline_stage_complete\|pipeline_stage_start" frontend/src/providers/SocketProvider.tsx`

- [ ] **Step 2: Add stage_start listener**

In `frontend/src/providers/SocketProvider.tsx`, near the existing `socket.on('pipeline_stage_progress', ...)`, add:

```tsx
    socket.on('pipeline_stage_start', (ev: StageStartEvent) => {
      dispatch({ type: 'STAGE_START', ev });
    });
```

Ensure import:

```ts
import type { StageStartEvent } from '../lib/socket-events';
```

Add cleanup in the useEffect return statement to match the existing pattern:

```tsx
      socket.off('pipeline_stage_start');
```

- [ ] **Step 3: Typecheck + vitest**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: 0 NEW TS errors, all tests pass

- [ ] **Step 4: Commit**

```bash
git add frontend/src/providers/SocketProvider.tsx
git commit -m "feat(socket): listen for pipeline_stage_start (Bug 3)"
```

---

## Task 3.4: deriveStageCells lifecycle-aware helper

**Files:**
- Modify: `frontend/src/pages/Console/derive-stage-cells.ts`
- Modify: `frontend/src/pages/Console/derive-stage-cells.test.ts`

- [ ] **Step 1: Write failing tests**

Append to `frontend/src/pages/Console/derive-stage-cells.test.ts`:

```ts
  it('queued phase → state queued', () => {
    const cells = deriveStageCells({
      status: 'queued',
      stage_outputs: [{ stage_type: 'asr', stage_ref: 'mlx' }],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      stagePhaseMap: { 0: 'queued' },
    });
    expect(cells[0].state).toBe('queued');
  });

  it('starting phase → state starting', () => {
    const cells = deriveStageCells({
      status: 'transcribing',
      stage_outputs: [{ stage_type: 'asr', stage_ref: 'mlx' }],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      stagePhaseMap: { 0: 'starting' },
    });
    expect(cells[0].state).toBe('starting');
  });

  it('running phase with percent=47 → warn 47', () => {
    const cells = deriveStageCells({
      status: 'transcribing',
      stage_outputs: [{ stage_type: 'asr', stage_ref: 'mlx' }],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: { 0: { percent: 47, status: 'running' } },
      stagePhaseMap: { 0: 'running' },
    });
    expect(cells[0]).toEqual({ state: 'warn', percent: 47 });
  });

  it('phase missing + prog.status running → falls through to warn', () => {
    const cells = deriveStageCells({
      status: 'transcribing',
      stage_outputs: [{ stage_type: 'asr', stage_ref: 'mlx' }],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: { 0: { percent: 22, status: 'running' } },
      stagePhaseMap: {},
    });
    expect(cells[0].state).toBe('warn');
  });

  it('prog.status=failed short-circuits regardless of phase', () => {
    const cells = deriveStageCells({
      status: 'failed',
      stage_outputs: [{ stage_type: 'asr', stage_ref: 'mlx' }],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: { 0: { percent: 30, status: 'failed' } },
      stagePhaseMap: { 0: 'starting' },
    });
    expect(cells[0].state).toBe('err');
  });

  it('phase clears (undefined) → falls through to idle when no prog', () => {
    const cells = deriveStageCells({
      status: 'uploaded',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      stagePhaseMap: {},
    });
    expect(cells[0].state).toBe('idle');
  });
```

- [ ] **Step 2: Run to verify FAIL**

Run: `cd frontend && npx vitest run src/pages/Console/derive-stage-cells.test.ts`
Expected: 6 new tests FAIL — `Property 'stagePhaseMap' does not exist on DeriveInput`

- [ ] **Step 3: Update derive-stage-cells.ts**

In `frontend/src/pages/Console/derive-stage-cells.ts`:

3a. Extend `DeriveInput`:

```ts
export type StagePhase = 'queued' | 'starting' | 'running';
export type StagePhaseMap = Record<number, StagePhase | undefined>;

type DeriveInput = {
  status: FileRecord['status'];
  stage_outputs: Array<{ stage_type: string; stage_ref: string }>;
  approved_count: number;
  segment_count: number;
  stageProgressMap: StageProgressMap;
  stagePhaseMap?: StagePhaseMap;
  fileId?: string;
  renderStatus?: Record<string, 'running' | 'done' | 'failed' | 'cancelled'>;
  renderProgress?: Record<string, number>;
};
```

3b. Refactor `deriveCellFromProgress` to a lifecycle-aware helper that takes both progress and phase:

```ts
function deriveLifecycleCell(
  prog: StageProgressEntry | undefined,
  phase: StagePhase | undefined,
): ConsoleStageCell {
  // Terminal states first
  if (prog?.status === 'failed') return { state: 'err' };
  if (prog?.status === 'done' || prog?.percent === 100) return { state: 'done' };

  // Phase trumps absence of progress
  if (phase === 'queued') return { state: 'queued' };
  if (phase === 'starting') return { state: 'starting' };
  if (phase === 'running') {
    return { state: 'warn', percent: prog?.percent ?? 0 };
  }
  // Legacy fallback for files seen via BULK_FILES without phase info
  if (prog?.status === 'running') return { state: 'warn', percent: prog.percent };
  return { state: 'idle' };
}
```

3c. Update position 0 and 1 logic to use the new helper + stagePhaseMap lookup:

```ts
  // Position 0 — ASR
  const asrStageIdx = input.stage_outputs.findIndex(s => classifyStage(s.stage_type) === 'asr');
  if (asrStageIdx >= 0) {
    cells[0] = deriveLifecycleCell(
      input.stageProgressMap[asrStageIdx],
      input.stagePhaseMap?.[asrStageIdx],
    );
  } else if (input.stagePhaseMap?.[0]) {
    // File enqueued before stage_outputs is populated — still show queued
    cells[0] = deriveLifecycleCell(undefined, input.stagePhaseMap[0]);
  }

  // Position 1 — MT
  const mtStageIdx = input.stage_outputs.findIndex(s => classifyStage(s.stage_type) === 'mt');
  if (mtStageIdx >= 0) {
    cells[1] = deriveLifecycleCell(
      input.stageProgressMap[mtStageIdx],
      input.stagePhaseMap?.[mtStageIdx],
    );
  }
```

3d. Remove or leave the existing `deriveCellFromProgress` function — if unused after refactor, delete; if other callers remain (none expected), keep.

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run src/pages/Console/derive-stage-cells.test.ts`
Expected: 17 PASS (11 prior + 6 new lifecycle)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Console/derive-stage-cells.ts \
        frontend/src/pages/Console/derive-stage-cells.test.ts
git commit -m "feat(console): lifecycle-aware deriveStageCells with queued+starting (Bug 3)"
```

---

## Task 3.5: to-console-file forwards stagePhaseMap

**Files:**
- Modify: `frontend/src/pages/Console/to-console-file.ts`
- Modify: `frontend/src/pages/Console/QueueColumn.tsx`

- [ ] **Step 1: Update to-console-file.ts**

Edit `frontend/src/pages/Console/to-console-file.ts` to accept and forward stagePhaseMap. Modify the `options` parameter:

```ts
export function toConsoleFile(
  file: FileRecord,
  stageProgressMap: StageProgressMap,
  options?: {
    stagePhaseMap?: import('./derive-stage-cells').StagePhaseMap;
    renderStatus?: Record<string, 'running' | 'done' | 'failed' | 'cancelled'>;
    renderProgress?: Record<string, number>;
    nowSeconds?: number;
  },
): ConsoleFile {
  // ... existing code ...
    stageCells: deriveStageCells({
      // ... existing fields ...
      stagePhaseMap: options?.stagePhaseMap,
      fileId: file.id,
      renderStatus: options?.renderStatus,
      renderProgress: options?.renderProgress,
    }),
```

- [ ] **Step 2: Update QueueColumn.tsx**

Update the `toConsoleFile` call inside `consoleFiles` useMemo:

```tsx
  const consoleFiles: ConsoleFile[] = useMemo(() => {
    const fileEntries = Object.values(state.files ?? {});
    return fileEntries.map(f =>
      toConsoleFile(f as FileRecord, (state as any).stageProgress?.[(f as any).id] ?? {}, {
        stagePhaseMap: state.stagePhase?.[(f as any).id] ?? {},
        renderStatus: state.renderStatus,
        renderProgress: state.renderProgress,
      })
    );
  }, [state]);
```

- [ ] **Step 3: Run vitest**

Run: `cd frontend && npx vitest run`
Expected: all tests pass (282+ depending on prior count)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Console/to-console-file.ts frontend/src/pages/Console/QueueColumn.tsx
git commit -m "feat(console): toConsoleFile + QueueColumn forward stagePhaseMap (Bug 3)"
```

---

## Task 3.6: console.css pulse keyframes + queued/starting cell selectors

**Files:**
- Modify: `frontend/src/styles/console.css`

- [ ] **Step 1: Locate existing stage bar CSS**

Run: `grep -n "\.con-q-stages\|@keyframes\|r-dot--pulse" frontend/src/styles/console.css | head`

- [ ] **Step 2: Append keyframe + 2 selector rules**

In `frontend/src/styles/console.css`, after the existing `.con-q-stages i.err` rule (which marks the end of stage cell variants), append:

```css

/* Bug 3 — lifecycle pulse animation for queued + starting cells.
 * Same cadence as r-dot--pulse for visual coherence. */
@keyframes con-cell-pulse {
  0%, 100% { opacity: 0.4; }
  50%      { opacity: 1; }
}
.con-q-stages i.queued {
  background: var(--accent-soft);
  animation: con-cell-pulse 1.4s ease-in-out infinite;
}
.con-q-stages i.starting {
  background: linear-gradient(90deg, var(--warning) 5%, var(--surface-3) 5%);
  animation: con-cell-pulse 1.4s ease-in-out infinite;
}
```

- [ ] **Step 3: No unit test for CSS — manually verify in browser**

This step is documentation-only:
1. Restart dev server: `cd frontend && npm run dev`
2. Open `http://localhost:5173/console?console=1` (logged in)
3. Drop a file — the ASR cell should pulse (alternating opacity 0.4 ↔ 1) while waiting for pipeline_stage_start
4. When pipeline_stage_start fires — ASR cell transitions to `starting` (pulsing + faint yellow 5% fill)
5. When first pipeline_stage_progress event arrives — cell transitions to `warn` (solid yellow fill, percent-driven width)

If visual verification fails, check:
- The keyframe is registered (no typo in `@keyframes con-cell-pulse`)
- The selectors `.con-q-stages i.queued` and `.con-q-stages i.starting` are reachable (`StageBar.tsx` renders `<i className={c.state}>`, so `c.state === 'queued'` produces `<i class="queued">`)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/styles/console.css
git commit -m "feat(console): pulse animation for queued + starting stage cells (Bug 3)"
```

---

## Task 3.7: Sharpen Playwright Step 12 assertion

**Files:**
- Modify: `frontend/tests-e2e/_user-workflow.spec.ts`

- [ ] **Step 1: Find Step 12 block**

Locate the block starting with `await test.step('12. Stage bar reflects pipeline state',` in `frontend/tests-e2e/_user-workflow.spec.ts`.

- [ ] **Step 2: Replace with sharpened assertion**

Replace the entire Step 12 body:

```ts
  await test.step('12. Stage bar shows queued/starting/warn (not idle) shortly after enqueue', async () => {
    if (!newFileId) {
      record('12. Stage bar update', '— skipped', 'no file');
      return;
    }
    const cells = page.locator(`[data-testid="queue-item-${newFileId}"] [data-testid="queue-stage-bar"] i`);

    // Within 2 seconds, the first cell should be NOT idle (queued, starting, or warn).
    // Allows for pipeline_stage_start latency.
    await expect.poll(
      async () => {
        const cls = await cells.nth(0).getAttribute('class');
        return cls ?? '';
      },
      { timeout: 5_000 }
    ).not.toMatch(/^idle$/);

    const cls = await cells.nth(0).getAttribute('class');
    if (cls === 'queued' || cls === 'starting' || cls === 'warn') {
      record('12. Stage bar update', '✓ works', `cell 0 class="${cls}" within 5s of enqueue`);
    } else if (cls === 'err') {
      record('12. Stage bar update', '⚠ partial', `cell 0 went to err (pipeline failed)`);
    } else if (cls === 'done') {
      record('12. Stage bar update', '✓ works', `cell 0 went to done (pipeline was fast)`);
    } else {
      record('12. Stage bar update', '✗ broken', `unexpected cell 0 class: "${cls}"`);
    }
  });
```

- [ ] **Step 3: Run workflow spec**

Run: `cd frontend && npx playwright test tests-e2e/_user-workflow.spec.ts --reporter=line`
Expected: Step 12 reports `✓ works` (within 5s of enqueue, cell 0 is queued/starting/warn — not idle).

- [ ] **Step 4: Commit**

```bash
git add frontend/tests-e2e/_user-workflow.spec.ts
git commit -m "test(console): sharpen Step 12 to assert non-idle within 5s of enqueue"
```

---

# Phase 4 — Final verification

## Task 4.1: Full vitest no-regression check

- [ ] **Step 1: Run full vitest**

Run: `cd frontend && npx vitest run 2>&1 | grep -E "Test Files|Tests "`
Expected: All passing (294 = 278 + 5 video context + 4 reducer render + 5 derive render + 6 derive lifecycle + 4 reducer phase + 2 useWorkerStatus merge − any adjustments)

If any test fails: read the failure, fix at minimum scope (don't over-refactor), re-run.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 NEW errors (6 pre-existing `tests-e2e/v6-pipeline-smoke.spec.ts` errors unchanged)

- [ ] **Step 3: No commit needed (verification step only)**

---

## Task 4.2: Full backend pytest no-regression check

- [ ] **Step 1: Run full backend**

Run: `cd backend && source venv/bin/activate && pytest -q --tb=no 2>&1 | tail -3`
Expected: 1050 PASS / 23 failed (baseline) / 21 skipped

- [ ] **Step 2: No commit needed**

---

## Task 4.3: Full Playwright no-regression check

- [ ] **Step 1: Run all Console specs**

```bash
cd frontend && npx playwright test tests-e2e/console.spec.ts tests-e2e/dashboard.spec.ts tests-e2e/bold-dashboard.spec.ts --reporter=line
```
Expected: all passing (Console 9 + 1 skipped, Dashboard suites green — regression baseline preserved)

- [ ] **Step 2: Run user-workflow spec (manual local)**

```bash
cd frontend && npx playwright test tests-e2e/_user-workflow.spec.ts --reporter=line
```
Expected: 16/16 work (previously 13/16); Step 12 + 14 newly `✓ works`. Step 15 (Render cell) should be `✓ works` IF a real render is triggered during the test — currently it's not, so may stay `⚠ partial`. That's acceptable.

- [ ] **Step 3: No commit needed**

---

## Task 4.4: Update CONSOLE_REDESIGN.md known limitations

**Files:**
- Modify: `docs/CONSOLE_REDESIGN.md`

- [ ] **Step 1: Read current known-limitations section**

Run: `grep -n "Known limitations\|MVP\|Space play\|Render cell\|Stage bar" docs/CONSOLE_REDESIGN.md`

- [ ] **Step 2: Strike through resolved entries**

In `docs/CONSOLE_REDESIGN.md` Known Limitations section, mark these resolved:

```markdown
- ~~VideoPanel: no real `<video>` element yet; uses placeholder safe-grid.~~ ✅ wired in commit 775b1ed
- ~~TranscriptList: read-only, no edit, single-column (sourceLang only — hook returns `{start, end, text}` shape).~~ — still a limitation
- ~~⌘K Global search: placeholder modal, no actual search wiring.~~ — still a limitation
- ~~Render position (4th stage cell) always idle — needs cross-file `useActiveRenders()` hook.~~ ✅ wired via render socket events (Bug 2)
- ~~Pipelines page has preset_slot dropdown for CREATE only — no EDIT flow yet.~~ — still a limitation
- ~~Mobile fallback at `<1024px` redirects to `/` (Console is desktop-only per spec).~~ — by design

Add a new line summarizing what's resolved:
- Space play actually controls `<video>` via VideoControlContext (Bug 1, design 2026-05-22)
- Render lifecycle wired via `render_*` socket events; 4th stage cell + WorkerStatus reflect live state (Bug 2)
- Stage bar shows pulsing `queued` immediately on enqueue + `starting` on pipeline_stage_start (Bug 3, no 8s grey-idle window)
```

- [ ] **Step 3: Commit**

```bash
git add docs/CONSOLE_REDESIGN.md
git commit -m "docs(console): mark Bug 1+2+3 resolved in known limitations"
```

---

## Task 4.5: Final summary commit + cleanup

- [ ] **Step 1: Verify clean git tree**

Run: `git status --short`
Expected: empty (all changes committed)

- [ ] **Step 2: Summary of commits**

Run: `git log --oneline 9d8ec2d..HEAD | head -30`
Expected: ~25 commits matching the task structure of this plan.

- [ ] **Step 3: No further commit — proceed to finishing-a-development-branch**

---

# Acceptance criteria (from spec)

When all tasks complete, the following must all be true:

1. ✅ Pressing Space with a queue item selected and a video loaded → `videoEl.paused` flips true ↔ false within 100ms.
2. ✅ Starting a render via `POST /api/render` → the 4th stage cell of the matching queue item transitions through `idle` → `warn(0%)` → `warn(N%)` → `done` (or `err`) without page reload.
3. ✅ Starting a render → an active card appears in WorkerStatus with tag `燒字` and percent progress.
4. ✅ Uploading a new file → ASR cell shows `queued` (pulsing) within 1 second of dropzone confirmation.
5. ✅ Backend `pipeline_stage_start` fires before first `pipeline_stage_progress` → ASR cell transitions through `queued` → `starting` (pulse + faint fill) → `warn(N%)` (solid fill).
6. ✅ Existing `console.spec.ts` (10 tests) still passes; existing `dashboard.spec.ts` / `bold-dashboard.spec.ts` still pass.
7. ✅ All vitest tests still pass; backend pytest 1050 PASS / 23 baseline failed (was 1047) + 3 new render-event tests.

---

# Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-22-console-ux-completion-plan.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. ~22 tasks across 4 phases. Backend tasks can use Sonnet; frontend tasks use Sonnet; no Opus needed (well-specified spec with full code blocks).

2. **Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`. Batch execution with checkpoints for review. ~3-4 hr wall clock.

**Which approach?**
