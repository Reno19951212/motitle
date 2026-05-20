import { z } from 'zod';

export const TRANSCRIBE_ENGINES = ['whisper', 'mlx-whisper', 'qwen3-asr'] as const;
export const TRANSCRIBE_LANGUAGES = ['en', 'zh', 'ja', 'ko', 'yue', 'fr', 'de', 'es', 'th', 'auto'] as const;

export const TranscribeProfileSchema = z.object({
  name: z.string().min(1).max(64),
  engine: z.enum(TRANSCRIBE_ENGINES),
  language: z.enum(TRANSCRIBE_LANGUAGES).default('auto'),
  model_size: z.string().optional(),
  initial_prompt: z.string().max(512).optional(),
  shared: z.boolean().default(false),
});

export type TranscribeProfile = z.infer<typeof TranscribeProfileSchema>;

export interface TranscribeProfileRow extends TranscribeProfile {
  id: string;
  user_id: number;
  created_at: number;
  updated_at: number;
}
