import { z } from 'zod';

export const GLOSSARY_LANGS = ['en', 'zh', 'ja', 'ko', 'es', 'fr', 'de', 'th'] as const;

export const GlossaryEntrySchema = z.object({
  source: z.string().min(1),
  target: z.string().min(1),
  target_aliases: z.array(z.string()).default([]),
});

export const GlossarySchema = z
  .object({
    name: z.string().min(1).max(64),
    description: z.string().max(256).default(''),
    shared: z.boolean().default(false),
    source_lang: z.enum(GLOSSARY_LANGS),
    target_lang: z.enum(GLOSSARY_LANGS),
    entries: z.array(GlossaryEntrySchema).default([]),
  })
  .refine((g) => g.source_lang !== g.target_lang || g.entries.length === 0, {
    message: 'source_lang and target_lang cannot match unless entries empty',
  });

export type Glossary = z.infer<typeof GlossarySchema>;
export type GlossaryEntry = z.infer<typeof GlossaryEntrySchema>;
