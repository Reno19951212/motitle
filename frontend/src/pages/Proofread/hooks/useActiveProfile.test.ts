// src/pages/Proofread/hooks/useActiveProfile.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useActiveProfile } from './useActiveProfile';

beforeEach(() => { vi.restoreAllMocks(); });

describe('useActiveProfile', () => {
  it('fetches /api/profiles/active on mount', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ profile: { id: 'p1', name: 'P', font: { family: 'Noto Sans TC', size: 35, color: '#fff', outline_color: '#000', outline_width: 2, margin_bottom: 40, subtitle_source: 'auto', bilingual_order: 'source_top' } } }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const { result } = renderHook(() => useActiveProfile());
    await waitFor(() => expect(result.current.profile).not.toBeNull());
    expect(result.current.profile?.font.family).toBe('Noto Sans TC');
  });

  it('keeps profile null on fetch error (swallows)', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValueOnce(new Error('network'));
    const { result } = renderHook(() => useActiveProfile());
    // After error, profile should remain null
    await waitFor(() => expect(result.current.profile).toBeNull());
  });
});
