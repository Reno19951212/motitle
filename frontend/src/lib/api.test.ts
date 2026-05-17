import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiFetch, ApiError, UnauthorizedError } from './api';

describe('apiFetch', () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it('returns parsed JSON on 200', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    );
    const data = await apiFetch('/api/health');
    expect(data).toEqual({ ok: true });
  });

  it('throws UnauthorizedError on 401', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(new Response('', { status: 401 }));
    await expect(apiFetch('/api/me')).rejects.toBeInstanceOf(UnauthorizedError);
  });

  it('throws ApiError on 4xx with parsed error payload', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ error: 'bad input' }), { status: 400, headers: { 'Content-Type': 'application/json' } })
    );
    try {
      await apiFetch('/api/whatever');
      throw new Error('should have thrown');
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).message).toBe('bad input');
      expect((e as ApiError).status).toBe(400);
    }
  });

  it('always includes credentials: include', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
    );
    await apiFetch('/api/anything');
    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    expect(init.credentials).toBe('include');
  });
});
