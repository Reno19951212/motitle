import { z } from 'zod';

export const LLM_BACKENDS = ['ollama', 'openrouter', 'claude'] as const;

export const LlmProfileSchema = z.object({
  name: z.string().min(1).max(64),
  backend: z.enum(LLM_BACKENDS),
  model: z.string().min(1),
  base_url: z.string().url(),
  temperature: z.number().min(0).max(2).default(0.2),
  shared: z.boolean().default(false),
  api_key: z.string().optional(),
});

export type LlmProfile = z.infer<typeof LlmProfileSchema>;

export interface LlmProfileRow extends LlmProfile {
  id: string;
  user_id: number;
  created_at: number;
  updated_at: number;
}
