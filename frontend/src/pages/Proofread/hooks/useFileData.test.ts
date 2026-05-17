// src/pages/Proofread/hooks/useFileData.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useFileData } from './useFileData';

beforeEach(() => { vi.restoreAllMocks(); });

describe('useFileData', () => {
  it('fetches file + translations on mount', async () => {
    vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: 'a', original_name: 'x.mp4', status: 'completed' }), {
          status: 200, headers: { 'Content-Type': 'application/json' }
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ translations: [{ idx: 0, en_text: 'hi', zh_text: '你好', status: 'pending', flags: [] }] }), {
          status: 200, headers: { 'Content-Type': 'application/json' }
        }),
      );
    const { result } = renderHook(() => useFileData('a'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.file?.original_name).toBe('x.mp4');
    expect(result.current.translations).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('sets error on file fetch failure', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValueOnce(new Error('network'));
    const { result } = renderHook(() => useFileData('a'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeTruthy();
  });

  it('refresh refetches when called', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'a', original_name: 'x.mp4', status: 'completed' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ translations: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    const { result } = renderHook(() => useFileData('a'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    fetchSpy
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'a', original_name: 'x.mp4', status: 'completed' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ translations: [{ idx: 0, en_text: 'a', zh_text: 'b', status: 'pending', flags: [] }] }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    await act(async () => { await result.current.refresh(); });
    await waitFor(() => expect(result.current.translations).toHaveLength(1));
  });
});
