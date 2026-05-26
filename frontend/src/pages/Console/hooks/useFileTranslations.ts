import { useEffect, useState } from 'react';
import { apiFetch } from '../../../lib/api';

// Subset of the Proofread Translation shape — the only fields the Console
// overlay consumes. Backend returns more (status, flags, idx, etc.) but
// Console doesn't render them. Kept narrow on purpose so this hook stays
// thin and the Console subtree doesn't pull the Proofread type graph.
export interface ConsoleTranslation {
  start?: number;
  end?: number;
  en_text: string;
  zh_text: string;
}

// Backend may return either a bare array (v4 shape) or {translations:[...]}
// envelope. Probe both — useFileData in Proofread does the same shape dance.
function unwrap(raw: unknown): ConsoleTranslation[] {
  if (Array.isArray(raw)) return raw as ConsoleTranslation[];
  if (raw && typeof raw === 'object' && Array.isArray((raw as { translations?: unknown }).translations)) {
    return (raw as { translations: ConsoleTranslation[] }).translations;
  }
  return [];
}

export function useFileTranslations(fileId: string | null) {
  const [translations, setTranslations] = useState<ConsoleTranslation[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!fileId) { setTranslations([]); return; }
    let cancelled = false;
    setLoading(true);
    apiFetch<unknown>(`/api/files/${fileId}/translations`)
      .then(raw => { if (!cancelled) setTranslations(unwrap(raw)); })
      .catch(() => { if (!cancelled) setTranslations([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fileId]);

  return { translations, loading };
}

// Linear lookup is fine — typical file is <500 segments and called only on
// timeupdate (~4/sec on Chrome). Memoize at caller via useMemo if needed.
export function findActiveTranslation(
  translations: ConsoleTranslation[],
  currentTime: number,
): ConsoleTranslation | undefined {
  for (const t of translations) {
    if (t.start === undefined || t.end === undefined) continue;
    if (currentTime >= t.start && currentTime < t.end) return t;
  }
  return undefined;
}
