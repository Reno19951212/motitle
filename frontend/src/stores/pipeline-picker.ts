import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { apiFetch } from '@/lib/api';

export interface PipelineSummary {
  id: string;
  name: string;
  description: string;
  shared: boolean;
  user_id: number | null;
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
          const pipelines = await apiFetch<PipelineSummary[]>('/api/pipelines');
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
