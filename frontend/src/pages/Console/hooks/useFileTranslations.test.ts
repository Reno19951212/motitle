import { describe, it, expect } from 'vitest';
import { findActiveTranslation, type ConsoleTranslation } from './useFileTranslations';

const T = (start: number, end: number, zh: string): ConsoleTranslation =>
  ({ start, end, zh_text: zh, en_text: '' });

describe('findActiveTranslation', () => {
  const segs = [T(0, 5, 'A'), T(5, 10, 'B'), T(10, 15, 'C')];

  it('returns the segment whose [start, end) contains t', () => {
    expect(findActiveTranslation(segs, 0)?.zh_text).toBe('A');
    expect(findActiveTranslation(segs, 4.9)?.zh_text).toBe('A');
    expect(findActiveTranslation(segs, 5)?.zh_text).toBe('B');
    expect(findActiveTranslation(segs, 14.99)?.zh_text).toBe('C');
  });
  it('returns undefined past the last segment', () => {
    expect(findActiveTranslation(segs, 15)).toBeUndefined();
    expect(findActiveTranslation(segs, 999)).toBeUndefined();
  });
  it('returns undefined on empty list', () => {
    expect(findActiveTranslation([], 5)).toBeUndefined();
  });
  it('skips segments missing start/end', () => {
    const partial = [{ en_text: '', zh_text: 'bad' } as ConsoleTranslation, T(0, 5, 'A')];
    expect(findActiveTranslation(partial, 1)?.zh_text).toBe('A');
  });
});
