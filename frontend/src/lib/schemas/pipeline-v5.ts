import { z } from 'zod';
import { TRANSLATOR_LANGS } from './translator-profile';

export const PIPELINE_V5_LANGS = TRANSLATOR_LANGS;

const FontConfigSchema = z.object({
  family: z.string().min(1),
  color: z.string().min(1),
  outline_color: z.string().min(1),
});

const AsrPrimarySchema = z.object({
  transcribe_profile_id: z.string().min(1),
  source_lang: z.enum(PIPELINE_V5_LANGS),
});

const AsrSecondarySchema = z.object({
  transcribe_profile_id: z.string().min(1),
  source_lang: z.enum(PIPELINE_V5_LANGS),
}).nullable();

const AsrVerifierSchema = z.object({
  llm_profile_id: z.string().min(1),
  prompt_template_id: z.string().min(1),
}).nullable();

const RefinementEntrySchema = z.object({
  refiner_profile_id: z.string().min(1),
});

const TranslatorEntrySchema = z.object({
  translator_profile_id: z.string().min(1),
});

export const PipelineV5Schema = z.object({
  name: z.string().min(1).max(64),
  version: z.literal(5),
  asr_primary: AsrPrimarySchema,
  asr_secondary: AsrSecondarySchema,
  asr_verifier: AsrVerifierSchema,
  target_languages: z.array(z.enum(PIPELINE_V5_LANGS)).min(1),
  refinements: z.record(z.string(), z.array(RefinementEntrySchema)),
  translators: z.record(z.string(), TranslatorEntrySchema),
  glossary_stages: z.record(z.string(), z.array(z.string())).optional().default({}),
  font_config: FontConfigSchema,
  shared: z.boolean().default(false),
}).refine(
  (data) => {
    if (data.asr_secondary && data.asr_secondary.source_lang !== data.asr_primary.source_lang) {
      return false;
    }
    return true;
  },
  { message: 'asr_secondary.source_lang must equal asr_primary.source_lang', path: ['asr_secondary'] },
).refine(
  (data) => {
    for (const lang of Object.keys(data.refinements)) {
      if (!data.target_languages.includes(lang as typeof data.target_languages[number])) {
        return false;
      }
    }
    return true;
  },
  { message: 'refinements keys must appear in target_languages', path: ['refinements'] },
).refine(
  (data) => {
    const source = data.asr_primary.source_lang;
    for (const lang of data.target_languages) {
      if (lang !== source && !(lang in data.translators)) {
        return false;
      }
    }
    return true;
  },
  { message: 'translators required for every non-source target language', path: ['translators'] },
);

export type PipelineV5 = z.infer<typeof PipelineV5Schema>;

export interface PipelineV5Row extends PipelineV5 {
  id: string;
  user_id: number;
  created_at: number;
  updated_at: number;
}
