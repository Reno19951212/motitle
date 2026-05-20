import { z } from 'zod';
import { TRANSLATOR_LANGS } from './translator-profile';

export const VERIFIER_LANGS = TRANSLATOR_LANGS;

export const VerifierProfileSchema = z.object({
  name: z.string().min(1).max(64),
  lang: z.enum(VERIFIER_LANGS),
  llm_profile_id: z.string().min(1),
  prompt_template_id: z.string().min(1),
  shared: z.boolean().default(false),
});

export type VerifierProfile = z.infer<typeof VerifierProfileSchema>;

export interface VerifierProfileRow extends VerifierProfile {
  id: string;
  user_id: number;
  created_at: number;
  updated_at: number;
}
