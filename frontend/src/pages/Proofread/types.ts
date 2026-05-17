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
  stage_outputs?: StageOutput[];
  subtitle_source?: 'auto' | 'source' | 'target' | 'bilingual';
  bilingual_order?: 'source_top' | 'target_top';
  prompt_overrides?: Record<string, unknown> | null;
}
