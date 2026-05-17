import { describe, it, expect } from 'vitest';
import { Mp4Schema, ProResSchema, XdcamSchema, RenderOptionsSchema } from './render-options';

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

describe('ProResSchema', () => {
  it('accepts default ProRes', () => {
    const r = ProResSchema.parse({ format: 'mxf_prores' });
    expect(r.prores_profile).toBe('3');
    expect(r.audio_bit_depth).toBe('24');
  });

  it('rejects unknown profile', () => {
    expect(() => ProResSchema.parse({ format: 'mxf_prores', prores_profile: '99' })).toThrow();
  });

  it('accepts each profile 0-5', () => {
    for (const p of ['0', '1', '2', '3', '4', '5'] as const) {
      const r = ProResSchema.parse({ format: 'mxf_prores', prores_profile: p });
      expect(r.prores_profile).toBe(p);
    }
  });
});

describe('XdcamSchema', () => {
  it('accepts default XDCAM (50 Mbps)', () => {
    const r = XdcamSchema.parse({ format: 'mxf_xdcam_hd422' });
    expect(r.video_bitrate_mbps).toBe(50);
  });

  it('rejects bitrate < 10', () => {
    expect(() => XdcamSchema.parse({ format: 'mxf_xdcam_hd422', video_bitrate_mbps: 5 })).toThrow();
  });

  it('rejects bitrate > 100', () => {
    expect(() => XdcamSchema.parse({ format: 'mxf_xdcam_hd422', video_bitrate_mbps: 150 })).toThrow();
  });
});

describe('RenderOptionsSchema (discriminated union)', () => {
  it('discriminates on format=mp4', () => {
    const r = RenderOptionsSchema.parse({ format: 'mp4', bitrate_mode: 'crf' });
    expect(r.format).toBe('mp4');
  });

  it('discriminates on format=mxf_prores', () => {
    const r = RenderOptionsSchema.parse({ format: 'mxf_prores' });
    expect(r.format).toBe('mxf_prores');
  });

  it('discriminates on format=mxf_xdcam_hd422', () => {
    const r = RenderOptionsSchema.parse({ format: 'mxf_xdcam_hd422' });
    expect(r.format).toBe('mxf_xdcam_hd422');
  });
});
