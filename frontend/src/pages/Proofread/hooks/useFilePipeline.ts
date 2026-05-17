// src/pages/Proofread/hooks/useFilePipeline.ts
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import type { FontConfig } from '@/lib/schemas/pipeline';

export interface PipelineSummary {
  id: string;
  name: string;
  asr_profile_id: string;
  mt_stages: string[];
  glossary_stage: {
    enabled: boolean;
    glossary_ids: string[];
    apply_order: string;
    apply_method: string;
  };
  font_config: FontConfig;
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
  const glossaryId: string | null = pipeline?.glossary_stage.glossary_ids[0] ?? null;
  return { pipeline, font, glossaryId, refresh };
}
