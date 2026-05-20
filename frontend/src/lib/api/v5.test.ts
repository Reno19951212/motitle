import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as v5 from './v5';

type FetchMock = ReturnType<typeof vi.fn>;

function mockFetchOnce(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  const ok = init.ok ?? true;
  const status = init.status ?? (ok ? 200 : 500);
  return {
    ok,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

describe('v5 API client', () => {
  let originalFetch: typeof globalThis.fetch;
  let fetchMock: FetchMock;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('getLlmProfiles GETs /api/llm_profiles with credentials and unwraps envelope', async () => {
    fetchMock.mockResolvedValueOnce(mockFetchOnce({ profiles: [{ id: 'llm-1', name: 'X' }] }));
    const r = await v5.getLlmProfiles();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchMock.mock.calls[0]!;
    const [url, init] = call as [string, RequestInit | undefined];
    expect(url).toBe('/api/llm_profiles');
    expect(init?.credentials).toBe('include');
    expect(r).toEqual([{ id: 'llm-1', name: 'X' }]);
  });

  it('createTranscribeProfile POSTs JSON to /api/transcribe_profiles', async () => {
    fetchMock.mockResolvedValueOnce(mockFetchOnce({ id: 't-1' }));
    const payload = {
      name: 'X',
      engine: 'whisper' as const,
      language: 'auto' as const,
      shared: false,
    };
    const r = await v5.createTranscribeProfile(payload);
    const call = fetchMock.mock.calls[0]!;
    const [url, init] = call as [string, RequestInit | undefined];
    expect(url).toBe('/api/transcribe_profiles');
    expect(init?.method).toBe('POST');
    expect(init?.headers).toMatchObject({ 'Content-Type': 'application/json' });
    expect(init?.body).toBe(JSON.stringify(payload));
    expect(init?.credentials).toBe('include');
    expect(r).toEqual({ id: 't-1' });
  });

  it('getTranslations passes shape=v5 query and unwraps {translations}', async () => {
    fetchMock.mockResolvedValueOnce(mockFetchOnce({ translations: [], file_id: 'file-abc' }));
    const r = await v5.getTranslations('file-abc');
    const call = fetchMock.mock.calls[0]!;
    const [url] = call as [string, RequestInit | undefined];
    expect(url).toBe('/api/files/file-abc/translations?shape=v5');
    expect(r).toEqual([]);
  });

  it('runPipeline POSTs file_id to /api/pipelines/:id/run', async () => {
    fetchMock.mockResolvedValueOnce(mockFetchOnce({ job_id: 'j-1' }));
    const r = await v5.runPipeline('pipe-1', 'file-1');
    const call = fetchMock.mock.calls[0]!;
    const [url, init] = call as [string, RequestInit | undefined];
    expect(url).toBe('/api/pipelines/pipe-1/run');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(JSON.stringify({ file_id: 'file-1' }));
    expect(r).toEqual({ job_id: 'j-1' });
  });

  it('updateLlmProfile PATCHes to /api/llm_profiles/<id>', async () => {
    fetchMock.mockResolvedValueOnce(mockFetchOnce({ id: 'llm-1', name: 'updated' }));
    const result = await v5.updateLlmProfile('llm-1', { name: 'updated' });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/llm_profiles/llm-1',
      expect.objectContaining({
        method: 'PATCH',
        credentials: 'include',
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    );
    expect(result.id).toBe('llm-1');
  });

  it('deleteTranscribeProfile DELETEs and returns {deleted}', async () => {
    fetchMock.mockResolvedValueOnce(mockFetchOnce({ deleted: 'tp-1' }));
    const result = await v5.deleteTranscribeProfile('tp-1');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/transcribe_profiles/tp-1',
      expect.objectContaining({ method: 'DELETE', credentials: 'include' }),
    );
    expect(result.deleted).toBe('tp-1');
  });

  it('throws on non-ok HTTP with server error message', async () => {
    fetchMock.mockResolvedValueOnce(
      mockFetchOnce({ error: 'validation failed' }, { ok: false, status: 400 }),
    );
    await expect(v5.getLlmProfiles()).rejects.toThrow(/validation failed/);
  });
});
