// src/pages/Proofread/hooks/useFindReplace.ts
import { useCallback, useMemo, useState } from 'react';
import type { Translation } from '../types';

export type FindScope = 'zh' | 'en' | 'both' | 'pending';

export interface FindMatch {
  idx: number;       // translation idx
  field: 'zh' | 'en';
}

export interface Replacement {
  idx: number;
  field: 'zh' | 'en';
  oldText: string;
  newText: string;
}

export function useFindReplace(translations: Translation[]) {
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState<FindScope>('zh');
  const [cursor, setCursor] = useState(0);

  const matches = useMemo<FindMatch[]>(() => {
    if (!query) return [];
    const result: FindMatch[] = [];
    const q = query;
    const checkZh = scope === 'zh' || scope === 'both' || scope === 'pending';
    const checkEn = scope === 'en' || scope === 'both';
    for (const t of translations) {
      if (scope === 'pending' && t.status === 'approved') continue;
      if (checkZh && t.zh_text.includes(q)) result.push({ idx: t.idx, field: 'zh' });
      if (checkEn && t.en_text.includes(q)) result.push({ idx: t.idx, field: 'en' });
    }
    return result;
  }, [query, scope, translations]);

  const next = useCallback(() => {
    if (matches.length === 0) return;
    setCursor((c) => (c + 1) % matches.length);
  }, [matches.length]);

  const prev = useCallback(() => {
    if (matches.length === 0) return;
    setCursor((c) => (c - 1 + matches.length) % matches.length);
  }, [matches.length]);

  const replaceOne = useCallback(
    (newText: string): Replacement[] => {
      if (matches.length === 0) return [];
      const m = matches[cursor];
      if (!m) return [];
      const t = translations.find((x) => x.idx === m.idx);
      if (!t) return [];
      const oldFieldText = m.field === 'zh' ? t.zh_text : t.en_text;
      const replaced = oldFieldText.split(query).join(newText);
      return [{ idx: m.idx, field: m.field, oldText: oldFieldText, newText: replaced }];
    },
    [matches, cursor, translations, query],
  );

  const replaceAll = useCallback(
    (newText: string): Replacement[] => {
      if (matches.length === 0) return [];
      const seen = new Set<string>();
      const out: Replacement[] = [];
      for (const m of matches) {
        const key = `${m.idx}:${m.field}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const t = translations.find((x) => x.idx === m.idx);
        if (!t) continue;
        const oldFieldText = m.field === 'zh' ? t.zh_text : t.en_text;
        const replaced = oldFieldText.split(query).join(newText);
        out.push({ idx: m.idx, field: m.field, oldText: oldFieldText, newText: replaced });
      }
      return out;
    },
    [matches, translations, query],
  );

  return { query, setQuery, scope, setScope, matches, cursor, setCursor, next, prev, replaceOne, replaceAll };
}
