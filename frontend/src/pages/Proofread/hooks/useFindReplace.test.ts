// src/pages/Proofread/hooks/useFindReplace.test.ts
import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useFindReplace } from './useFindReplace';
import type { Translation } from '../types';

function t(idx: number, en: string, zh: string, status: Translation['status'] = 'pending'): Translation {
  return { idx, en_text: en, zh_text: zh, status, flags: [] };
}

const sample: Translation[] = [
  t(0, 'Real Madrid', '皇家馬德里'),
  t(1, 'Manchester United', '曼聯'),
  t(2, 'Real Sociedad', '皇家社會', 'approved'),
];

describe('useFindReplace', () => {
  it('returns no matches when query empty', () => {
    const { result } = renderHook(() => useFindReplace(sample));
    expect(result.current.matches).toEqual([]);
  });

  it('matches zh substring with scope=zh', () => {
    const { result } = renderHook(() => useFindReplace(sample));
    act(() => result.current.setQuery('皇家'));
    expect(result.current.matches).toHaveLength(2);
    expect(result.current.matches[0]?.field).toBe('zh');
  });

  it('matches en substring with scope=en', () => {
    const { result } = renderHook(() => useFindReplace(sample));
    act(() => { result.current.setQuery('Real'); result.current.setScope('en'); });
    expect(result.current.matches).toHaveLength(2);
    expect(result.current.matches.every((m) => m.field === 'en')).toBe(true);
  });

  it('scope=both returns zh + en matches together', () => {
    const { result } = renderHook(() => useFindReplace(sample));
    act(() => { result.current.setQuery('Real'); result.current.setScope('both'); });
    // 2 en matches + 0 zh matches (no "Real" in chinese fields)
    expect(result.current.matches).toHaveLength(2);
  });

  it('scope=pending skips approved rows', () => {
    const { result } = renderHook(() => useFindReplace(sample));
    act(() => { result.current.setQuery('皇家'); result.current.setScope('pending'); });
    // Only row idx=0 matches (idx=2 is approved + skipped)
    expect(result.current.matches).toHaveLength(1);
    expect(result.current.matches[0]?.idx).toBe(0);
  });

  it('next/prev cycle through matches', () => {
    const { result } = renderHook(() => useFindReplace(sample));
    act(() => result.current.setQuery('皇家'));
    expect(result.current.cursor).toBe(0);
    act(() => result.current.next());
    expect(result.current.cursor).toBe(1);
    act(() => result.current.next());
    expect(result.current.cursor).toBe(0); // wraps
    act(() => result.current.prev());
    expect(result.current.cursor).toBe(1);
  });

  it('replaceOne returns one mutation at current cursor', () => {
    const { result } = renderHook(() => useFindReplace(sample));
    act(() => result.current.setQuery('皇家'));
    const muts = result.current.replaceOne('皇室');
    expect(muts).toHaveLength(1);
    expect(muts[0]?.newText).toBe('皇室馬德里');
  });

  it('replaceAll returns mutations for every match', () => {
    const { result } = renderHook(() => useFindReplace(sample));
    act(() => result.current.setQuery('皇家'));
    const muts = result.current.replaceAll('皇室');
    expect(muts).toHaveLength(2);
    expect(muts.find((m) => m.idx === 0)?.newText).toBe('皇室馬德里');
    expect(muts.find((m) => m.idx === 2)?.newText).toBe('皇室社會');
  });

  it('replaceOne returns empty array when no matches', () => {
    const { result } = renderHook(() => useFindReplace(sample));
    act(() => result.current.setQuery('nonexistent'));
    expect(result.current.replaceOne('x')).toEqual([]);
  });
});
