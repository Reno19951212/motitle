// src/pages/Proofread/hooks/useFileData.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useFileData } from './useFileData';

beforeEach(() => { vi.restoreAllMocks(); });

const jsonResp = (obj: unknown) =>
  new Response(JSON.stringify(obj), { status: 200, headers: { 'Content-Type': 'application/json' } });

describe('useFileData', () => {
  it('fetches file + translations + segments on mount', async () => {
    vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce(jsonResp({ id: 'a', original_name: 'x.mp4', status: 'completed' }))
      .mockResolvedValueOnce(jsonResp({
        translations: [{ idx: 0, en_text: 'hi', zh_text: '你好', status: 'pending', flags: [] }],
      }))
      .mockResolvedValueOnce(jsonResp({ id: 'a', status: 'completed', segments: [], text: '' }));
    const { result } = renderHook(() => useFileData('a'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.file?.original_name).toBe('x.mp4');
    expect(result.current.translations).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('synthesizes translations from segments when MT is empty (ASR-only)', async () => {
    vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce(jsonResp({ id: 'a', original_name: 'x.mp4', status: 'completed' }))
      .mockResolvedValueOnce(jsonResp({ translations: [] }))
      .mockResolvedValueOnce(jsonResp({
        id: 'a',
        status: 'completed',
        segments: [
          { id: '0', start: 0, end: 1, text: '第一段' },
          { id: '1', start: 1, end: 2, text: '第二段' },
        ],
        text: '',
      }));
    const { result } = renderHook(() => useFileData('a'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.translations).toHaveLength(2);
    expect(result.current.translations[0].en_text).toBe('第一段');
    expect(result.current.translations[0].zh_text).toBe('第一段');
  });

  it('sets error on file fetch failure', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValueOnce(new Error('network'));
    const { result } = renderHook(() => useFileData('a'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeTruthy();
  });

  it('refresh refetches when called', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce(jsonResp({ id: 'a', original_name: 'x.mp4', status: 'completed' }))
      .mockResolvedValueOnce(jsonResp({ translations: [] }))
      .mockResolvedValueOnce(jsonResp({ id: 'a', status: 'completed', segments: [], text: '' }));
    const { result } = renderHook(() => useFileData('a'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    fetchSpy
      .mockResolvedValueOnce(jsonResp({ id: 'a', original_name: 'x.mp4', status: 'completed' }))
      .mockResolvedValueOnce(jsonResp({
        translations: [{ idx: 0, en_text: 'a', zh_text: 'b', status: 'pending', flags: [] }],
      }))
      .mockResolvedValueOnce(jsonResp({ id: 'a', status: 'completed', segments: [], text: '' }));
    await act(async () => { await result.current.refresh(); });
    await waitFor(() => expect(result.current.translations).toHaveLength(1));
  });
});
