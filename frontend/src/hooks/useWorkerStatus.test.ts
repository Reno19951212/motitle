import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useWorkerStatus } from './useWorkerStatus';

// Mock useSocket to avoid SocketProvider dependency in tests
vi.mock('../providers/SocketProvider', () => ({
  useSocket: () => ({ state: { files: {}, stageProgress: {}, stageStatus: {} }, dispatch: () => {}, refresh: async () => {} }),
}));

afterEach(() => vi.restoreAllMocks());

function mockFetchOnce(body: unknown) {
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
    ok: true,
    json: async () => body,
  } as Response);
}

describe('useWorkerStatus', () => {
  it('partitions running / queued / failed', async () => {
    mockFetchOnce([
      { id: 'j1', file_id: 'f1', status: 'running', position: 0, file_name: 'a.mp4', owner_username: 'u', eta_seconds: null, type: 'asr', created_at: 1 },
      { id: 'j2', file_id: 'f2', status: 'queued',  position: 1, file_name: 'b.mp4', owner_username: 'u', eta_seconds: null, type: 'asr', created_at: 2 },
      { id: 'j3', file_id: 'f3', status: 'failed',  position: 2, file_name: 'c.mp4', owner_username: 'u', eta_seconds: null, type: 'asr', created_at: 3 },
    ]);
    const { result } = renderHook(() => useWorkerStatus());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.activeJobs).toHaveLength(1);
    expect(result.current.queuedJobs).toHaveLength(1);
    expect(result.current.erroredJobs).toHaveLength(1);
  });

  it('sets error when fetch fails', async () => {
    // Mock ALL fetch calls to reject so no call falls through to jsdom's URL parser
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useWorkerStatus());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('boom');
  });
});
