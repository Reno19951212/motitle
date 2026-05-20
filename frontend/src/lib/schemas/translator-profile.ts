import { z } from 'zod';

export const TRANSLATOR_LANGS = ['en', 'zh', 'ja', 'ko', 'yue', 'fr', 'de', 'es', 'th'] as const;

export const TranslatorProfileSchema = z.object({
  name: z.string().min(1).max(64),
  source_lang: z.enum(TRANSLATOR_LANGS),
  target_lang: z.enum(TRANSLATOR_LANGS),
  llm_profile_id: z.string().min(1),
  prompt_template_id: z.string().min(1),
  shared: z.boolean().default(false),
}).refine(
  (data) => data.source_lang !== data.target_lang,
  { message: 'source_lang and target_lang must differ (use Refiner for same-lang polish)', path: ['target_lang'] },
);

export type TranslatorProfile = z.infer<typeof TranslatorProfileSchema>;

export interface TranslatorProfileRow extends TranslatorProfile {
  id: string;
  user_id: number;
  created_at: number;
  updated_at: number;
}
