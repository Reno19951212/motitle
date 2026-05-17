// src/pages/Proofread/hooks/useActiveProfile.ts
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';

export interface ActiveProfile {
  id: string;
  name: string;
  font: {
    family: string;
    size: number;
    color: string;
    outline_color: string;
    outline_width: number;
    margin_bottom: number;
    subtitle_source: 'auto' | 'source' | 'target' | 'bilingual';
    bilingual_order: 'source_top' | 'target_top';
  };
  translation?: { glossary_id?: string };
}

export function useActiveProfile() {
  const [profile, setProfile] = useState<ActiveProfile | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await apiFetch<{ profile: ActiveProfile }>('/api/profiles/active');
      setProfile(r.profile);
    } catch {
      /* swallow — UI shows defaults if profile unavailable */
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return { profile, refresh };
}
