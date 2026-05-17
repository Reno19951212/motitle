// src/pages/Proofread/hooks/useFilePipeline.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useFilePipeline } from './useFilePipeline';

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('useFilePipeline', () => {
  it('returns null when pipelineId is null', async () => {
    const { result } = renderHook(() => useFilePipeline(null));
    await waitFor(() => expect(result.current.pipeline).toBeNull());
    expect(result.current.font).toBeNull();
    expect(result.current.glossaryId).toBeNull();
  });

  it('fetches /api/pipelines/<id> and exposes font + glossaryId', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          id: 'p1',
          name: 'P',
          asr_profile_id: 'a1',
          mt_stages: ['m1'],
          glossary_stage: {
            enabled: true,
            glossary_ids: ['g1'],
            apply_order: 'explicit',
            apply_method: 'string-match-then-llm',
          },
          font_config: {
            family: 'Noto Sans TC',
            size: 35,
            color: '#fff',
            outline_color: '#000',
            outline_width: 2,
            margin_bottom: 40,
            subtitle_source: 'auto',
            bilingual_order: 'source_top',
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const { result } = renderHook(() => useFilePipeline('p1'));
    await waitFor(() => expect(result.current.pipeline?.id).toBe('p1'));
    expect(result.current.font?.family).toBe('Noto Sans TC');
    expect(result.current.glossaryId).toBe('g1');
  });

  it('returns null font/glossaryId on fetch failure', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValueOnce(new Error('500'));
    const { result } = renderHook(() => useFilePipeline('p1'));
    await waitFor(() => expect(result.current.pipeline).toBeNull());
    expect(result.current.font).toBeNull();
    expect(result.current.glossaryId).toBeNull();
  });
});
