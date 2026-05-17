import { z } from 'zod';

export const SUBTITLE_SOURCES = ['auto', 'source', 'target', 'bilingual'] as const;
export const BILINGUAL_ORDERS = ['source_top', 'target_top'] as const;
export const GLOSSARY_APPLY_ORDERS = ['explicit'] as const;
export const GLOSSARY_APPLY_METHODS = ['string-match-then-llm'] as const;

export const GlossaryStageSchema = z
  .object({
    enabled: z.boolean(),
    glossary_ids: z.array(z.string().min(1)).default([]),
    apply_order: z.enum(GLOSSARY_APPLY_ORDERS).default('explicit'),
    apply_method: z.enum(GLOSSARY_APPLY_METHODS).default('string-match-then-llm'),
  })
  .refine((s) => !s.enabled || s.glossary_ids.length > 0, {
    message: 'glossary_ids must be non-empty when enabled=true',
    path: ['glossary_ids'],
  });

export const FontConfigSchema = z.object({
  family: z.string().min(1),
  color: z.string().min(1),
  outline_color: z.string().min(1),
  size: z.number().int().nonnegative(),
  outline_width: z.number().int().nonnegative(),
  margin_bottom: z.number().int().nonnegative(),
  subtitle_source: z.enum(SUBTITLE_SOURCES),
  bilingual_order: z.enum(BILINGUAL_ORDERS),
});

export const PipelineSchema = z.object({
  name: z.string().min(1).max(64),
  description: z.string().max(256).default(''),
  shared: z.boolean().default(false),
  asr_profile_id: z.string().min(1),
  mt_stages: z.array(z.string().min(1)).max(8).default([]),
  glossary_stage: GlossaryStageSchema,
  font_config: FontConfigSchema,
});

export type Pipeline = z.infer<typeof PipelineSchema>;
export type GlossaryStage = z.infer<typeof GlossaryStageSchema>;
export type FontConfig = z.infer<typeof FontConfigSchema>;
