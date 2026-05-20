// src/pages/Proofread/hooks/useFileData.test.ts
// v5-A3 — useFileData now signature is (fileId, activeLang) and fetches via
// v5 shape (?shape=v5) deriving v4-shape Translation[] for the active lang.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useFileData } from './useFileData';

beforeEach(() => { vi.restoreAllMocks(); });

const jsonResp = (obj: unknown) =>
  new Response(JSON.stringify(obj), { status: 200, headers: { 'Content-Type': 'application/json' } });

const v5Rows = [
  {
    idx: 0,
    start: 0,
    end: 1,
    source_lang: 'en',
    source_text: 'hi',
    by_lang: {
      en: { text: 'hi', status: 'pending', flags: [] as string[] },
      zh: { text: '你好', status: 'pending', flags: [] as string[] },
    },
  },
];

describe('useFileData', () => {
  it('fetches file + v5 translations + segments on mount; derives for activeLang', async () => {
    vi.spyOn(global, 'fetch')
      // Promise.all order: file, translations(v5), segments
      .mockResolvedValueOnce(jsonResp({ id: 'a', original_name: 'x.mp4', status: 'completed' }))
      .mockResolvedValueOnce(jsonResp({ translations: v5Rows }))
      .mockResolvedValueOnce(jsonResp({ id: 'a', status: 'completed', segments: [], text: '' }));
    const { result } = renderHook(() => useFileData('a', 'zh'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.file?.original_name).toBe('x.mp4');
    expect(result.current.translations).toHaveLength(1);
    expect(result.current.translations[0]?.en_text).toBe('hi');
    expect(result.current.translations[0]?.zh_text).toBe('你好');
    expect(result.current.availableLangs).toEqual(['en', 'zh']);
    expect(result.current.sourceLang).toBe('en');
    expect(result.current.error).toBeNull();
  });

  it('re-derives translations when activeLang changes (no re-fetch)', async () => {
    vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce(jsonResp({ id: 'a', original_name: 'x.mp4', status: 'completed' }))
      .mockResolvedValueOnce(jsonResp({ translations: v5Rows }))
      .mockResolvedValueOnce(jsonResp({ id: 'a', status: 'completed', segments: [], text: '' }));
    const { result, rerender } = renderHook(
      ({ lang }: { lang: string }) => useFileData('a', lang),
      { initialProps: { lang: 'zh' } },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.translations[0]?.zh_text).toBe('你好');
    rerender({ lang: 'en' });
    expect(result.current.translations[0]?.zh_text).toBe('hi');
  });

  it('synthesizes translations from segments when v5 list is empty (ASR-only)', async () => {
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
    const { result } = renderHook(() => useFileData('a', 'zh'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.translations).toHaveLength(2);
    expect(result.current.translations[0]?.en_text).toBe('第一段');
    expect(result.current.translations[0]?.zh_text).toBe('第一段');
    expect(result.current.availableLangs).toEqual([]);
    expect(result.current.sourceLang).toBeNull();
  });

  it('sets error on file fetch failure', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValueOnce(new Error('network'));
    const { result } = renderHook(() => useFileData('a', 'zh'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeTruthy();
  });

  it('refresh refetches when called', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce(jsonResp({ id: 'a', original_name: 'x.mp4', status: 'completed' }))
      .mockResolvedValueOnce(jsonResp({ translations: [] }))
      .mockResolvedValueOnce(jsonResp({ id: 'a', status: 'completed', segments: [], text: '' }));
    const { result } = renderHook(() => useFileData('a', 'zh'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    fetchSpy
      .mockResolvedValueOnce(jsonResp({ id: 'a', original_name: 'x.mp4', status: 'completed' }))
      .mockResolvedValueOnce(jsonResp({ translations: v5Rows }))
      .mockResolvedValueOnce(jsonResp({ id: 'a', status: 'completed', segments: [], text: '' }));
    await act(async () => { await result.current.refresh(); });
    await waitFor(() => expect(result.current.translations).toHaveLength(1));
    expect(result.current.translations[0]?.zh_text).toBe('你好');
  });
});
