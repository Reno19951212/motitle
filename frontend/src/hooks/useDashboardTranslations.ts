// src/hooks/useDashboardTranslations.ts
// Boundary adapter that powers the Dashboard live overlay + inspector preview.
// Fetches v5 by_lang translations and falls back to the raw /segments endpoint
// when translations are empty (v4 files, ASR-only files, files not re-run).
import { useEffect, useMemo, useState } from 'react';
import { apiFetch } from '@/lib/api';
import * as v5 from '@/lib/api/v5';
import type { V5Translation } from '@/lib/api/v5';

export interface SegmentPreview {
  start: number;
  end: number;
  text: string;
}

interface SegmentsResponse {
  id: string;
  status: string;
  segments: SegmentPreview[];
  text: string;
}

interface HookResult {
  segments: SegmentPreview[];
  availableLangs: string[];
  sourceLang: string | null;
  loading: boolean;
}

const EMPTY_RESULT: HookResult = {
  segments: [],
  availableLangs: [],
  sourceLang: null,
  loading: false,
};

function deriveForLang(rows: V5Translation[], activeLang: string): SegmentPreview[] {
  return rows.map((r) => ({
    start: r.start,
    end: r.end,
    text: r.by_lang[activeLang]?.text || r.source_text,
  }));
}

export function useDashboardTranslations(
  fileId: string | null,
  activeLang: string,
): HookResult {
  const [v5rows, setV5rows] = useState<V5Translation[]>([]);
  const [rawSegments, setRawSegments] = useState<SegmentPreview[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!fileId) {
      setV5rows([]);
      setRawSegments([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all([
      v5.getTranslations(fileId).catch(() => [] as V5Translation[]),
      apiFetch<SegmentsResponse>(`/api/files/${fileId}/segments`).catch(
        () => ({ id: fileId, status: '', segments: [], text: '' } as SegmentsResponse),
      ),
    ]).then(([translations, segmentsResp]) => {
      if (cancelled) return;
      setV5rows(translations ?? []);
      setRawSegments(segmentsResp.segments ?? []);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [fileId]);

  const availableLangs = useMemo(() => {
    const set = new Set<string>();
    for (const r of v5rows) for (const k of Object.keys(r.by_lang)) set.add(k);
    return Array.from(set).sort();
  }, [v5rows]);

  const sourceLang = v5rows[0]?.source_lang ?? null;

  const segments = useMemo(() => {
    if (v5rows.length > 0) return deriveForLang(v5rows, activeLang);
    return rawSegments;
  }, [v5rows, rawSegments, activeLang]);

  if (!fileId) return EMPTY_RESULT;
  return { segments, availableLangs, sourceLang, loading };
}
