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
