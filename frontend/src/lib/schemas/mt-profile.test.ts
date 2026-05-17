import { describe, it, expect } from 'vitest';
import { MtProfileSchema } from './mt-profile';

describe('MtProfileSchema', () => {
  const valid = {
    name: 'MT-EN',
    input_lang: 'en' as const,
    output_lang: 'en' as const,
    system_prompt: 'You are a translator.',
    user_message_template: 'Translate: {text}',
  };

  it('accepts minimal valid payload', () => {
    const r = MtProfileSchema.parse(valid);
    expect(r.engine).toBe('qwen3.5-35b-a3b');
    expect(r.batch_size).toBe(1);
    expect(r.temperature).toBe(0.1);
    expect(r.parallel_batches).toBe(1);
  });

  it('accepts custom batch_size, temperature, parallel_batches', () => {
    const r = MtProfileSchema.parse({
      ...valid,
      batch_size: 8,
      temperature: 0.5,
      parallel_batches: 4,
    });
    expect(r.batch_size).toBe(8);
    expect(r.temperature).toBe(0.5);
    expect(r.parallel_batches).toBe(4);
  });

  it('accepts shared flag and description', () => {
    const r = MtProfileSchema.parse({ ...valid, shared: true, description: 'team-mt' });
    expect(r.shared).toBe(true);
    expect(r.description).toBe('team-mt');
  });

  it('rejects user_message_template without {text} placeholder', () => {
    expect(() =>
      MtProfileSchema.parse({ ...valid, user_message_template: 'Translate this please' }),
    ).toThrow();
  });

  it('rejects batch_size > 64', () => {
    expect(() => MtProfileSchema.parse({ ...valid, batch_size: 65 })).toThrow();
  });

  it('rejects temperature > 2', () => {
    expect(() => MtProfileSchema.parse({ ...valid, temperature: 2.5 })).toThrow();
  });

  it('rejects engine other than qwen3.5-35b-a3b', () => {
    expect(() => MtProfileSchema.parse({ ...valid, engine: 'gpt-4' })).toThrow();
  });

  it('rejects when input_lang differs from output_lang (same-lang only)', () => {
    expect(() =>
      MtProfileSchema.parse({ ...valid, input_lang: 'en', output_lang: 'zh' }),
    ).toThrow();
  });

  it('rejects empty system_prompt', () => {
    expect(() => MtProfileSchema.parse({ ...valid, system_prompt: '' })).toThrow();
  });
});
