import { describe, it, expect } from 'vitest';
import { PipelineV5Schema } from './pipeline-v5';

const font_config = {
  family: 'Noto Sans TC',
  color: '#FFFFFF',
  outline_color: '#000000',
};

const minimalValid = {
  name: 'ZH Only Pipeline',
  version: 5 as const,
  asr_primary: { transcribe_profile_id: 't-1', source_lang: 'zh' as const },
  asr_secondary: null,
  asr_verifier: null,
  target_languages: ['zh' as const],
  refinements: { zh: [{ refiner_profile_id: 'r-1' }] },
  translators: {},
  font_config,
};

describe('PipelineV5Schema', () => {
  it('accepts a minimal valid v5 pipeline (source-only)', () => {
    const r = PipelineV5Schema.parse(minimalValid);
    expect(r.version).toBe(5);
    expect(r.target_languages).toEqual(['zh']);
    expect(r.glossary_stages).toEqual({});
    expect(r.shared).toBe(false);
  });

  it('rejects refinements key not in target_languages', () => {
    expect(() => PipelineV5Schema.parse({
      ...minimalValid,
      target_languages: ['zh'],
      refinements: { en: [{ refiner_profile_id: 'r-1' }] },
    })).toThrow(/refinements keys/);
  });

  it('rejects asr_secondary lang mismatch with primary', () => {
    expect(() => PipelineV5Schema.parse({
      ...minimalValid,
      asr_secondary: { transcribe_profile_id: 't-2', source_lang: 'en' },
    })).toThrow(/asr_secondary/);
  });

  it('rejects missing translator for non-source target', () => {
    expect(() => PipelineV5Schema.parse({
      ...minimalValid,
      target_languages: ['zh', 'en'],
      refinements: {
        zh: [{ refiner_profile_id: 'r-1' }],
        en: [{ refiner_profile_id: 'r-2' }],
      },
      translators: {},
    })).toThrow(/translators required/);
  });

  it('accepts ZH + EN with explicit translator', () => {
    const r = PipelineV5Schema.parse({
      ...minimalValid,
      target_languages: ['zh', 'en'],
      refinements: {
        zh: [{ refiner_profile_id: 'r-1' }],
        en: [{ refiner_profile_id: 'r-2' }],
      },
      translators: {
        en: { translator_profile_id: 'tr-1' },
      },
    });
    expect(r.target_languages).toEqual(['zh', 'en']);
    expect(r.translators['en']).toEqual({ translator_profile_id: 'tr-1' });
  });
});
