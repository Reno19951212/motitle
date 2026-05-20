import { z } from 'zod';
import { TRANSLATOR_LANGS } from './translator-profile';

export const REFINER_LANGS = TRANSLATOR_LANGS;

export const RefinerProfileSchema = z.object({
  name: z.string().min(1).max(64),
  lang: z.enum(REFINER_LANGS),
  style: z.string().min(1),
  llm_profile_id: z.string().min(1),
  prompt_template_id: z.string().min(1),
  shared: z.boolean().default(false),
});

export type RefinerProfile = z.infer<typeof RefinerProfileSchema>;

export interface RefinerProfileRow extends RefinerProfile {
  id: string;
  user_id: number;
  created_at: number;
  updated_at: number;
}
