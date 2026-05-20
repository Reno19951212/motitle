// src/pages/Proofread/hooks/useFileData.ts
// v5-A3 — fetches translations from /api/files/<id>/translations?shape=v5
// and derives the v4-shape Translation[] for the active target language so
// downstream components keep their existing zh_text/en_text contract.
import { useCallback, useEffect, useState, useMemo } from 'react';
import { apiFetch } from '@/lib/api';
import * as v5 from '@/lib/api/v5';
import type { V5Translation } from '@/lib/api/v5';
import type { FileDetail, Segment, Translation } from '../types';

interface SegmentsResponse {
  id: string;
  status: string;
  segments: Segment[];
  text: string;
}

// For ASR-only pipelines (mt_stages: []) the backend produces segments but
// zero translations. Synthesize a 1:1 "translation" per segment so the
// Proofread editor renders the ASR text as the editable subtitle line.
function synthesizeTranslationsFromSegments(segments: Segment[]): Translation[] {
  return segments.map((s, i) => ({
    idx: i,
    en_text: s.text,
    zh_text: s.text,
    status: 'pending' as const,
    flags: [],
    start: s.start,
    end: s.end,
  }));
}

function deriveForLang(v5rows: V5Translation[], activeLang: string): Translation[] {
  return v5rows.map((r) => {
    const entry = r.by_lang[activeLang];
    return {
      idx: r.idx,
      en_text: r.source_text,
      zh_text: entry?.text ?? '',
      // Coerce arbitrary status string back to the v4 enum the rest of the UI expects.
      status: (entry?.status as Translation['status']) ?? 'pending',
      flags: entry?.flags ?? [],
      start: r.start,
      end: r.end,
    };
  });
}

export function useFileData(fileId: string, activeLang: string) {
  const [file, setFile] = useState<FileDetail | null>(null);
  const [v5rows, setV5rows] = useState<V5Translation[]>([]);
  const [synthesized, setSynthesized] = useState<Translation[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [f, t, s] = await Promise.all([
        apiFetch<FileDetail>(`/api/files/${fileId}`),
        v5.getTranslations(fileId),
        apiFetch<SegmentsResponse>(`/api/files/${fileId}/segments`),
      ]);
      setFile(f);
      const real = t ?? [];
      setV5rows(real);
      if (real.length === 0) {
        setSynthesized(synthesizeTranslationsFromSegments(s.segments ?? []));
      } else {
        setSynthesized(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [fileId]);

  useEffect(() => { refresh(); }, [refresh]);

  // Available langs across all v5 rows (union of by_lang keys).
  const availableLangs = useMemo(() => {
    const set = new Set<string>();
    for (const r of v5rows) for (const k of Object.keys(r.by_lang)) set.add(k);
    return Array.from(set).sort();
  }, [v5rows]);

  // Source lang (first row wins — all rows share the same source per v5 contract).
  const sourceLang = v5rows[0]?.source_lang ?? null;

  // Derived v4-shape Translation[] for the active lang.
  const translations = useMemo(() => {
    if (synthesized) return synthesized;
    return deriveForLang(v5rows, activeLang);
  }, [v5rows, synthesized, activeLang]);

  return {
    file,
    translations,
    availableLangs,
    sourceLang,
    loading,
    error,
    refresh,
  };
}
