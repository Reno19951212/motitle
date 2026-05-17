import { describe, it, expect } from 'vitest';
import { Mp4Schema } from './render-options';

const base = { format: 'mp4' as const, bitrate_mode: 'crf' as const };

describe('Mp4Schema', () => {
  it('accepts default MP4 + CRF', () => {
    const r = Mp4Schema.parse(base);
    expect(r.crf).toBe(18);
    expect(r.profile).toBe('high');
    expect(r.pixel_format).toBe('yuv420p');
  });

  it('rejects crf > 51', () => {
    expect(() => Mp4Schema.parse({ ...base, crf: 60 })).toThrow();
  });

  it('rejects video_bitrate_mbps > 100', () => {
    expect(() => Mp4Schema.parse({ ...base, bitrate_mode: 'cbr', video_bitrate_mbps: 200 })).toThrow();
  });

  it('rejects pixel_format=yuv422p + profile=high (mismatch)', () => {
    expect(() => Mp4Schema.parse({ ...base, pixel_format: 'yuv422p', profile: 'high' })).toThrow();
  });

  it('accepts pixel_format=yuv422p + profile=high422', () => {
    const r = Mp4Schema.parse({ ...base, pixel_format: 'yuv422p', profile: 'high422' });
    expect(r.profile).toBe('high422');
  });

  it('rejects profile=high444 + pixel_format=yuv420p (reverse direction)', () => {
    expect(() => Mp4Schema.parse({ ...base, profile: 'high444', pixel_format: 'yuv420p' })).toThrow();
  });

  it('accepts pixel_format=yuv444p + profile=high444', () => {
    const r = Mp4Schema.parse({ ...base, pixel_format: 'yuv444p', profile: 'high444' });
    expect(r.profile).toBe('high444');
  });

  it('accepts unknown level=auto', () => {
    const r = Mp4Schema.parse({ ...base, level: 'auto' });
    expect(r.level).toBe('auto');
  });
});
