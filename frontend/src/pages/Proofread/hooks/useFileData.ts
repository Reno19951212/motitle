// src/pages/Proofread/hooks/useFileData.ts
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import type { FileDetail, Translation } from '../types';

export function useFileData(fileId: string) {
  const [file, setFile] = useState<FileDetail | null>(null);
  const [translations, setTranslations] = useState<Translation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [f, t] = await Promise.all([
        apiFetch<FileDetail>(`/api/files/${fileId}`),
        apiFetch<{ translations: Translation[] }>(`/api/files/${fileId}/translations`),
      ]);
      setFile(f);
      setTranslations(t.translations ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [fileId]);

  useEffect(() => { refresh(); }, [refresh]);

  return { file, translations, loading, error, refresh };
}
