// src/pages/Proofread/types.ts
export interface Segment {
  id: string;
  start: number;
  end: number;
  text: string;
  words?: Array<{ word: string; start: number; end: number; probability?: number }>;
}

export interface Translation {
  idx: number;
  en_text: string;
  zh_text: string;
  status: 'pending' | 'approved' | 'needs_review' | 'long' | 'review';
  flags: string[];
  start?: number;
  end?: number;
}

export interface StageOutput {
  stage_type: string;
  stage_ref: string;
  segments: Segment[];
}

export interface FileDetail {
  id: string;
  original_name: string;
  status: string;
  pipeline_id?: string | null;
  // Backend writes stage_outputs as a dict keyed by str(stage_index).
  // Consumers should normalize to an array via Object.entries(...) sort.
  stage_outputs?: StageOutput[] | Record<string, StageOutput>;
  subtitle_source?: 'auto' | 'source' | 'target' | 'bilingual';
  bilingual_order?: 'source_top' | 'target_top';
  prompt_overrides?: Record<string, unknown> | null;
}

// v5-A3 — multi-lang shape from GET /api/files/<id>/translations?shape=v5
// Re-exported from lib/api/v5.ts for ergonomic imports inside Proofread/.
export type { V5Translation } from '@/lib/api/v5';
