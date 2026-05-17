import { z } from 'zod';

export const RESOLUTIONS = ['keep', '720p', '1080p', '4k'] as const;
export const SUBTITLE_SOURCES = ['auto', 'source', 'target', 'bilingual'] as const;
export const BILINGUAL_ORDERS = ['source_top', 'target_top'] as const;
export const AUDIO_BIT_DEPTHS = ['16', '24', '32'] as const;

export const MP4_BITRATE_MODES = ['crf', 'cbr', '2pass'] as const;
export const MP4_PRESETS = [
  'ultrafast',
  'superfast',
  'veryfast',
  'faster',
  'fast',
  'medium',
  'slow',
  'slower',
  'veryslow',
] as const;
export const MP4_PIXEL_FORMATS = ['yuv420p', 'yuv422p', 'yuv444p'] as const;
export const MP4_PROFILES = ['baseline', 'main', 'high', 'high422', 'high444'] as const;
export const MP4_LEVELS = ['3.1', '3.2', '4.0', '4.1', '5.0', '5.1', '5.2', 'auto'] as const;
export const MP4_AUDIO_BITRATES = ['128k', '192k', '320k'] as const;

export const PRORES_PROFILES = ['0', '1', '2', '3', '4', '5'] as const;
export const PRORES_PROFILE_LABELS: Record<(typeof PRORES_PROFILES)[number], string> = {
  '0': 'Proxy',
  '1': 'LT',
  '2': 'Standard',
  '3': 'HQ',
  '4': '4444',
  '5': '4444 XQ',
};

const commonOptions = {
  resolution: z.enum(RESOLUTIONS).default('keep'),
  subtitle_source: z.enum(SUBTITLE_SOURCES).default('auto'),
  bilingual_order: z.enum(BILINGUAL_ORDERS).default('source_top'),
};

type Mp4PixelProfileInput = {
  pixel_format: (typeof MP4_PIXEL_FORMATS)[number];
  profile: (typeof MP4_PROFILES)[number];
};

const mp4PixelProfileCheck = (v: Mp4PixelProfileInput): boolean => {
  if (v.pixel_format === 'yuv422p' && v.profile !== 'high422') return false;
  if (v.pixel_format === 'yuv444p' && v.profile !== 'high444') return false;
  if (v.profile === 'high422' && v.pixel_format !== 'yuv422p') return false;
  if (v.profile === 'high444' && v.pixel_format !== 'yuv444p') return false;
  return true;
};

const MP4_PIXEL_PROFILE_MESSAGE =
  'pixel_format and H.264 profile must match (yuv422p↔high422, yuv444p↔high444)';

// Base object schema (no .refine) so it can participate in z.discriminatedUnion.
const Mp4SchemaBase = z.object({
  format: z.literal('mp4'),
  bitrate_mode: z.enum(MP4_BITRATE_MODES).default('crf'),
  crf: z.number().int().min(0).max(51).default(18),
  video_bitrate_mbps: z.number().int().min(2).max(100).default(15),
  preset: z.enum(MP4_PRESETS).default('medium'),
  pixel_format: z.enum(MP4_PIXEL_FORMATS).default('yuv420p'),
  profile: z.enum(MP4_PROFILES).default('high'),
  level: z.enum(MP4_LEVELS).default('auto'),
  audio_bitrate: z.enum(MP4_AUDIO_BITRATES).default('192k'),
  ...commonOptions,
});

export const Mp4Schema = Mp4SchemaBase.refine(mp4PixelProfileCheck, {
  message: MP4_PIXEL_PROFILE_MESSAGE,
  path: ['profile'],
});

export const ProResSchema = z.object({
  format: z.literal('mxf_prores'),
  prores_profile: z.enum(PRORES_PROFILES).default('3'),
  audio_bit_depth: z.enum(AUDIO_BIT_DEPTHS).default('24'),
  ...commonOptions,
});

export const XdcamSchema = z.object({
  format: z.literal('mxf_xdcam_hd422'),
  video_bitrate_mbps: z.number().int().min(10).max(100).default(50),
  audio_bit_depth: z.enum(AUDIO_BIT_DEPTHS).default('24'),
  ...commonOptions,
});

// Discriminated union uses the *base* MP4 object (z.discriminatedUnion rejects ZodEffects),
// then we re-apply the MP4 cross-field refinement via `.superRefine` so the union still
// enforces the same constraint when format === 'mp4'.
export const RenderOptionsSchema = z
  .discriminatedUnion('format', [Mp4SchemaBase, ProResSchema, XdcamSchema])
  .superRefine((v, ctx) => {
    if (v.format === 'mp4' && !mp4PixelProfileCheck(v)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: MP4_PIXEL_PROFILE_MESSAGE,
        path: ['profile'],
      });
    }
  });

export type Mp4Options = z.infer<typeof Mp4Schema>;
export type ProResOptions = z.infer<typeof ProResSchema>;
export type XdcamOptions = z.infer<typeof XdcamSchema>;
export type RenderOptions = z.infer<typeof RenderOptionsSchema>;
