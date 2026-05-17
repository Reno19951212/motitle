import { describe, it, expect } from 'vitest';
import { AsrProfileSchema } from './asr-profile';

describe('AsrProfileSchema', () => {
  const valid = {
    name: 'Test',
    engine: 'whisper' as const,
    mode: 'same-lang' as const,
    language: 'en' as const,
  };

  it('accepts minimal valid payload', () => {
    const r = AsrProfileSchema.parse(valid);
    expect(r.name).toBe('Test');
    expect(r.model_size).toBe('large-v3');
    expect(r.device).toBe('auto');
    expect(r.shared).toBe(false);
  });

  it('accepts full valid payload with all optional fields', () => {
    const r = AsrProfileSchema.parse({
      ...valid,
      description: 'desc',
      shared: true,
      initial_prompt: 'p',
      simplified_to_traditional: true,
      condition_on_previous_text: false,
      device: 'cuda',
    });
    expect(r.initial_prompt).toBe('p');
    expect(r.device).toBe('cuda');
    expect(r.simplified_to_traditional).toBe(true);
  });

  it('accepts mlx-whisper engine', () => {
    const r = AsrProfileSchema.parse({ ...valid, engine: 'mlx-whisper' });
    expect(r.engine).toBe('mlx-whisper');
  });

  it('rejects empty name', () => {
    expect(() => AsrProfileSchema.parse({ ...valid, name: '' })).toThrow();
  });

  it('rejects unknown engine', () => {
    expect(() => AsrProfileSchema.parse({ ...valid, engine: 'fake' })).toThrow();
  });

  it('rejects model_size != large-v3', () => {
    expect(() => AsrProfileSchema.parse({ ...valid, model_size: 'medium' })).toThrow();
  });

  it('rejects unknown mode', () => {
    expect(() => AsrProfileSchema.parse({ ...valid, mode: 'bogus' })).toThrow();
  });

  it('rejects unknown language', () => {
    expect(() => AsrProfileSchema.parse({ ...valid, language: 'xx' })).toThrow();
  });

  it('rejects name longer than 64 chars', () => {
    expect(() => AsrProfileSchema.parse({ ...valid, name: 'x'.repeat(65) })).toThrow();
  });
});
