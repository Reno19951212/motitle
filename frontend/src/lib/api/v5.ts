/**
 * v5 API client — typed wrappers around the 30 v5 REST calls.
 *
 * Uses raw global.fetch (not the v4 `apiFetch` wrapper) — keeps the v5
 * surface independently testable and lets future v5-A4 wire it into a new
 * (e.g. tanstack-query) client without inheriting v4 plumbing.
 */
import type { LlmProfile, LlmProfileRow } from '../schemas/llm-profile';
import type { TranscribeProfile, TranscribeProfileRow } from '../schemas/transcribe-profile';
import type { TranslatorProfile, TranslatorProfileRow } from '../schemas/translator-profile';
import type { RefinerProfile, RefinerProfileRow } from '../schemas/refiner-profile';
import type { VerifierProfile, VerifierProfileRow } from '../schemas/verifier-profile';
import type { PipelineV5, PipelineV5Row } from '../schemas/pipeline-v5';

// ---------------------------------------------------------------------------
// Private fetch helpers
// ---------------------------------------------------------------------------

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    ...init,
  });
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      try {
        detail = await res.text();
      } catch {
        detail = null;
      }
    }
    const message =
      detail && typeof detail === 'object' && 'error' in detail
        ? String((detail as { error: unknown }).error)
        : `HTTP ${res.status}`;
    const err = new Error(message) as Error & { status: number; detail: unknown };
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  return (await res.json()) as T;
}

async function jsonPost<T>(path: string, body: unknown): Promise<T> {
  return fetchJson<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

async function jsonPatch<T>(path: string, body: unknown): Promise<T> {
  return fetchJson<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

async function httpDelete<T>(path: string): Promise<T> {
  return fetchJson<T>(path, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// LLM profiles
// ---------------------------------------------------------------------------

export async function getLlmProfiles(): Promise<LlmProfileRow[]> {
  const r = await fetchJson<{ profiles: LlmProfileRow[] }>('/api/llm_profiles');
  return r.profiles;
}

export function createLlmProfile(p: LlmProfile): Promise<LlmProfileRow> {
  return jsonPost<LlmProfileRow>('/api/llm_profiles', p);
}

export function updateLlmProfile(id: string, patch: Partial<LlmProfile>): Promise<LlmProfileRow> {
  return jsonPatch<LlmProfileRow>(`/api/llm_profiles/${id}`, patch);
}

export function deleteLlmProfile(id: string): Promise<{ deleted: string }> {
  return httpDelete<{ deleted: string }>(`/api/llm_profiles/${id}`);
}

// ---------------------------------------------------------------------------
// Transcribe profiles
// ---------------------------------------------------------------------------

export async function getTranscribeProfiles(): Promise<TranscribeProfileRow[]> {
  const r = await fetchJson<{ profiles: TranscribeProfileRow[] }>('/api/transcribe_profiles');
  return r.profiles;
}

export function createTranscribeProfile(p: TranscribeProfile): Promise<TranscribeProfileRow> {
  return jsonPost<TranscribeProfileRow>('/api/transcribe_profiles', p);
}

export function updateTranscribeProfile(
  id: string,
  patch: Partial<TranscribeProfile>,
): Promise<TranscribeProfileRow> {
  return jsonPatch<TranscribeProfileRow>(`/api/transcribe_profiles/${id}`, patch);
}

export function deleteTranscribeProfile(id: string): Promise<{ deleted: string }> {
  return httpDelete<{ deleted: string }>(`/api/transcribe_profiles/${id}`);
}

// ---------------------------------------------------------------------------
// Translator profiles
// ---------------------------------------------------------------------------

export async function getTranslatorProfiles(): Promise<TranslatorProfileRow[]> {
  const r = await fetchJson<{ profiles: TranslatorProfileRow[] }>('/api/translator_profiles');
  return r.profiles;
}

export function createTranslatorProfile(p: TranslatorProfile): Promise<TranslatorProfileRow> {
  return jsonPost<TranslatorProfileRow>('/api/translator_profiles', p);
}

export function updateTranslatorProfile(
  id: string,
  patch: Partial<TranslatorProfile>,
): Promise<TranslatorProfileRow> {
  return jsonPatch<TranslatorProfileRow>(`/api/translator_profiles/${id}`, patch);
}

export function deleteTranslatorProfile(id: string): Promise<{ deleted: string }> {
  return httpDelete<{ deleted: string }>(`/api/translator_profiles/${id}`);
}

// ---------------------------------------------------------------------------
// Refiner profiles
// ---------------------------------------------------------------------------

export async function getRefinerProfiles(): Promise<RefinerProfileRow[]> {
  const r = await fetchJson<{ profiles: RefinerProfileRow[] }>('/api/refiner_profiles');
  return r.profiles;
}

export function createRefinerProfile(p: RefinerProfile): Promise<RefinerProfileRow> {
  return jsonPost<RefinerProfileRow>('/api/refiner_profiles', p);
}

export function updateRefinerProfile(
  id: string,
  patch: Partial<RefinerProfile>,
): Promise<RefinerProfileRow> {
  return jsonPatch<RefinerProfileRow>(`/api/refiner_profiles/${id}`, patch);
}

export function deleteRefinerProfile(id: string): Promise<{ deleted: string }> {
  return httpDelete<{ deleted: string }>(`/api/refiner_profiles/${id}`);
}

// ---------------------------------------------------------------------------
// Verifier profiles
// ---------------------------------------------------------------------------

export async function getVerifierProfiles(): Promise<VerifierProfileRow[]> {
  const r = await fetchJson<{ profiles: VerifierProfileRow[] }>('/api/verifier_profiles');
  return r.profiles;
}

export function createVerifierProfile(p: VerifierProfile): Promise<VerifierProfileRow> {
  return jsonPost<VerifierProfileRow>('/api/verifier_profiles', p);
}

export function updateVerifierProfile(
  id: string,
  patch: Partial<VerifierProfile>,
): Promise<VerifierProfileRow> {
  return jsonPatch<VerifierProfileRow>(`/api/verifier_profiles/${id}`, patch);
}

export function deleteVerifierProfile(id: string): Promise<{ deleted: string }> {
  return httpDelete<{ deleted: string }>(`/api/verifier_profiles/${id}`);
}

// ---------------------------------------------------------------------------
// v5 pipeline create + run
// ---------------------------------------------------------------------------

export function createPipelineV5(p: PipelineV5): Promise<PipelineV5Row> {
  return jsonPost<PipelineV5Row>('/api/pipelines', p);
}

export function patchPipeline(
  id: string,
  patch: Record<string, unknown>,
): Promise<PipelineV5Row> {
  return jsonPatch<PipelineV5Row>(`/api/pipelines/${id}`, patch);
}

export function getPipeline(id: string): Promise<PipelineV5Row> {
  return fetchJson<PipelineV5Row>(`/api/pipelines/${id}`);
}

export function runPipeline(
  pipelineId: string,
  fileId: string,
): Promise<{ job_id: string }> {
  return jsonPost<{ job_id: string }>(`/api/pipelines/${pipelineId}/run`, {
    file_id: fileId,
  });
}

// ---------------------------------------------------------------------------
// v5 translations (always ?shape=v5 so client sees by_lang shape)
// ---------------------------------------------------------------------------

export interface V5TranslationByLangEntry {
  text: string;
  status: 'pending' | 'approved';
  flags: string[];
}

export interface V5Translation {
  idx: number;
  start: number;
  end: number;
  source_lang: string;
  source_text: string;
  by_lang: Record<string, V5TranslationByLangEntry>;
}

export async function getTranslations(fileId: string): Promise<V5Translation[]> {
  const r = await fetchJson<{ translations: V5Translation[] }>(
    `/api/files/${fileId}/translations?shape=v5`,
  );
  return r.translations;
}
