// Profile-lookup cache — Batch F + B (shared)
// ---------------------------------------------------------------------------
// Resolves ASR profile / MT profile / Glossary / Pipeline IDs into the full
// entity dicts so other components don't have to inline `apiFetch` and don't
// re-fetch the same id repeatedly across renders.
//
// Cache values:
//   undefined  → never requested (call `fetchAsr(id)` etc. to kick off)
//   null       → request in flight OR resolved-to-null (404/403/network).
//                Once null is recorded for a 4xx/network error we DO NOT
//                refetch (would hammer the server). A successful refetch is
//                still possible via `forceRefetch*` if a caller knows the
//                data has actually changed (e.g. after PATCH).
//   <object>   → resolved entity
//
// Field shapes mirror the backend exactly (flat — no `.asr.engine` nesting):
//   AsrProfile: { id, name, engine, model_size, mode, language, device, ... }
//   MtProfile:  { id, name, engine, input_lang, output_lang, ... }
//   Glossary:   { id, name, source_lang, target_lang, entries[], ... }
//   Pipeline:   { id, name, asr_profile_id, mt_stages[], glossary_stage,
//                 font_config, broken_refs? }
//
// `forceRefetch*` re-issues the fetch even if a value is already cached. Used
// when we know the entity changed (e.g. after a PATCH from /pipelines page).
// ---------------------------------------------------------------------------
import { create } from 'zustand';
import { apiFetch, ApiError } from '@/lib/api';

export interface AsrProfileLookup {
  id: string;
  name: string;
  engine: string;
  model_size: string;
  mode: string;
  language: string;
  device: string;
  initial_prompt?: string;
  condition_on_previous_text?: boolean;
  simplified_to_traditional?: boolean;
  shared?: boolean;
  user_id?: number | null;
  description?: string;
}

export interface MtProfileLookup {
  id: string;
  name: string;
  engine: string;
  input_lang: string;
  output_lang: string;
  batch_size?: number;
  temperature?: number;
  parallel_batches?: number;
  shared?: boolean;
  user_id?: number | null;
  description?: string;
}

export interface GlossaryLookup {
  id: string;
  name: string;
  source_lang: string;
  target_lang: string;
  description?: string;
  shared?: boolean;
  user_id?: number | null;
  entry_count?: number;
}

export interface PipelineFontConfig {
  family: string;
  color: string;
  outline_color: string;
  size: number;
  outline_width: number;
  margin_bottom: number;
  subtitle_source: string;
  bilingual_order: string;
}

export interface GlossaryStageConfig {
  enabled: boolean;
  glossary_ids?: string[];
  apply_order?: string;
  apply_method?: string;
}

export interface PipelineLookup {
  id: string;
  name: string;
  description?: string;
  shared?: boolean;
  user_id?: number | null;
  asr_profile_id: string;
  mt_stages: string[];
  glossary_stage: GlossaryStageConfig;
  font_config: PipelineFontConfig;
  broken_refs?: {
    asr_profile_id?: string;
    mt_stages?: string[];
    glossary_ids?: string[];
  };
}

interface LookupState {
  asrProfiles: Record<string, AsrProfileLookup | null | undefined>;
  mtProfiles: Record<string, MtProfileLookup | null | undefined>;
  glossaries: Record<string, GlossaryLookup | null | undefined>;
  pipelines: Record<string, PipelineLookup | null | undefined>;

  fetchAsr: (id: string) => Promise<AsrProfileLookup | null>;
  fetchMt: (id: string) => Promise<MtProfileLookup | null>;
  fetchGlossary: (id: string) => Promise<GlossaryLookup | null>;
  fetchPipeline: (id: string) => Promise<PipelineLookup | null>;

  forceRefetchAsr: (id: string) => Promise<AsrProfileLookup | null>;
  forceRefetchMt: (id: string) => Promise<MtProfileLookup | null>;
  forceRefetchGlossary: (id: string) => Promise<GlossaryLookup | null>;
  forceRefetchPipeline: (id: string) => Promise<PipelineLookup | null>;

  /** Test-only: drop all cached entries. */
  _reset: () => void;
}

/** Generic fetcher with cache check. `null` already in cache → skip refetch. */
async function cachedFetch<T>(
  current: Record<string, T | null | undefined>,
  id: string,
  url: string,
  setEntry: (id: string, val: T | null) => void,
): Promise<T | null> {
  if (!id) return null;
  // Already resolved (truthy) → return cached.
  const cached = current[id];
  if (cached) return cached;
  // Already attempted (null) → don't refetch.
  if (cached === null) return null;

  // Mark as in-flight (null) so concurrent callers don't fire duplicate
  // requests. Note: this is a deliberate UX tradeoff — a network failure
  // pins the id at `null` until forceRefetch or _reset is called.
  setEntry(id, null);
  try {
    const result = await apiFetch<T>(url);
    setEntry(id, result);
    return result;
  } catch (e) {
    // 4xx/network — keep null cached to avoid hammering.
    void e;
    if (e instanceof ApiError && e.status === 401) {
      // 401 is special: the auth layer will redirect to /login. Don't poison
      // the cache (let a post-login retry succeed).
      setEntry(id, undefined as unknown as T | null);
    }
    return null;
  }
}

async function forceFetch<T>(
  id: string,
  url: string,
  setEntry: (id: string, val: T | null) => void,
): Promise<T | null> {
  if (!id) return null;
  setEntry(id, null);
  try {
    const result = await apiFetch<T>(url);
    setEntry(id, result);
    return result;
  } catch {
    return null;
  }
}

export const useProfileLookupStore = create<LookupState>()((set, get) => ({
  asrProfiles: {},
  mtProfiles: {},
  glossaries: {},
  pipelines: {},

  fetchAsr: (id) =>
    cachedFetch(get().asrProfiles, id, `/api/transcribe_profiles/${encodeURIComponent(id)}`, (k, v) =>
      set((s) => ({ asrProfiles: { ...s.asrProfiles, [k]: v } })),
    ),
  fetchMt: (id) =>
    cachedFetch(get().mtProfiles, id, `/api/refiner_profiles/${encodeURIComponent(id)}`, (k, v) =>
      set((s) => ({ mtProfiles: { ...s.mtProfiles, [k]: v } })),
    ),
  fetchGlossary: (id) =>
    cachedFetch(get().glossaries, id, `/api/glossaries/${encodeURIComponent(id)}`, (k, v) =>
      set((s) => ({ glossaries: { ...s.glossaries, [k]: v } })),
    ),
  fetchPipeline: (id) =>
    cachedFetch(get().pipelines, id, `/api/pipelines/${encodeURIComponent(id)}`, (k, v) =>
      set((s) => ({ pipelines: { ...s.pipelines, [k]: v } })),
    ),

  forceRefetchAsr: (id) =>
    forceFetch(id, `/api/transcribe_profiles/${encodeURIComponent(id)}`, (k, v) =>
      set((s) => ({ asrProfiles: { ...s.asrProfiles, [k]: v } })),
    ),
  forceRefetchMt: (id) =>
    forceFetch(id, `/api/refiner_profiles/${encodeURIComponent(id)}`, (k, v) =>
      set((s) => ({ mtProfiles: { ...s.mtProfiles, [k]: v } })),
    ),
  forceRefetchGlossary: (id) =>
    forceFetch(id, `/api/glossaries/${encodeURIComponent(id)}`, (k, v) =>
      set((s) => ({ glossaries: { ...s.glossaries, [k]: v } })),
    ),
  forceRefetchPipeline: (id) =>
    forceFetch(id, `/api/pipelines/${encodeURIComponent(id)}`, (k, v) =>
      set((s) => ({ pipelines: { ...s.pipelines, [k]: v } })),
    ),

  _reset: () => set({ asrProfiles: {}, mtProfiles: {}, glossaries: {}, pipelines: {} }),
}));
