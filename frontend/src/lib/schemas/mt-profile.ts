import { z } from 'zod';

export const MT_ENGINES = ['qwen3.5-35b-a3b'] as const;
export const MT_LANGUAGES = ['en', 'zh', 'ja', 'ko', 'fr', 'de', 'es'] as const;

export const MtProfileSchema = z
  .object({
    name: z.string().min(1).max(64),
    description: z.string().max(256).default(''),
    shared: z.boolean().default(false),
    engine: z.enum(MT_ENGINES).default('qwen3.5-35b-a3b'),
    input_lang: z.enum(MT_LANGUAGES),
    output_lang: z.enum(MT_LANGUAGES),
    system_prompt: z.string().min(1).max(4096),
    user_message_template: z
      .string()
      .min(1)
      .max(1024)
      .refine((s) => s.includes('{text}'), {
        message: 'user_message_template must contain {text} placeholder',
      }),
    batch_size: z.number().int().min(1).max(64).default(1),
    temperature: z.number().min(0).max(2).default(0.1),
    parallel_batches: z.number().int().min(1).max(16).default(1),
  })
  .refine((d) => d.input_lang === d.output_lang, {
    message: 'MT is same-lang only — input_lang must equal output_lang (v4.0)',
  });

export type MtProfile = z.infer<typeof MtProfileSchema>;
