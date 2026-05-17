import { describe, it, expect } from 'vitest';
import { PipelineSchema, GlossaryStageSchema, FontConfigSchema } from './pipeline';

const validFont = {
  family: 'Noto Sans TC',
  color: '#FFFFFF',
  outline_color: '#000000',
  size: 48,
  outline_width: 2,
  margin_bottom: 80,
  subtitle_source: 'auto' as const,
  bilingual_order: 'source_top' as const,
};

describe('FontConfigSchema', () => {
  it('accepts valid font config', () => {
    const r = FontConfigSchema.parse(validFont);
    expect(r.family).toBe('Noto Sans TC');
  });

  it('rejects negative size', () => {
    expect(() => FontConfigSchema.parse({ ...validFont, size: -1 })).toThrow();
  });

  it('rejects empty family', () => {
    expect(() => FontConfigSchema.parse({ ...validFont, family: '' })).toThrow();
  });
});

describe('GlossaryStageSchema', () => {
  it('accepts disabled stage with empty glossary_ids', () => {
    const r = GlossaryStageSchema.parse({ enabled: false });
    expect(r.glossary_ids).toEqual([]);
    expect(r.apply_order).toBe('explicit');
  });

  it('accepts enabled stage with glossary_ids', () => {
    const r = GlossaryStageSchema.parse({ enabled: true, glossary_ids: ['g1', 'g2'] });
    expect(r.glossary_ids).toEqual(['g1', 'g2']);
  });

  it('rejects enabled stage with empty glossary_ids', () => {
    expect(() => GlossaryStageSchema.parse({ enabled: true, glossary_ids: [] })).toThrow();
  });
});

describe('PipelineSchema', () => {
  const validPipeline = {
    name: 'Production',
    asr_profile_id: 'asr-1',
    mt_stages: ['mt-1', 'mt-2'],
    glossary_stage: { enabled: false, glossary_ids: [] },
    font_config: validFont,
  };

  it('accepts valid pipeline', () => {
    const r = PipelineSchema.parse(validPipeline);
    expect(r.name).toBe('Production');
    expect(r.mt_stages).toHaveLength(2);
  });

  it('accepts pipeline with empty mt_stages', () => {
    const r = PipelineSchema.parse({ ...validPipeline, mt_stages: [] });
    expect(r.mt_stages).toEqual([]);
  });

  it('accepts pipeline with 8 mt_stages (max allowed)', () => {
    const stages = Array.from({ length: 8 }, (_, i) => `mt-${i}`);
    const r = PipelineSchema.parse({ ...validPipeline, mt_stages: stages });
    expect(r.mt_stages).toHaveLength(8);
  });

  it('rejects pipeline without asr_profile_id', () => {
    const { asr_profile_id: _omit, ...rest } = validPipeline;
    expect(() => PipelineSchema.parse(rest)).toThrow();
  });

  it('rejects pipeline with > 8 mt_stages', () => {
    const stages = Array.from({ length: 9 }, (_, i) => `mt-${i}`);
    expect(() => PipelineSchema.parse({ ...validPipeline, mt_stages: stages })).toThrow();
  });

  it('rejects pipeline with glossary enabled but empty glossary_ids', () => {
    expect(() =>
      PipelineSchema.parse({
        ...validPipeline,
        glossary_stage: { enabled: true, glossary_ids: [] },
      }),
    ).toThrow();
  });

  it('rejects pipeline with negative font size', () => {
    expect(() =>
      PipelineSchema.parse({ ...validPipeline, font_config: { ...validFont, size: -5 } }),
    ).toThrow();
  });

  it('rejects empty asr_profile_id', () => {
    expect(() => PipelineSchema.parse({ ...validPipeline, asr_profile_id: '' })).toThrow();
  });
});
