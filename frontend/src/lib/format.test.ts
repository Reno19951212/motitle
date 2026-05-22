// frontend/src/lib/format.test.ts
import { describe, it, expect } from 'vitest';
import { formatDuration, formatBytes, formatRelativeTime } from './format';

describe('formatDuration', () => {
  it('returns dash for null', () => {
    expect(formatDuration(null)).toBe('—');
  });
  it('formats under an hour as mm:ss', () => {
    expect(formatDuration(0)).toBe('00:00');
    expect(formatDuration(7)).toBe('00:07');
    expect(formatDuration(65)).toBe('01:05');
    expect(formatDuration(2538)).toBe('42:18');
  });
  it('formats an hour or more as h:mm:ss', () => {
    expect(formatDuration(3600)).toBe('1:00:00');
    expect(formatDuration(3725)).toBe('1:02:05');
  });
  it('handles fractional seconds by flooring', () => {
    expect(formatDuration(42.9)).toBe('00:42');
  });
});

describe('formatBytes', () => {
  it('formats KB', () => {
    expect(formatBytes(1024)).toBe('1.0 KB');
    expect(formatBytes(2048)).toBe('2.0 KB');
  });
  it('formats MB', () => {
    expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
    expect(formatBytes(284 * 1024 * 1024)).toBe('284.0 MB');
  });
  it('formats GB', () => {
    expect(formatBytes(1.2 * 1024 ** 3)).toBe('1.2 GB');
  });
});

describe('formatRelativeTime', () => {
  const now = 1716000000;  // any fixed instant
  it('returns "剛剛" for < 60s', () => {
    expect(formatRelativeTime(now - 30, now)).toBe('剛剛');
  });
  it('returns "N 分鐘前" for minutes', () => {
    expect(formatRelativeTime(now - 120, now)).toBe('2 分鐘前');
  });
  it('returns "N 小時前" for hours', () => {
    expect(formatRelativeTime(now - 7200, now)).toBe('2 小時前');
  });
  it('returns "N 日前" for days', () => {
    expect(formatRelativeTime(now - 86400 * 3, now)).toBe('3 日前');
  });
});
