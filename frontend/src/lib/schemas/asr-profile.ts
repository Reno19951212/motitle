import { z } from 'zod';

export const ASR_ENGINES = ['whisper', 'mlx-whisper'] as const;
export const ASR_MODEL_SIZES = ['large-v3'] as const;
export const ASR_MODES = ['same-lang', 'emergent-translate', 'translate-to-en'] as const;
export const ASR_LANGUAGES = ['en', 'zh', 'ja', 'ko', 'fr', 'de', 'es'] as const;
export const ASR_DEVICES = ['auto', 'cpu', 'cuda'] as const;

export const AsrProfileSchema = z.object({
  name: z.string().min(1).max(64),
  description: z.string().max(256).default(''),
  shared: z.boolean().default(false),
  engine: z.enum(ASR_ENGINES),
  model_size: z.enum(ASR_MODEL_SIZES).default('large-v3'),
  mode: z.enum(ASR_MODES),
  language: z.enum(ASR_LANGUAGES),
  initial_prompt: z.string().max(512).default(''),
  device: z.enum(ASR_DEVICES).default('auto'),
  condition_on_previous_text: z.boolean().default(false),
  simplified_to_traditional: z.boolean().default(false),
});

export type AsrProfile = z.infer<typeof AsrProfileSchema>;
