import { z } from 'zod';

export const RESOLUTIONS = ['keep', '720p', '1080p', '4k'] as const;
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

export const Mp4Schema = z
  .object({
    format: z.literal('mp4'),
    bitrate_mode: z.enum(MP4_BITRATE_MODES).default('crf'),
    crf: z.number().int().min(0).max(51).default(18),
    video_bitrate_mbps: z.number().int().min(2).max(100).default(15),
    preset: z.enum(MP4_PRESETS).default('medium'),
    pixel_format: z.enum(MP4_PIXEL_FORMATS).default('yuv420p'),
    profile: z.enum(MP4_PROFILES).default('high'),
    level: z.enum(MP4_LEVELS).default('auto'),
    audio_bitrate: z.enum(MP4_AUDIO_BITRATES).default('192k'),
    resolution: z.enum(RESOLUTIONS).default('keep'),
    subtitle_source: z.enum(['auto', 'source', 'target', 'bilingual']).default('auto'),
    bilingual_order: z.enum(['source_top', 'target_top']).default('source_top'),
  })
  .refine(
    (v) => {
      if (v.pixel_format === 'yuv422p' && v.profile !== 'high422') return false;
      if (v.pixel_format === 'yuv444p' && v.profile !== 'high444') return false;
      if (v.profile === 'high422' && v.pixel_format !== 'yuv422p') return false;
      if (v.profile === 'high444' && v.pixel_format !== 'yuv444p') return false;
      return true;
    },
    {
      message: 'pixel_format and H.264 profile must match (yuv422p↔high422, yuv444p↔high444)',
      path: ['profile'],
    },
  );

export type Mp4Options = z.infer<typeof Mp4Schema>;

// T15 will add MXF schemas + discriminated union RenderOptionsSchema
// For now, just re-export Mp4Schema as the union for type compat.
export const RenderOptionsSchema = Mp4Schema;
export type RenderOptions = z.infer<typeof RenderOptionsSchema>;
