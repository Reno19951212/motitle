// src/pages/Proofread/hooks/useFileData.ts
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
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

export function useFileData(fileId: string) {
  const [file, setFile] = useState<FileDetail | null>(null);
  const [translations, setTranslations] = useState<Translation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [f, t, s] = await Promise.all([
        apiFetch<FileDetail>(`/api/files/${fileId}`),
        apiFetch<{ translations: Translation[] }>(`/api/files/${fileId}/translations`),
        apiFetch<SegmentsResponse>(`/api/files/${fileId}/segments`),
      ]);
      setFile(f);
      const real = t.translations ?? [];
      setTranslations(
        real.length > 0 ? real : synthesizeTranslationsFromSegments(s.segments ?? []),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [fileId]);

  useEffect(() => { refresh(); }, [refresh]);

  return { file, translations, loading, error, refresh };
}
