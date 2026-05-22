import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { apiFetch } from '@/lib/api';

/**
 * Backend annotates each pipeline with `broken_refs` describing sub-resource
 * ids the requesting user cannot view (see backend/pipelines.py
 * `annotate_broken_refs`). Empty dict `{}` means no broken refs.
 */
export interface PipelineBrokenRefs {
  asr_profile_id?: string;
  mt_stages?: string[];
  glossary_ids?: string[];
}

export interface PipelineSummary {
  id: string;
  name: string;
  description: string;
  shared: boolean;
  user_id: number | null;
  broken_refs?: PipelineBrokenRefs;
  preset_slot?: 1 | 2 | 3 | 4 | null;   // Q3
}

interface PickerState {
  pipelineId: string | null;
  pipelines: PipelineSummary[];
  setPipelineId: (id: string | null) => void;
  refresh: () => Promise<void>;
}

export const usePipelinePickerStore = create<PickerState>()(
  persist(
    (set) => ({
      pipelineId: null,
      pipelines: [],
      setPipelineId: (id) => set({ pipelineId: id }),
      refresh: async () => {
        try {
          const { pipelines } = await apiFetch<{ pipelines: PipelineSummary[] }>('/api/pipelines');
          set({ pipelines });
        } catch {
          /* keep stale */
        }
      },
    }),
    {
      name: 'motitle.pipeline-picker',
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ pipelineId: s.pipelineId }),
    }
  )
);
