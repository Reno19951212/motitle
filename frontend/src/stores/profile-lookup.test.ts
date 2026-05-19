import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useProfileLookupStore } from './profile-lookup';

beforeEach(() => {
  useProfileLookupStore.getState()._reset();
  vi.restoreAllMocks();
});

function mockFetchOnce(payload: unknown, status = 200) {
  vi.spyOn(global, 'fetch').mockResolvedValueOnce(
    new Response(JSON.stringify(payload), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

describe('useProfileLookupStore', () => {
  it('starts empty', () => {
    const s = useProfileLookupStore.getState();
    expect(s.asrProfiles).toEqual({});
    expect(s.mtProfiles).toEqual({});
    expect(s.glossaries).toEqual({});
    expect(s.pipelines).toEqual({});
  });

  it('fetchAsr stores resolved profile + does not refetch on subsequent calls', async () => {
    mockFetchOnce({
      id: 'a1',
      name: 'Whisper EN',
      engine: 'whisper',
      model_size: 'large-v3',
      mode: 'same-lang',
      language: 'en',
      device: 'auto',
    });
    const first = await useProfileLookupStore.getState().fetchAsr('a1');
    expect(first?.name).toBe('Whisper EN');
    expect(useProfileLookupStore.getState().asrProfiles['a1']?.name).toBe('Whisper EN');

    // Second call should hit cache, NOT fetch again — global.fetch was mocked
    // exactly once, so a second fetch would throw.
    const second = await useProfileLookupStore.getState().fetchAsr('a1');
    expect(second?.name).toBe('Whisper EN');
  });

  it('fetchMt resolves MT profile shape', async () => {
    mockFetchOnce({
      id: 'm1',
      name: 'Qwen MT',
      engine: 'qwen3.5-35b-a3b',
      input_lang: 'en',
      output_lang: 'zh',
    });
    const r = await useProfileLookupStore.getState().fetchMt('m1');
    expect(r?.output_lang).toBe('zh');
  });

  it('fetchGlossary resolves glossary shape', async () => {
    mockFetchOnce({
      id: 'g1',
      name: 'Broadcast',
      source_lang: 'en',
      target_lang: 'zh',
      entries: [],
    });
    const r = await useProfileLookupStore.getState().fetchGlossary('g1');
    expect(r?.name).toBe('Broadcast');
  });

  it('fetchPipeline resolves nested pipeline shape including font_config', async () => {
    mockFetchOnce({
      id: 'p1',
      name: 'News TC',
      asr_profile_id: 'a1',
      mt_stages: ['m1', 'm2'],
      glossary_stage: { enabled: true, glossary_ids: ['g1'] },
      font_config: {
        family: 'Noto Sans TC',
        color: '#FFF',
        outline_color: '#000',
        size: 36,
        outline_width: 2,
        margin_bottom: 80,
        subtitle_source: 'auto',
        bilingual_order: 'source_top',
      },
    });
    const r = await useProfileLookupStore.getState().fetchPipeline('p1');
    expect(r?.mt_stages).toEqual(['m1', 'm2']);
    expect(r?.glossary_stage.enabled).toBe(true);
    expect(r?.font_config.family).toBe('Noto Sans TC');
  });

  it('fetchAsr on 404 caches null and does not refetch', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ error: 'not found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const r = await useProfileLookupStore.getState().fetchAsr('missing');
    expect(r).toBeNull();
    expect(useProfileLookupStore.getState().asrProfiles['missing']).toBeNull();

    // Second call: no second mock registered → if a refetch happened it would
    // throw. Should just resolve to null from cache.
    const r2 = await useProfileLookupStore.getState().fetchAsr('missing');
    expect(r2).toBeNull();
  });

  it('forceRefetchAsr re-issues fetch even if cached', async () => {
    mockFetchOnce({
      id: 'a1',
      name: 'Original',
      engine: 'whisper',
      model_size: 'large-v3',
      mode: 'same-lang',
      language: 'en',
      device: 'auto',
    });
    await useProfileLookupStore.getState().fetchAsr('a1');
    expect(useProfileLookupStore.getState().asrProfiles['a1']?.name).toBe('Original');

    mockFetchOnce({
      id: 'a1',
      name: 'Updated',
      engine: 'whisper',
      model_size: 'large-v3',
      mode: 'same-lang',
      language: 'en',
      device: 'auto',
    });
    await useProfileLookupStore.getState().forceRefetchAsr('a1');
    expect(useProfileLookupStore.getState().asrProfiles['a1']?.name).toBe('Updated');
  });

  it('empty id is a no-op (returns null, does not fetch)', async () => {
    const spy = vi.spyOn(global, 'fetch');
    const r = await useProfileLookupStore.getState().fetchAsr('');
    expect(r).toBeNull();
    expect(spy).not.toHaveBeenCalled();
  });
});
