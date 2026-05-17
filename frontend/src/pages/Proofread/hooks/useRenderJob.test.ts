import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useRenderJob } from './useRenderJob';

// `shouldAdvanceTime: true` lets React Testing Library's `waitFor` internal timeouts
// proceed in real time while we still control polling intervals via `advanceTimersByTime`.
beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.restoreAllMocks();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('useRenderJob', () => {
  it('startRender POSTs /api/render and stores job', async () => {
    vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ render_id: 'r1', filename: 'x.mp4' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ render_id: 'r1', filename: 'x.mp4', status: 'queued', progress: 0 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      );
    const { result } = renderHook(() => useRenderJob());
    await act(async () => {
      await result.current.startRender({ file_id: 'a', format: 'mp4' });
    });
    expect(result.current.currentJob?.render_id).toBe('r1');
  });

  it('polls every 2s and stops on completed', async () => {
    const fetchSpy = vi
      .spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ render_id: 'r1', filename: 'x.mp4' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      // Immediate poll (running)
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ render_id: 'r1', filename: 'x.mp4', status: 'running', progress: 50 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      // Second poll (completed)
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ render_id: 'r1', filename: 'x.mp4', status: 'completed', progress: 100 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      // Should not be called again
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ render_id: 'r1', filename: 'x.mp4', status: 'completed' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      );
    const { result } = renderHook(() => useRenderJob());
    await act(async () => {
      await result.current.startRender({});
    });
    await waitFor(() => expect(result.current.currentJob?.status).toBe('running'));
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    await waitFor(() => expect(result.current.currentJob?.status).toBe('completed'));
    const callsBefore = fetchSpy.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(4000);
    });
    expect(fetchSpy.mock.calls.length).toBe(callsBefore); // no more polls
  });

  it('handles startRender API failure', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValueOnce(new Error('500'));
    const { result } = renderHook(() => useRenderJob());
    await act(async () => {
      await result.current.startRender({});
    });
    expect(result.current.currentJob?.status).toBe('failed');
  });

  it('cancel DELETEs /api/renders/<id> and marks cancelled', async () => {
    const fetchSpy = vi
      .spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ render_id: 'r1', filename: 'x.mp4' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ render_id: 'r1', filename: 'x.mp4', status: 'running' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
      );
    const { result } = renderHook(() => useRenderJob());
    await act(async () => {
      await result.current.startRender({});
    });
    await waitFor(() => expect(result.current.currentJob?.status).toBe('running'));
    await act(async () => {
      await result.current.cancel();
    });
    expect(result.current.currentJob?.status).toBe('cancelled');
    const deleteCall = fetchSpy.mock.calls.find(
      (c) => (c[1] as RequestInit | undefined)?.method === 'DELETE',
    );
    expect(deleteCall).toBeTruthy();
  });

  it('clear resets state', async () => {
    vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ render_id: 'r1', filename: 'x.mp4' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ render_id: 'r1', filename: 'x.mp4', status: 'queued' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      );
    const { result } = renderHook(() => useRenderJob());
    await act(async () => {
      await result.current.startRender({});
    });
    expect(result.current.currentJob).not.toBeNull();
    act(() => result.current.clear());
    expect(result.current.currentJob).toBeNull();
  });
});
