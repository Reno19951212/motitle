import { describe, it, expect } from 'vitest';
import { TranscribeProfileSchema } from './transcribe-profile';

describe('TranscribeProfileSchema', () => {
  it('accepts a qwen3-asr profile with default language=auto', () => {
    const r = TranscribeProfileSchema.parse({
      name: 'Qwen3 ASR',
      engine: 'qwen3-asr',
    });
    expect(r.engine).toBe('qwen3-asr');
    expect(r.language).toBe('auto');
    expect(r.shared).toBe(false);
  });

  it('accepts whisper with explicit language + model_size', () => {
    const r = TranscribeProfileSchema.parse({
      name: 'Whisper EN',
      engine: 'whisper',
      language: 'en',
      model_size: 'large-v3',
    });
    expect(r.engine).toBe('whisper');
    expect(r.language).toBe('en');
    expect(r.model_size).toBe('large-v3');
  });

  it('rejects unknown engine', () => {
    expect(() => TranscribeProfileSchema.parse({
      name: 'X',
      engine: 'sensevoice',
    })).toThrow();
  });

  it('rejects initial_prompt > 512 chars', () => {
    expect(() => TranscribeProfileSchema.parse({
      name: 'X',
      engine: 'whisper',
      initial_prompt: 'x'.repeat(513),
    })).toThrow();
  });
});
