import { describe, it, expect } from 'vitest';
import { formatTimecode } from './format-timecode';

describe('formatTimecode', () => {
  it('returns 00:00:00:00 at t=0', () => {
    expect(formatTimecode(0)).toBe('00:00:00:00');
  });
  it('formats whole seconds at 25fps', () => {
    expect(formatTimecode(1)).toBe('00:00:01:00');
    expect(formatTimecode(61)).toBe('00:01:01:00');
    expect(formatTimecode(3661)).toBe('01:01:01:00');
  });
  it('rounds sub-second to nearest frame', () => {
    expect(formatTimecode(0.04)).toBe('00:00:00:01'); // 1 frame at 25fps
    expect(formatTimecode(0.5)).toBe('00:00:00:13');  // 12.5 → Math.round → 13
  });
  it('handles fractional that crosses second boundary via rounding', () => {
    // 0.999s * 25 = 24.975 → round = 25 → carries into 1s
    expect(formatTimecode(0.999)).toBe('00:00:01:00');
  });
  it('returns sentinel for NaN/Infinity/negative', () => {
    expect(formatTimecode(NaN)).toBe('00:00:00:00');
    expect(formatTimecode(Infinity)).toBe('00:00:00:00');
    expect(formatTimecode(-1)).toBe('00:00:00:00');
  });
  it('honors custom fps', () => {
    expect(formatTimecode(1, 30)).toBe('00:00:01:00');
    expect(formatTimecode(0.5, 30)).toBe('00:00:00:15');
  });
});
