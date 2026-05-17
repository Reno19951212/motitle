import { describe, it, expect } from 'vitest';
import { LoginSchema, CreateUserSchema } from './user';

describe('LoginSchema', () => {
  it('accepts valid login payload', () => {
    const r = LoginSchema.parse({ username: 'admin', password: 'pw' });
    expect(r.username).toBe('admin');
  });

  it('accepts username at max length 64', () => {
    const r = LoginSchema.parse({ username: 'a'.repeat(64), password: 'p' });
    expect(r.username.length).toBe(64);
  });

  it('rejects empty username', () => {
    expect(() => LoginSchema.parse({ username: '', password: 'pw' })).toThrow();
  });

  it('rejects empty password', () => {
    expect(() => LoginSchema.parse({ username: 'admin', password: '' })).toThrow();
  });

  it('rejects username longer than 64 chars', () => {
    expect(() => LoginSchema.parse({ username: 'a'.repeat(65), password: 'pw' })).toThrow();
  });
});

describe('CreateUserSchema', () => {
  const valid = { username: 'alice_99', password: 'TestPass1!' };

  it('accepts valid user payload', () => {
    const r = CreateUserSchema.parse(valid);
    expect(r.username).toBe('alice_99');
    expect(r.is_admin).toBe(false);
  });

  it('accepts is_admin=true', () => {
    const r = CreateUserSchema.parse({ ...valid, is_admin: true });
    expect(r.is_admin).toBe(true);
  });

  it('rejects username with invalid characters', () => {
    expect(() => CreateUserSchema.parse({ ...valid, username: 'has space' })).toThrow();
    expect(() => CreateUserSchema.parse({ ...valid, username: 'tom@example' })).toThrow();
  });

  it('rejects username shorter than 3 chars', () => {
    expect(() => CreateUserSchema.parse({ ...valid, username: 'ab' })).toThrow();
  });

  it('rejects password shorter than 8 chars', () => {
    expect(() => CreateUserSchema.parse({ ...valid, password: 'short' })).toThrow();
  });

  it('rejects password longer than 128 chars', () => {
    expect(() => CreateUserSchema.parse({ ...valid, password: 'p'.repeat(129) })).toThrow();
  });
});
