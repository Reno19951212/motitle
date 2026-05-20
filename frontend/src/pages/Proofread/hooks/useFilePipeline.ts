// src/pages/Proofread/hooks/useFilePipeline.ts
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import type { FontConfig } from '@/lib/schemas/pipeline';

export interface PipelineSummary {
  id: string;
  name: string;
  version?: number;
  asr_profile_id?: string;
  mt_stages?: string[];
  glossary_stage?: {
    enabled: boolean;
    glossary_ids: string[];
    apply_order: string;
    apply_method: string;
  };
  glossary_stages?: Record<string, string[]>;
  font_config?: FontConfig;
}

export function useFilePipeline(pipelineId: string | null | undefined) {
  const [pipeline, setPipeline] = useState<PipelineSummary | null>(null);

  const refresh = useCallback(async () => {
    if (!pipelineId) {
      setPipeline(null);
      return;
    }
    try {
      const p = await apiFetch<PipelineSummary>(`/api/pipelines/${pipelineId}`);
      setPipeline(p);
    } catch {
      setPipeline(null);
    }
  }, [pipelineId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const font: FontConfig | null = pipeline?.font_config ?? null;
  // v4 pipelines use `glossary_stage` (singular object). v5 pipelines use
  // `glossary_stages` (plural per-lang map). Probe both shapes so the panel
  // surfaces a glossary id from either; if neither has one, the panel falls
  // back to its "尚未指派" placeholder.
  let glossaryId: string | null = pipeline?.glossary_stage?.glossary_ids?.[0] ?? null;
  if (!glossaryId && pipeline?.glossary_stages) {
    for (const ids of Object.values(pipeline.glossary_stages)) {
      const first = Array.isArray(ids) ? ids[0] : undefined;
      if (first) {
        glossaryId = first;
        break;
      }
    }
  }
  return { pipeline, font, glossaryId, refresh };
}
