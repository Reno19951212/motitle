// Dashboard — Bold variant redesign
// Pixel-faithful port of /tmp/v4-design/motitle/project/variant-bold.jsx
// This component renders a full-page layout that bypasses the parent Layout shell.
import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import { useSocket } from '@/providers/SocketProvider';
import { usePipelinePickerStore } from '@/stores/pipeline-picker';
import type { PipelineBrokenRefs, PipelineSummary } from '@/stores/pipeline-picker';
import { useUIStore } from '@/stores/ui';
import { useAuthStore } from '@/stores/auth';
import { useProfileLookupStore } from '@/stores/profile-lookup';
import type {
  AsrProfileLookup,
  MtProfileLookup,
  GlossaryLookup,
  PipelineLookup,
} from '@/stores/profile-lookup';
import { apiFetch, ApiError } from '@/lib/api';
import type { FileRecord, StageStatus } from '@/lib/socket-events';
import { Icon, MoTitleStageBadge } from '@/lib/motitle-icons';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { useDashboardTranslations } from '@/hooks/useDashboardTranslations';
import '@/styles/motitle-bold.css';
import { pillClass, pillLabel, type StagePhase } from './Dashboard-pill-helpers';

// ---------------------------------------------------------------------------
// Engine health probe types (Batch D)
// ---------------------------------------------------------------------------
interface EngineProbeItem {
  engine: string;
  available: boolean;
  description?: string;
}

interface EngineProbeResponse {
  engines: EngineProbeItem[];
}

// ---------------------------------------------------------------------------
// Pipeline broken_refs helpers (Batch C)
// ---------------------------------------------------------------------------

/** Returns true when the pipeline has any broken sub-resource references. */
function hasBrokenRefs(p: PipelineSummary | undefined | null): boolean {
  const br: PipelineBrokenRefs | undefined = p?.broken_refs;
  if (!br) return false;
  if (br.asr_profile_id) return true;
  if (Array.isArray(br.mt_stages) && br.mt_stages.length > 0) return true;
  if (Array.isArray(br.glossary_ids) && br.glossary_ids.length > 0) return true;
  return false;
}

/** Build a multi-line tooltip string listing the broken refs. */
function brokenRefsTooltip(p: PipelineSummary | undefined | null): string {
  const br: PipelineBrokenRefs | undefined = p?.broken_refs;
  if (!br) return '';
  const parts: string[] = [];
  if (br.asr_profile_id) parts.push(`ASR profile: ${br.asr_profile_id}`);
  if (Array.isArray(br.mt_stages) && br.mt_stages.length > 0) {
    parts.push(`MT 階段 (${br.mt_stages.length}): ${br.mt_stages.join(', ')}`);
  }
  if (Array.isArray(br.glossary_ids) && br.glossary_ids.length > 0) {
    parts.push(`術語表 (${br.glossary_ids.length}): ${br.glossary_ids.join(', ')}`);
  }
  if (!parts.length) return '';
  return `⚠ 此 Pipeline 引用咗你無權限睇嘅資源：\n${parts.join('\n')}`;
}

/** Inline red dot used to flag pipelines with broken refs. */
function BrokenRefsDot({ title }: { title: string }) {
  return (
    <span
      title={title}
      aria-label="broken-refs"
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: '#ef4444',
        flexShrink: 0,
        marginLeft: 6,
        boxShadow: '0 0 0 2px rgba(239, 68, 68, 0.15)',
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Helpers — map FileRecord → design's "f" shape
// ---------------------------------------------------------------------------

interface DesignFile {
  id: string;
  name: string;
  duration: string;
  segments: number;
  approved: number;
  uploaded: string;
  /** derived stage string for display — kept for legacy badge / inspector */
  stage: string;
  transcribeProgress: number;
  renderProgress: number;
  size: string;
  // New 6-phase fields — see docs/superpowers/specs/2026-05-27-queue-execution-feedback-design.md
  asrPhase:   StagePhase;
  asrPercent: number;
  mtPhase:    StagePhase;
  mtPercent:  number;
}

/**
 * Derive the 6-phase state for a single stage index from reducer state.
 * Terminal states (done / failed from stageStatus) take precedence — even
 * if a stale stagePhase entry says 'running', backend telling us it's
 * done wins. Otherwise consult stagePhase (queued / starting / running)
 * and fall back to 'idle' if no signal is present.
 */
function deriveStagePhase(
  idx: number,
  stageProgress: Record<number, number> | undefined,
  stageStatus: Record<number, import('@/lib/socket-events').StageStatus> | undefined,
  stagePhase: Record<number, 'queued' | 'starting' | 'running'> | undefined,
): { phase: StagePhase; percent: number } {
  const status = stageStatus?.[idx];
  if (status === 'done')   return { phase: 'done',   percent: 100 };
  if (status === 'failed') return { phase: 'failed', percent: stageProgress?.[idx] ?? 0 };
  const phase = stagePhase?.[idx];
  if (phase === 'queued')   return { phase: 'queued',   percent: 0 };
  if (phase === 'starting') return { phase: 'starting', percent: 0 };
  if (phase === 'running')  return { phase: 'running',  percent: stageProgress?.[idx] ?? 0 };
  return { phase: 'idle', percent: 0 };
}

/**
 * Derive the "representative" MT phase across all stage indices >= 1.
 * Pipelines may have multiple MT stages scheduled sequentially; show the
 * highest-numbered stage that is still non-idle. When all MT stages are
 * idle (or there are none), returns idle.
 */
function deriveMtPhase(
  stageProgress: Record<number, number> | undefined,
  stageStatus: Record<number, import('@/lib/socket-events').StageStatus> | undefined,
  stagePhase: Record<number, 'queued' | 'starting' | 'running'> | undefined,
): { phase: StagePhase; percent: number } {
  const indices = new Set<number>();
  for (const k of Object.keys(stageProgress ?? {})) indices.add(Number(k));
  for (const k of Object.keys(stageStatus ?? {}))   indices.add(Number(k));
  for (const k of Object.keys(stagePhase ?? {}))    indices.add(Number(k));
  const mtIndices = Array.from(indices).filter(i => i >= 1).sort((a, b) => b - a);
  for (const i of mtIndices) {
    const d = deriveStagePhase(i, stageProgress, stageStatus, stagePhase);
    if (d.phase !== 'idle') return d;
  }
  return { phase: 'idle', percent: 0 };
}

/**
 * Map a backend FileRecord (GET /api/files row) into the design shape consumed
 * by Bold-variant queue/workbench/inspector. Socket-derived live progress is
 * threaded in via `stageProgress`/`stageStatus` so we do not depend on backend
 * to set a per-record `transcribe_progress` field (it doesn't).
 */
export function toDesignFile(
  f: FileRecord,
  stageProgress: Record<number, number> | undefined,
  stageStatus: Record<number, import('@/lib/socket-events').StageStatus> | undefined,
  stagePhase: Record<number, 'queued' | 'starting' | 'running'> | undefined,
): DesignFile {
  // Derive stage from FileRecord.status + live per-stage Socket.IO state.
  // Note: if any MT stage_idx > 0 is 'running', we still surface 'translating'
  //   — improving per-MT-stage badge labels stays out of Batch A scope (see
  //   audit doc "Out of scope" follow-ups).
  let stage = 'idle';
  const status = f.status ?? '';
  if (status === 'transcribing' || status === 'running') {
    stage = 'transcribing';
  } else if (status === 'translating') {
    stage = 'translating';
  } else if (status === 'proofreading') {
    stage = 'proofreading';
  } else if (status === 'rendering') {
    stage = 'rendering';
  } else if (status === 'completed' || status === 'done') {
    stage = 'done';
  } else if (status === 'failed' || status === 'error') {
    stage = 'error';
  } else if (status === 'queued') {
    stage = 'transcribing';
  }

  const name = String(f.original_name ?? f.id ?? 'unknown');

  // Backend uses `uploaded_at` (Unix epoch float, time.time() from
  // backend/helpers/files.py:112). Previous code read `created_at` which was
  // always undefined → every queue row showed '—'.
  const uploadedAt = typeof f.uploaded_at === 'number' ? f.uploaded_at : 0;
  const ageSec = uploadedAt > 0 ? (Date.now() / 1000 - uploadedAt) : 0;
  let uploaded = '—';
  if (uploadedAt > 0) {
    if (ageSec < 120) uploaded = '剛剛';
    else if (ageSec < 3600) uploaded = `${Math.floor(ageSec / 60)} 分鐘前`;
    else if (ageSec < 86400) uploaded = `${Math.floor(ageSec / 3600)} 小時前`;
    else uploaded = `${Math.floor(ageSec / 86400)} 日前`;
  }

  // Live ASR (stage 0) progress comes from Socket.IO pipeline_stage_progress.
  // Stage 0 is always ASR per backend pipeline_runner.py contract (ASRStage
  // is appended first). Fall back to 0 if no event has fired yet.
  const asrPercent = typeof stageProgress?.[0] === 'number' ? stageProgress[0] : 0;
  // Detect any MT stage (>= idx 1) currently running for the future
  // "MT stage N" badge — recorded but not yet rendered in queue-item (see
  // audit doc Out-of-scope).
  void stageStatus;

  // duration: deferred until backend captures via ffprobe at upload.
  // Workbench/inspector still render the field but show '?:??'; the queue
  // row no longer renders the duration span (Batch A drops it).

  // 6-phase derive — see Dashboard-pill-helpers.ts for the phase machine.
  const asr = deriveStagePhase(0, stageProgress, stageStatus, stagePhase);
  const mt  = deriveMtPhase(stageProgress, stageStatus, stagePhase);

  return {
    id: f.id,
    name,
    duration: '?:??',
    segments: typeof f.segment_count === 'number' ? f.segment_count : 0,
    approved: typeof f.approved_count === 'number' ? f.approved_count : 0,
    uploaded,
    stage,
    transcribeProgress: Math.round(asrPercent),
    // renderProgress dropped from queue items (renders are separate jobs via
    // /api/renders/<id>, not pipeline stages). Inspector still displays the
    // value but it is no longer surfaced on queue rows.
    renderProgress: 0,
    size: typeof f.size === 'number' ? formatBytes(f.size) : '—',
    asrPhase:   asr.phase,
    asrPercent: asr.percent,
    mtPhase:    mt.phase,
    mtPercent:  mt.percent,
  };
}

// Format byte count as human readable. Mirrors small-form OS file sizes.
function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const kb = n / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

/** Squash threshold: more than this many MT stages collapses into one chip. */
const MT_SQUASH_THRESHOLD = 3;

// ---------------------------------------------------------------------------
// PipelineStrip — data-driven per audit Batch B
//
// Renders the active pipeline as variable-length chip strip:
//   [Pipeline preset] · ASR · → · MT (× N or squashed) · → · Glossary
//
// There is no "Output" chip — output format is chosen per-render-job
// (render modal payload), not stored on the pipeline.
//
// Step popovers are read-only summaries (name / engine / model / language)
// with a "編輯 →" link to /pipelines. Inline editing is out of scope; a
// profile bundles engine+model+lang+params and switching one model isn't
// a meaningful operation here — switch the whole pipeline via the preset
// dropdown to the left.
//
// Profile resolution reuses `useProfileLookupStore` from Batch F so we
// avoid duplicate fetches when the inspector also resolves the same ids.
// ---------------------------------------------------------------------------

/** ASR step chip with read-only summary popover. */
function PipelineAsrStep({
  asrId,
  asrProfile,
}: {
  asrId: string;
  asrProfile: AsrProfileLookup | null | undefined;
}) {
  const v = asrProfile
    ? asrProfile.name || asrProfile.model_size || asrProfile.engine || asrId
    : '…';
  const isLoading = asrProfile === null || asrProfile === undefined;
  return (
    <div className="step" style={{ position: 'relative' }}>
      <Icon name="waveform" size={12} color="var(--accent-2)" />
      <div>
        <div className="k">ASR</div>
        <div className="v">{v}</div>
      </div>
      <Icon name="caret" size={10} />
      <div className="step-menu" style={{ minWidth: 240 }}>
        <div className="step-menu-head">ASR · 詳情</div>
        {isLoading ? (
          <div style={{ padding: '8px 10px', fontSize: 12, color: 'var(--text-dim)' }}>
            載入中…
          </div>
        ) : (
          <div style={{ padding: '6px 10px', display: 'flex', flexDirection: 'column', gap: 3 }}>
            <div className="smn-main">
              <span className="smn-name">{asrProfile?.name ?? '—'}</span>
            </div>
            <div className="smn-desc">引擎：{asrProfile?.engine ?? '—'}</div>
            {asrProfile?.model_size && (
              <div className="smn-desc">模型：{asrProfile.model_size}</div>
            )}
            {asrProfile?.language && (
              <div className="smn-desc">語言：{asrProfile.language}</div>
            )}
            {asrProfile?.device && (
              <div className="smn-desc">裝置：{asrProfile.device}</div>
            )}
          </div>
        )}
        <div className="split-divider" />
        <Link
          to="/asr_profiles"
          className="smn-manage"
          style={{ display: 'flex', gap: 8, padding: '7px 10px', borderRadius: 6, fontSize: 13, color: 'var(--text-mid)', alignItems: 'center' }}
        >
          <span className="fmt-badge outline">✎</span>
          <span className="fmt-desc">編輯 ASR Profile →</span>
        </Link>
      </div>
    </div>
  );
}

/** Single MT step chip with read-only summary popover. */
function PipelineMtStep({
  index,
  total,
  mtId,
  mtProfile,
}: {
  index: number;
  total: number;
  mtId: string;
  mtProfile: MtProfileLookup | null | undefined;
}) {
  const label = total > 1 ? `MT ${index + 1}` : 'MT';
  const v = mtProfile
    ? mtProfile.name || mtProfile.engine || mtId
    : '…';
  const isLoading = mtProfile === null || mtProfile === undefined;
  return (
    <div className="step" style={{ position: 'relative' }}>
      <Icon name="layers" size={12} color="var(--accent-2)" />
      <div>
        <div className="k">{label}</div>
        <div className="v">{v}</div>
      </div>
      <Icon name="caret" size={10} />
      <div className="step-menu" style={{ minWidth: 240 }}>
        <div className="step-menu-head">{label} · 詳情</div>
        {isLoading ? (
          <div style={{ padding: '8px 10px', fontSize: 12, color: 'var(--text-dim)' }}>
            載入中…
          </div>
        ) : (
          <div style={{ padding: '6px 10px', display: 'flex', flexDirection: 'column', gap: 3 }}>
            <div className="smn-main">
              <span className="smn-name">{mtProfile?.name ?? '—'}</span>
            </div>
            <div className="smn-desc">引擎：{mtProfile?.engine ?? '—'}</div>
            {(mtProfile?.input_lang || mtProfile?.output_lang) && (
              <div className="smn-desc">
                語向：{mtProfile?.input_lang ?? '?'} → {mtProfile?.output_lang ?? '?'}
              </div>
            )}
            {typeof mtProfile?.batch_size === 'number' && (
              <div className="smn-desc">Batch：{mtProfile.batch_size}</div>
            )}
          </div>
        )}
        <div className="split-divider" />
        <Link
          to="/mt_profiles"
          className="smn-manage"
          style={{ display: 'flex', gap: 8, padding: '7px 10px', borderRadius: 6, fontSize: 13, color: 'var(--text-mid)', alignItems: 'center' }}
        >
          <span className="fmt-badge outline">✎</span>
          <span className="fmt-desc">編輯 MT Profile →</span>
        </Link>
      </div>
    </div>
  );
}

/** Squashed MT chip (>3 stages) — lists every stage in popover. */
function PipelineMtSquashedStep({
  mtIds,
  mtProfiles,
}: {
  mtIds: string[];
  mtProfiles: Array<MtProfileLookup | null | undefined>;
}) {
  return (
    <div className="step" style={{ position: 'relative' }}>
      <Icon name="layers" size={12} color="var(--accent-2)" />
      <div>
        <div className="k">MT</div>
        <div className="v">{`× ${mtIds.length}`}</div>
      </div>
      <Icon name="caret" size={10} />
      <div className="step-menu" style={{ minWidth: 260 }}>
        <div className="step-menu-head">MT 階段 · {mtIds.length} 段串接</div>
        {mtIds.map((id, i) => {
          const p = mtProfiles[i];
          const isLoading = p === null || p === undefined;
          return (
            <div key={`${id}-${i}`} style={{ padding: '6px 10px', display: 'flex', flexDirection: 'column', gap: 2 }}>
              <div className="smn-main">
                <span className="smn-name">
                  {i + 1}. {isLoading ? '…' : p?.name || p?.engine || id}
                </span>
                {!isLoading && p?.engine && <span className="smn-badge">{p.engine}</span>}
              </div>
              {!isLoading && (p?.input_lang || p?.output_lang) && (
                <div className="smn-desc">
                  {p?.input_lang ?? '?'} → {p?.output_lang ?? '?'}
                </div>
              )}
            </div>
          );
        })}
        <div className="split-divider" />
        <Link
          to="/mt_profiles"
          className="smn-manage"
          style={{ display: 'flex', gap: 8, padding: '7px 10px', borderRadius: 6, fontSize: 13, color: 'var(--text-mid)', alignItems: 'center' }}
        >
          <span className="fmt-badge outline">✎</span>
          <span className="fmt-desc">編輯 MT Profile →</span>
        </Link>
      </div>
    </div>
  );
}

/** Glossary step chip — reads `pipeline.glossary_stage`. */
function PipelineGlossaryStep({
  enabled,
  glossaryIds,
  glossaries,
}: {
  enabled: boolean;
  glossaryIds: string[];
  glossaries: Array<GlossaryLookup | null | undefined>;
}) {
  const count = glossaryIds.length;
  // Display value: enabled state + count or first name
  let v: string;
  const greyed = !enabled || count === 0;
  if (!enabled) {
    v = '未啟用';
  } else if (count === 0) {
    v = '未設定';
  } else if (count === 1) {
    const g = glossaries[0];
    if (g === null || g === undefined) v = '…';
    else v = g.name || glossaryIds[0] || '—';
  } else {
    v = `${count} 個術語表`;
  }
  return (
    <div
      className="step step-gloss"
      title="執行時套用嘅術語表"
      style={{
        position: 'relative',
        ...(greyed ? { opacity: 0.55 } : {}),
      }}
    >
      <Icon name="book" size={12} color="var(--accent)" />
      <div>
        <div className="k">術語表</div>
        <div className="v">{v}</div>
      </div>
      <Icon name="caret" size={10} />
      <div className="step-menu" style={{ minWidth: 260, right: 0, left: 'auto' }}>
        <div className="step-menu-head">術語表 · 詳情</div>
        {!enabled ? (
          <div style={{ padding: '8px 10px', fontSize: 12, color: 'var(--text-dim)' }}>
            此 Pipeline 已停用術語階段。
          </div>
        ) : count === 0 ? (
          <div style={{ padding: '8px 10px', fontSize: 12, color: 'var(--text-dim)' }}>
            已啟用但未設定任何術語表。
          </div>
        ) : (
          glossaryIds.map((id, i) => {
            const g = glossaries[i];
            const isLoading = g === null || g === undefined;
            return (
              <div key={`${id}-${i}`} style={{ padding: '6px 10px', display: 'flex', flexDirection: 'column', gap: 2 }}>
                <div className="smn-main">
                  <span className="smn-name">{isLoading ? '…' : g?.name || id}</span>
                  {!isLoading && (g?.source_lang || g?.target_lang) && (
                    <span className="smn-badge">
                      {(g?.source_lang ?? '?').toUpperCase()}→
                      {(g?.target_lang ?? '?').toUpperCase()}
                    </span>
                  )}
                </div>
                {!isLoading && typeof g?.entry_count === 'number' && (
                  <div className="smn-desc">{g.entry_count} 個條目</div>
                )}
              </div>
            );
          })
        )}
        <div className="split-divider" />
        <Link
          to="/glossaries"
          className="smn-manage"
          style={{ display: 'flex', gap: 8, padding: '7px 10px', borderRadius: 6, fontSize: 13, color: 'var(--text-mid)', alignItems: 'center' }}
        >
          <span className="fmt-badge outline">✎</span>
          <span className="fmt-desc">編輯術語表 →</span>
        </Link>
      </div>
    </div>
  );
}

function PipelineStrip() {
  const { pipelines, pipelineId, setPipelineId, refresh } = usePipelinePickerStore();

  // Reuse the Batch F profile-lookup cache so we don't duplicate fetches
  // when BoldInspector resolves the same ids on the right column.
  const fetchPipeline = useProfileLookupStore((s) => s.fetchPipeline);
  const fetchAsr = useProfileLookupStore((s) => s.fetchAsr);
  const fetchMt = useProfileLookupStore((s) => s.fetchMt);
  const fetchGlossary = useProfileLookupStore((s) => s.fetchGlossary);
  const cachedPipelines = useProfileLookupStore((s) => s.pipelines);
  const cachedAsrProfiles = useProfileLookupStore((s) => s.asrProfiles);
  const cachedMtProfiles = useProfileLookupStore((s) => s.mtProfiles);
  const cachedGlossaries = useProfileLookupStore((s) => s.glossaries);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Pick the active pipeline summary (from picker store) — used for name +
  // broken_refs warning. The full schema (mt_stages / glossary_stage) lives
  // in the lookup cache and gets fetched below.
  const activePipelineSummary =
    pipelines.find((p) => p.id === pipelineId) ?? pipelines[0] ?? null;
  const activeName = activePipelineSummary?.name ?? '—';
  const activeBrokenTooltip = brokenRefsTooltip(activePipelineSummary);

  // Cascade-fetch full pipeline → ASR profile + MT profiles + glossary list.
  const activeFullId = activePipelineSummary?.id ?? null;
  useEffect(() => {
    if (activeFullId) void fetchPipeline(activeFullId);
  }, [activeFullId, fetchPipeline]);

  const activeFull = activeFullId ? cachedPipelines[activeFullId] ?? null : null;

  useEffect(() => {
    if (activeFull?.asr_profile_id) {
      void fetchAsr(activeFull.asr_profile_id);
    }
    if (Array.isArray(activeFull?.mt_stages)) {
      for (const mtId of activeFull.mt_stages) {
        void fetchMt(mtId);
      }
    }
    const gIds = activeFull?.glossary_stage?.glossary_ids ?? [];
    for (const gId of gIds) {
      void fetchGlossary(gId);
    }
  }, [activeFull, fetchAsr, fetchMt, fetchGlossary]);

  const asrProfile = activeFull?.asr_profile_id
    ? cachedAsrProfiles[activeFull.asr_profile_id] ?? null
    : null;
  const mtIds = activeFull?.mt_stages ?? [];
  const mtProfiles = mtIds.map((id) => cachedMtProfiles[id] ?? null);
  const glossEnabled = !!activeFull?.glossary_stage?.enabled;
  const glossaryIds = activeFull?.glossary_stage?.glossary_ids ?? [];
  const glossaries = glossaryIds.map((id) => cachedGlossaries[id] ?? null);

  return (
    <div className="pipeline-strip" title="當前 Pipeline 組合">
      <div className="pipeline-preset-wrap" style={{ position: 'relative' }}>
        <button className="pipeline-preset" title="切換 Pipeline 預設">
          <Icon name="flow" size={13} color="var(--accent)" />
          <div className="pp-text">
            <div className="pp-k">Pipeline</div>
            <div className="pp-v" style={{ display: 'inline-flex', alignItems: 'center' }}>
              {activeName}
              {hasBrokenRefs(activePipelineSummary) && (
                <BrokenRefsDot title={activeBrokenTooltip} />
              )}
            </div>
          </div>
          <Icon name="caret" size={10} />
        </button>
        <div className="step-menu preset-menu" style={{ minWidth: 260, left: 0 }}>
          <div className="step-menu-head">Pipeline 預設</div>
          {pipelines.length === 0 ? (
            <div style={{ padding: '8px 10px', fontSize: 12, color: 'var(--text-dim)' }}>
              尚未建立 Pipeline
            </div>
          ) : (
            pipelines.map((p) => {
              const broken = hasBrokenRefs(p);
              const brokenTip = broken ? brokenRefsTooltip(p) : '';
              return (
                <button
                  key={p.id}
                  className={p.id === pipelineId ? 'on' : ''}
                  onClick={() => setPipelineId(p.id)}
                  title={brokenTip || undefined}
                >
                  <div className="smn-main">
                    <span className="smn-name" style={{ display: 'inline-flex', alignItems: 'center' }}>
                      {p.name}
                      {broken && <BrokenRefsDot title={brokenTip} />}
                    </span>
                    {p.id === pipelineId && <span className="smn-badge">當前</span>}
                  </div>
                  {p.description && <div className="smn-desc">{p.description}</div>}
                  {broken && (
                    <div
                      className="smn-desc"
                      style={{ color: '#ef4444', marginTop: 2 }}
                    >
                      ⚠ 引用咗無權限睇嘅 ASR/MT/術語表資源
                    </div>
                  )}
                </button>
              );
            })
          )}
          <div className="split-divider" />
          <Link to="/pipelines" className="smn-manage" style={{ display: 'flex', gap: 8, padding: '7px 10px', borderRadius: 6, fontSize: 13, color: 'var(--text-mid)', alignItems: 'center' }}>
            <span className="fmt-badge outline">⚙</span>
            <span className="fmt-desc">管理預設…</span>
          </Link>
        </div>
      </div>
      <span className="sep" />
      {/* No pipeline loaded yet: stub the strip with a single placeholder so
          the layout doesn't collapse. */}
      {!activeFull ? (
        <div className="step" style={{ opacity: 0.6 }}>
          <Icon name="waveform" size={12} color="var(--text-dim)" />
          <div>
            <div className="k">階段</div>
            <div className="v">載入中…</div>
          </div>
        </div>
      ) : (
        <>
          {/* ASR — always present */}
          {activeFull.asr_profile_id && (
            <PipelineAsrStep asrId={activeFull.asr_profile_id} asrProfile={asrProfile} />
          )}

          {/* MT — variable count, squashed when > MT_SQUASH_THRESHOLD */}
          {mtIds.length > 0 && <span className="arrow">→</span>}
          {mtIds.length > MT_SQUASH_THRESHOLD ? (
            <PipelineMtSquashedStep mtIds={mtIds} mtProfiles={mtProfiles} />
          ) : (
            mtIds.map((id, i) => (
              <span key={`${id}-${i}`} style={{ display: 'contents' }}>
                {i > 0 && <span className="arrow">→</span>}
                <PipelineMtStep
                  index={i}
                  total={mtIds.length}
                  mtId={id}
                  mtProfile={mtProfiles[i]}
                />
              </span>
            ))
          )}

          {/* Glossary — always rendered (shows 未啟用 when disabled) */}
          <span className="arrow">→</span>
          <PipelineGlossaryStep
            enabled={glossEnabled}
            glossaryIds={glossaryIds}
            glossaries={glossaries}
          />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// BoldTopbar
// ---------------------------------------------------------------------------

function BoldTopbar({ onRun }: { onRun?: () => void }) {
  const { state: socketState } = useSocket();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clearUser = useAuthStore((s) => s.clearUser);
  const [asrEngines, setAsrEngines] = useState<EngineProbeItem[] | null>(null);
  const [mtEngines, setMtEngines] = useState<EngineProbeItem[] | null>(null);

  async function handleLogout() {
    try {
      await apiFetch('/api/logout', { method: 'POST' });
    } catch {
      /* ignore */
    }
    clearUser();
    navigate('/login');
  }

  useEffect(() => {
    let cancelled = false;

    const probe = async () => {
      if (document.hidden) return;
      try {
        const asr = await apiFetch<EngineProbeResponse>('/api/asr/engines');
        if (!cancelled) setAsrEngines(asr.engines ?? []);
      } catch {
        if (!cancelled) setAsrEngines([]);
      }
      try {
        const mt = await apiFetch<EngineProbeResponse>('/api/translation/engines');
        if (!cancelled) setMtEngines(mt.engines ?? []);
      } catch {
        if (!cancelled) setMtEngines([]);
      }
    };

    probe();
    const id = window.setInterval(probe, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const asrReady = !!asrEngines && asrEngines.some((e) => e.available);
  const mtReady = !!mtEngines && mtEngines.some((e) => e.available);

  const asrTooltip = asrEngines
    ? asrEngines
        .map((e) => `${e.engine}: ${e.available ? 'OK' : 'unavailable'}${e.description ? ` (${e.description})` : ''}`)
        .join('\n')
    : 'ASR engines · loading…';
  const mtTooltip = mtEngines
    ? mtEngines
        .map((e) => `${e.engine}: ${e.available ? 'OK' : 'unavailable'}${e.description ? ` (${e.description})` : ''}`)
        .join('\n')
    : 'Translation engines · loading…';

  const socketConnected = socketState.connected;

  return (
    <div className="b-topbar">
      <div className="search">
        <Icon name="search" size={13} />
        <span>搜尋檔案、術語、Profile…</span>
        <span style={{ marginLeft: 'auto' }} className="kbd">
          ⌘K
        </span>
      </div>

      <div className="topbar-mid">
        <PipelineStrip />
        <div className="topbar-actions">
          <button className="run-btn" title="使用當前設定執行" onClick={onRun}>
            <Icon name="play" size={11} color="#fff" /> 執行
          </button>
        </div>
      </div>

      <div className="health-cluster">
        <div className={`health-pill ${asrReady ? 'ok' : 'err'}`} title={asrTooltip}>
          <span className="led" />
          <span className="hk">ASR</span>
          <span className="hv">{asrReady ? '就緒' : '離線'}</span>
        </div>
        <div className={`health-pill ${mtReady ? 'ok' : 'err'}`} title={mtTooltip}>
          <span className="led" />
          <span className="hk">MT</span>
          <span className="hv">{mtReady ? '就緒' : '離線'}</span>
        </div>
        <div
          className={`health-pill ${socketConnected ? 'ok' : 'err'}`}
          title={socketConnected ? 'Socket.IO 已連接 · 即時事件正常' : 'Socket.IO 中斷 · 即時事件不可用'}
        >
          <span className="led" />
          <span className="hk">即時</span>
          <span className="hv">{socketConnected ? '已連' : '離線'}</span>
        </div>
        <button
          className="health-pill"
          onClick={handleLogout}
          title={user ? `登出 ${user.username}` : '登出'}
          style={{ cursor: 'pointer' }}
        >
          <Icon name="user" size={11} />
          <span className="hk">{user?.username ?? '—'}</span>
          <span className="hv">Logout</span>
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DropHero — wired to upload handler
// ---------------------------------------------------------------------------

function DropHero({ onUploaded }: { onUploaded?: (fileId: string) => void }) {
  const pushToast = useUIStore((s) => s.pushToast);
  const { refresh } = useSocket();

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (!acceptedFiles.length) return;
      let anyUploaded = false;
      let lastUploadedId: string | null = null;
      for (const file of acceptedFiles) {
        const fd = new FormData();
        fd.append('file', file);
        try {
          const r = await fetch('/api/files/upload', {
            method: 'POST',
            body: fd,
            credentials: 'include',
          });
          if (!r.ok) {
            const body = await r.json().catch(() => ({ error: r.statusText }));
            pushToast({
              title: '上傳失敗',
              description: String((body as { error?: string }).error ?? r.statusText),
              variant: 'destructive',
            });
          } else {
            anyUploaded = true;
            const body = await r.json().catch(() => ({} as { file_id?: string }));
            const fid = (body as { file_id?: string }).file_id ?? null;
            if (fid) lastUploadedId = fid;
            pushToast({
              title: '✅ 已上傳',
              description: `${file.name} · 撳「執行」開始處理`,
            });
          }
        } catch (e) {
          pushToast({ title: '上傳失敗', description: String(e), variant: 'destructive' });
        }
      }
      // Belt-and-braces: force a queue refresh after upload so the new row
      // appears immediately even if the backend's socketio file_added broadcast
      // missed the client (e.g. polling→websocket transport upgrade race).
      if (anyUploaded) {
        await refresh();
        if (lastUploadedId && onUploaded) onUploaded(lastUploadedId);
      }
    },
    [pushToast, refresh, onUploaded]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'video/*': ['.mp4', '.mxf', '.mov', '.mkv'],
      'audio/*': ['.wav', '.mp3', '.m4a'],
    },
  });

  return (
    <div {...getRootProps()} className={`drop-hero ${isDragActive ? 'drag' : ''}`}>
      <input {...getInputProps()} />
      <div className="big">
        <Icon name="upload" size={16} color="#fff" />
      </div>
      <div className="txt">
        <div className="t">拖放影片上傳</div>
        <div className="s">MP4 · MOV · MXF · WAV · 最大 500MB</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// QueueItem
// ---------------------------------------------------------------------------

function QueueItem({
  f,
  onSelect,
  active,
  onDelete,
  onRun,
  pipelineId,
}: {
  f: DesignFile;
  onSelect: (f: DesignFile) => void;
  active: boolean;
  onDelete: (fileId: string) => void;
  onRun: (fileId: string) => void;
  pipelineId: string | null;
}) {
  const canRun = f.stage === 'idle' && !!pipelineId;

  return (
    <div
      className={`queue-item ${active ? 'active' : ''}`}
      onClick={() => onSelect(f)}
    >
      <div className="qh">
        <Icon
          name={f.name.endsWith('.wav') ? 'waveform' : 'film'}
          size={13}
          color="var(--accent-2)"
        />
        <span className="nm">{f.name}</span>
        <MoTitleStageBadge file={f} />
        {canRun && (
          <button
            className="qi-run"
            title="執行 Pipeline"
            onClick={(e) => {
              e.stopPropagation();
              onRun(f.id);
            }}
          >
            <Icon name="play" size={10} />
            <span style={{ fontSize: 11 }}>執行</span>
          </button>
        )}
        <button
          className="qi-del"
          title="刪除此檔案"
          onClick={(e) => {
            e.stopPropagation();
            onDelete(f.id);
          }}
        >
          <Icon name="x" size={10} />
        </button>
      </div>
      <div className="qm">
        {/* duration: deferred until backend captures via ffprobe at upload */}
        <span>{f.segments > 0 ? `${f.segments} 段` : '—'}</span>
        <span style={{ color: 'var(--border-strong)' }}>·</span>
        <span>{f.uploaded}</span>
      </div>
      <div className="stage">
        <div className={`stage-pill ${pillClass(f.asrPhase)}`}>
          <span className="lb">ASR</span>
          <span>{pillLabel(f.asrPhase, f.asrPercent)}</span>
        </div>
        <div className={`stage-pill ${pillClass(f.mtPhase)}`}>
          <span className="lb">MT</span>
          <span>{pillLabel(f.mtPhase, f.mtPercent)}</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// BoldWorkbench — real video player + waveform (Batch E)
// ---------------------------------------------------------------------------

/** Format seconds → "m:ss". Negative/NaN → "0:00". */
function fmtTime(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '0:00';
  const total = Math.floor(sec);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

interface SegmentPreview {
  start: number;
  end: number;
  text: string;
}

/** Find the segment whose [start, end] window contains `t`. Returns -1 if none.
 *  Linear scan (97 segments × 60Hz onTimeUpdate ≈ 6k ops/sec — negligible). */
function findSegmentIdxAtTime(segments: SegmentPreview[], t: number): number {
  for (let i = 0; i < segments.length; i++) {
    const s = segments[i];
    if (s && t >= s.start && t < s.end) return i;
  }
  return -1;
}

/** Subtitle overlay on top of the <video>. SVG paint-order matches the
 *  Proofread page's SubtitleOverlay (libass-compatible stroke geometry). */
function VideoSubtitleOverlay({
  segments,
  currentTime,
}: {
  segments: SegmentPreview[];
  currentTime: number;
}) {
  const idx = findSegmentIdxAtTime(segments, currentTime);
  if (idx < 0) return null;
  const text = segments[idx]?.text ?? '';
  if (!text) return null;
  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: '14%',
        textAlign: 'center',
        pointerEvents: 'none',
        padding: '0 24px',
      }}
    >
      <span
        style={{
          display: 'inline-block',
          maxWidth: '92%',
          fontFamily: '"Noto Sans HK", "PingFang HK", system-ui, sans-serif',
          fontSize: 'clamp(18px, 3.6vw, 36px)',
          fontWeight: 700,
          color: '#fff',
          lineHeight: 1.25,
          textShadow:
            '2px 0 0 #000, -2px 0 0 #000, 0 2px 0 #000, 0 -2px 0 #000,' +
            '1.4px 1.4px 0 #000, -1.4px 1.4px 0 #000,' +
            '1.4px -1.4px 0 #000, -1.4px -1.4px 0 #000',
          WebkitFontSmoothing: 'antialiased',
        }}
      >
        {text}
      </span>
    </div>
  );
}

function BoldWorkbench({
  file,
  asrProfile,
  segments,
  currentTime,
  onTimeUpdate,
}: {
  file: DesignFile | null;
  asrProfile: AsrProfileLookup | null;
  segments: SegmentPreview[];
  currentTime: number;
  onTimeUpdate: (t: number) => void;
}) {
  const navigate = useNavigate();
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // Player state — sync'd via <video> events.
  const [isPlaying, setIsPlaying] = useState(false);
  const [videoDuration, setVideoDuration] = useState<number | null>(null);
  const [videoError, setVideoError] = useState(false);

  const fileId = file?.id ?? null;

  // Reset player state whenever a different file is selected.
  // currentTime is lifted — parent resets it on file change.
  useEffect(() => {
    setIsPlaying(false);
    setVideoDuration(null);
    setVideoError(false);
  }, [fileId]);

  // Toggle play/pause via <video> element.
  const handleTogglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      void v.play();
    } else {
      v.pause();
    }
  }, []);

  // Click on waveform or progress bar → seek. Uses bounding rect so the math
  // survives any future flex/padding tweaks on the strip.
  const handleSeekFromBar = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const v = videoRef.current;
      if (!v) return;
      const el = e.currentTarget;
      const rect = el.getBoundingClientRect();
      const dur = v.duration;
      if (!Number.isFinite(dur) || dur <= 0) return;
      const x = e.clientX - rect.left;
      const ratio = Math.max(0, Math.min(1, rect.width === 0 ? 0 : x / rect.width));
      v.currentTime = ratio * dur;
      onTimeUpdate(v.currentTime);
    },
    [onTimeUpdate],
  );

  if (!file) {
    return (
      <div className="workbench">
        <div className="file-header">
          <div className="fh-name" style={{ color: 'var(--text-dim)', fontSize: 14 }}>
            <Icon name="film" size={16} color="var(--border-strong)" />
            <span>尚未選擇檔案</span>
          </div>
        </div>
        <div className="panel">
          <div className="empty">
            <div className="empty-icon">
              <Icon name="film" size={24} color="var(--text-dim)" />
            </div>
            <div className="empty-title">從佇列選擇一個檔案開始</div>
            <div className="empty-sub">點擊左側佇列中的任何檔案，即可在此預覽並進行校對。</div>
          </div>
        </div>
      </div>
    );
  }

  const stem = file.name.replace(/\.(mp4|mov|mxf|wav)$/i, '');
  const TAIL = 8;
  const head = stem.length > TAIL + 4 ? stem.slice(0, -TAIL) : stem;
  const tail = stem.length > TAIL + 4 ? stem.slice(-TAIL) : '';
  const ext = (file.name.match(/\.(\w+)$/) ?? [])[1]?.toUpperCase() ?? '';

  // Use <video>.duration once metadata loads; null until then.
  const realDuration: number | null = videoDuration ?? null;
  const durationLabel = realDuration != null ? fmtTime(realDuration) : null;
  const progressPct =
    realDuration && realDuration > 0
      ? Math.max(0, Math.min(100, (currentTime / realDuration) * 100))
      : 0;

  const mediaUrl = `/api/files/${encodeURIComponent(file.id)}/media`;

  return (
    <div className="workbench" style={{ gridTemplateRows: 'auto 1fr' }}>
      <div className="file-header">
        <div className="fh-name">
          <Icon name="film" size={16} color="var(--accent-2)" />
          <span className="fh-fname" title={file.name}>
            <span className="fh-fname-head">{head}</span>
            {tail && <span className="fh-fname-tail">{tail}</span>}
          </span>
          {ext && <span className="ext">{ext}</span>}
        </div>
        <div className="fh-meta">
          {durationLabel && (
            <div>
              <span className="k">時長</span>
              {durationLabel}
            </div>
          )}
          <div>
            <span className="k">段數</span>
            {file.segments}
          </div>
          <div>
            <span className="k">已批核</span>
            {file.approved}/{file.segments}
          </div>
          {asrProfile?.language && (
            <div>
              <span className="k">語言</span>
              {asrProfile.language}
            </div>
          )}
        </div>
        <div className="fh-actions">
          <button
            className="btn btn-primary"
            onClick={() => navigate(`/proofread/${file.id}`)}
          >
            <Icon name="edit" size={12} />
            校對 →
          </button>
        </div>
      </div>

      {/* Video preview panel — real <video> element */}
      <div className="panel workbench-video" style={{ minHeight: 0, display: 'grid', gridTemplateRows: '1fr' }}>
        <div style={{ position: 'relative', background: '#000', overflow: 'hidden' }}>
          <video
            ref={videoRef}
            src={mediaUrl}
            preload="metadata"
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              background: '#000',
            }}
            onLoadedMetadata={(e) => {
              const v = e.currentTarget;
              const d = v.duration;
              if (Number.isFinite(d) && d > 0) setVideoDuration(d);
              // Force the browser to decode + paint the first frame.
              // preload="metadata" only fetches container metadata; many
              // browsers leave the canvas black until the user plays. Seeking
              // to 0.01 nudges the decoder so a still frame is visible right
              // away — important since dashboard preview is read-only and
              // never auto-plays.
              if (v.currentTime === 0) {
                try { v.currentTime = 0.01; } catch { /* readyState may race */ }
              }
            }}
            onTimeUpdate={(e) => onTimeUpdate(e.currentTarget.currentTime)}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onError={() => setVideoError(true)}
          />
          <VideoSubtitleOverlay segments={segments} currentTime={currentTime} />
          {videoError && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'rgba(255,255,255,0.7)',
                fontSize: 12,
                background: 'rgba(0,0,0,0.6)',
                padding: 16,
                textAlign: 'center',
              }}
            >
              瀏覽器無法預覽呢個格式。請使用「校對」頁面或下載原檔。
            </div>
          )}
          <div
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              bottom: 0,
              padding: '10px 16px',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              background: 'linear-gradient(to top, rgba(0,0,0,0.85), transparent)',
              color: '#fff',
            }}
          >
            <button
              type="button"
              className="play"
              onClick={handleTogglePlay}
              aria-label={isPlaying ? '暫停' : '播放'}
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                background: '#fff',
                color: '#000',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: 'none',
                cursor: 'pointer',
                padding: 0,
              }}
            >
              <Icon name={isPlaying ? 'pause' : 'play'} size={11} color="#000" />
            </button>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                minWidth: 110,
              }}
            >
              {fmtTime(currentTime)} / {durationLabel ?? '0:00'}
            </div>
            <div
              onClick={handleSeekFromBar}
              style={{
                flex: 1,
                height: 4,
                background: 'rgba(255,255,255,0.18)',
                borderRadius: 2,
                overflow: 'hidden',
                cursor: realDuration ? 'pointer' : 'default',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${progressPct}%`,
                  background: 'linear-gradient(90deg, var(--accent), var(--accent-2))',
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// InspectorTranscriptPreview — inline first-N segments preview
// (Un-defers Batch F's deferred 實時字幕 inline preview)
// ---------------------------------------------------------------------------

function fmtTimestamp(sec: number): string {
  const total = Math.max(0, Math.floor(sec));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function InspectorTranscriptPreview({
  segments,
  currentTime,
}: {
  segments: SegmentPreview[];
  currentTime: number;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const activeIdx = findSegmentIdxAtTime(segments, currentTime);

  // Auto-scroll the active row into the middle of the viewport. We pick the
  // row via data-seg-idx attribute so the row → container math is robust to
  // dynamic row heights (variable text length).
  useEffect(() => {
    if (activeIdx < 0) return;
    const container = scrollRef.current;
    if (!container) return;
    const row = container.querySelector<HTMLDivElement>(
      `[data-seg-idx="${activeIdx}"]`,
    );
    if (!row) return;
    const cRect = container.getBoundingClientRect();
    const rRect = row.getBoundingClientRect();
    const offset =
      rRect.top - cRect.top - cRect.height / 2 + rRect.height / 2;
    container.scrollBy({ top: offset, behavior: 'smooth' });
  }, [activeIdx]);

  if (segments.length === 0) {
    return (
      <div className="transcript-scroll">
        <div className="empty"><div className="empty-sub">尚無字幕。Pipeline 完成後將顯示。</div></div>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className="transcript-scroll"
      style={{ padding: 4, fontSize: 12, lineHeight: 1.45, overflowY: 'auto' }}
    >
      {segments.map((s, i) => {
        const isActive = i === activeIdx;
        return (
          <div
            key={i}
            data-seg-idx={i}
            style={{
              display: 'grid',
              gridTemplateColumns: '50px 1fr',
              gap: 8,
              padding: '4px 6px',
              borderRadius: 4,
              background: isActive
                ? 'var(--accent-soft)'
                : i % 2 === 0
                  ? 'transparent'
                  : 'var(--surface-2)',
              borderLeft: isActive ? '2px solid var(--accent)' : '2px solid transparent',
              transition: 'background 120ms ease',
            }}
          >
            <span
              className="dim"
              style={{
                fontSize: 10,
                color: isActive ? 'var(--accent)' : undefined,
                fontWeight: isActive ? 700 : 400,
              }}
            >
              {fmtTimestamp(s.start)}
            </span>
            <span style={{ color: isActive ? 'var(--text)' : undefined, fontWeight: isActive ? 600 : 400 }}>
              {s.text}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// BoldInspector — empty state when no file selected
// ---------------------------------------------------------------------------

/**
 * Compact stage descriptor for the data-driven stages-track. Each step has:
 *   key:       react key + s-step className contribution
 *   label:     primary line shown under the dot (e.g. "ASR" / "MT" / "術語")
 *   sublabel:  secondary line (e.g. "whisper · large-v3", "qwen3.5 · 35b")
 *   stateKind: 'done' | 'active' | 'failed' | 'idle' (drives s-step + dot CSS)
 *   pulse:     true → dot pulses (use when status='running')
 */
interface StagesTrackStep {
  key: string;
  label: string;
  sublabel: string;
  stateKind: 'done' | 'active' | 'failed' | 'idle';
  pulse: boolean;
  showCheck: boolean;
}

/**
 * Read stage_outputs from a file_added socket payload. Backend stores it as
 * `Record<string, StageOutput>` (str-indexed dict, see pipeline_runner.py
 * `_persist_stage_output`). When file_added emits, the dict comes through
 * as-is. `/api/files` list endpoint does NOT include stage_outputs (only
 * segment_count + approved_count), so a freshly-loaded queue will lack it
 * until either file_added fires or the user runs the pipeline.
 *
 * Returns a per-stage-index lookup, normalising whichever shape arrived.
 */
function readPersistedStageOutputs(f: FileRecord | null | undefined): Record<number, { status?: string; stage_type?: string }> {
  if (!f) return {};
  const raw = (f as { stage_outputs?: unknown }).stage_outputs;
  if (!raw) return {};
  const out: Record<number, { status?: string; stage_type?: string }> = {};
  if (Array.isArray(raw)) {
    raw.forEach((item, idx) => {
      if (item && typeof item === 'object') {
        out[idx] = item as { status?: string; stage_type?: string };
      }
    });
    return out;
  }
  if (typeof raw === 'object') {
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
      const idx = Number(k);
      if (Number.isFinite(idx) && v && typeof v === 'object') {
        out[idx] = v as { status?: string; stage_type?: string };
      }
    }
  }
  return out;
}

/**
 * Build the data-driven stages-track step list from the resolved pipeline +
 * per-file Socket.IO live state + persisted stage_outputs from the registry.
 *
 * Stage layout per backend pipeline_runner.py:
 *   index 0           → ASR
 *   index 1..N        → MT (one per `pipeline.mt_stages[]` entry)
 *   index 1 + N       → Glossary (only if glossary_stage.enabled)
 *
 * "校對" and "燒字" are NOT pipeline stages and are intentionally dropped
 * from the track — see audit doc Batch F. They live elsewhere (proofread
 * page is the校對 surface; the workbench "匯出 →" button triggers render).
 */
function buildStagesTrackSteps(
  pipeline: PipelineLookup | null | undefined,
  liveStatus: Record<number, StageStatus> | undefined,
  liveProgress: Record<number, number> | undefined,
  persisted: Record<number, { status?: string; stage_type?: string }>,
  asrProfile: AsrProfileLookup | null | undefined,
  mtProfiles: Array<MtProfileLookup | null | undefined>,
): StagesTrackStep[] {
  if (!pipeline) {
    // Fallback: when pipeline not loaded yet, show a single greyed-out ASR
    // placeholder so the panel doesn't collapse.
    return [
      {
        key: 'asr-pending',
        label: 'ASR',
        sublabel: '—',
        stateKind: 'idle',
        pulse: false,
        showCheck: false,
      },
    ];
  }

  const mtStages = pipeline.mt_stages ?? [];
  const gloss = pipeline.glossary_stage;
  const glossEnabled = !!gloss?.enabled;

  function deriveStateAt(idx: number): { stateKind: StagesTrackStep['stateKind']; pulse: boolean; showCheck: boolean } {
    const live = liveStatus?.[idx];
    if (live === 'failed') return { stateKind: 'failed', pulse: false, showCheck: false };
    if (live === 'done') return { stateKind: 'done', pulse: false, showCheck: true };
    if (live === 'running') return { stateKind: 'active', pulse: true, showCheck: false };
    const persistStatus = persisted[idx]?.status;
    if (persistStatus === 'done') return { stateKind: 'done', pulse: false, showCheck: true };
    if (persistStatus === 'failed') return { stateKind: 'failed', pulse: false, showCheck: false };
    if (persistStatus === 'running') return { stateKind: 'active', pulse: true, showCheck: false };
    return { stateKind: 'idle', pulse: false, showCheck: false };
  }

  const steps: StagesTrackStep[] = [];

  // ASR (always stage 0)
  const asrState = deriveStateAt(0);
  const asrSub = asrProfile
    ? `${asrProfile.engine}${asrProfile.model_size ? ` · ${asrProfile.model_size}` : ''}`
    : '—';
  const asrLiveProgress = liveProgress?.[0];
  steps.push({
    key: 'asr',
    label: 'ASR',
    sublabel: asrState.stateKind === 'active' && typeof asrLiveProgress === 'number' ? `${asrLiveProgress}%` : asrSub,
    ...asrState,
  });

  // MT stages — squash when count > threshold to keep the rail readable.
  if (mtStages.length === 0) {
    // no MT — show a slim placeholder chip
    steps.push({
      key: 'mt-empty',
      label: 'MT',
      sublabel: '— 無翻譯 —',
      stateKind: 'idle',
      pulse: false,
      showCheck: false,
    });
  } else if (mtStages.length > MT_SQUASH_THRESHOLD) {
    // Aggregate across all MT stages. Any failed → failed; any running →
    // active; all done → done; else idle.
    let aggState: StagesTrackStep['stateKind'] = 'idle';
    let aggPulse = false;
    let runningIdx = -1;
    let doneCount = 0;
    for (let i = 0; i < mtStages.length; i++) {
      const idx = 1 + i;
      const s = deriveStateAt(idx);
      if (s.stateKind === 'failed') {
        aggState = 'failed';
        break;
      }
      if (s.stateKind === 'active') {
        aggState = 'active';
        aggPulse = true;
        runningIdx = idx;
      }
      if (s.stateKind === 'done') doneCount++;
    }
    if (aggState === 'idle' && doneCount === mtStages.length) aggState = 'done';
    const runningPct = runningIdx >= 0 ? liveProgress?.[runningIdx] : undefined;
    steps.push({
      key: 'mt-squashed',
      label: `MT × ${mtStages.length}`,
      sublabel:
        aggState === 'active' && typeof runningPct === 'number'
          ? `第 ${runningIdx} 段 · ${runningPct}%`
          : aggState === 'done'
          ? '完成'
          : aggState === 'failed'
          ? '失敗'
          : `${mtStages.length} 段串接`,
      stateKind: aggState,
      pulse: aggPulse,
      showCheck: aggState === 'done',
    });
  } else {
    for (let i = 0; i < mtStages.length; i++) {
      const idx = 1 + i;
      const s = deriveStateAt(idx);
      const prof = mtProfiles[i];
      const baseSub = prof ? `${prof.engine}` : '—';
      const livePct = liveProgress?.[idx];
      steps.push({
        key: `mt-${i}`,
        label: mtStages.length > 1 ? `MT ${i + 1}` : 'MT',
        sublabel: s.stateKind === 'active' && typeof livePct === 'number' ? `${livePct}%` : baseSub,
        ...s,
      });
    }
  }

  // Glossary (only if enabled)
  if (glossEnabled) {
    const idx = 1 + mtStages.length;
    const s = deriveStateAt(idx);
    const count = gloss?.glossary_ids?.length ?? 0;
    const livePct = liveProgress?.[idx];
    steps.push({
      key: 'glossary',
      label: '術語',
      sublabel: s.stateKind === 'active' && typeof livePct === 'number'
        ? `${livePct}%`
        : `${count} 個術語表`,
      ...s,
    });
  }

  return steps;
}

function BoldInspector({
  file,
  fileRecord,
  pipeline,
  asrProfile,
  mtProfiles,
  liveStatus,
  liveProgress,
  segments,
  currentTime,
}: {
  file: DesignFile | null;
  fileRecord: FileRecord | null;
  pipeline: PipelineLookup | null | undefined;
  asrProfile: AsrProfileLookup | null | undefined;
  mtProfiles: Array<MtProfileLookup | null | undefined>;
  liveStatus: Record<number, StageStatus> | undefined;
  liveProgress: Record<number, number> | undefined;
  segments: SegmentPreview[];
  currentTime: number;
}) {
  const [tab, setTab] = useState<'transcript' | 'tuning' | 'info'>('transcript');

  if (!file) {
    return (
      <div className="inspector">
        <div className="panel status-card">
          <div className="empty">
            <div className="empty-icon">
              <Icon name="layers" size={24} color="var(--text-dim)" />
            </div>
            <div className="empty-title">尚未選擇檔案</div>
            <div className="empty-sub">選擇佇列中的檔案以查看處理進度與字幕設定。</div>
          </div>
        </div>
        <div className="panel inspector-tabs-panel">
          <div className="inspector-tabs">
            <button className={tab === 'transcript' ? 'on' : ''} onClick={() => setTab('transcript')}>
              <Icon name="waveform" size={12} /> 實時字幕
            </button>
            <button className={tab === 'tuning' ? 'on' : ''} onClick={() => setTab('tuning')}>
              <Icon name="cog" size={12} /> 字幕設定
            </button>
            <button className={tab === 'info' ? 'on' : ''} onClick={() => setTab('info')}>
              <Icon name="help" size={12} /> 資訊
            </button>
          </div>
          <div className="inspector-body">
            <div className="empty">
              <div className="empty-sub">選擇檔案後顯示內容</div>
            </div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head">
            <div className="title">
              <Icon name="keyboard" size={12} /> 捷徑
            </div>
          </div>
          <div className="panel-body" style={{ paddingTop: 10, paddingBottom: 12 }}>
            <div className="kbd-list">
              <div className="kl">批核 &amp; 下一句</div>
              <span>
                <span className="kbd">⏎</span>
              </span>
              <div className="kl">快速上傳</div>
              <span>
                <span className="kbd">⌘</span>
                <span className="kbd">U</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const pct = file.segments ? Math.round((file.approved / file.segments) * 100) : 0;

  // Data-driven stages-track per audit Batch F: ASR + N MT + Glossary (if
  // enabled). 校對 / 燒字 are user-driven phases, not pipeline stages, so
  // they're dropped here and surfaced via the hint chip below.
  const persistedStages = readPersistedStageOutputs(fileRecord);
  const stagesSteps = buildStagesTrackSteps(
    pipeline,
    liveStatus,
    liveProgress,
    persistedStages,
    asrProfile,
    mtProfiles,
  );
  // Mark pipeline as fully done iff every step resolved to 'done'.
  const allStagesDone = stagesSteps.length > 0 && stagesSteps.every((s) => s.stateKind === 'done');

  // ASR engine/model + language for the 資訊 tab. Hide rows when the
  // lookup hasn't resolved (undefined / null) — fills in on next render once
  // the cache returns.
  const asrEngineLine = asrProfile ? `${asrProfile.engine} · ${asrProfile.model_size ?? ''}` : null;
  // MT engine line: show first stage, and "+N 段" suffix when there are more.
  let mtEngineLine: string | null = null;
  if (mtProfiles.length > 0 && mtProfiles[0]) {
    const first = mtProfiles[0];
    mtEngineLine = first.engine;
    if (mtProfiles.length > 1) {
      mtEngineLine += ` · +${mtProfiles.length - 1} 段`;
    }
  } else if (pipeline && (pipeline.mt_stages ?? []).length === 0) {
    mtEngineLine = '—';
  }
  const langLine = asrProfile?.language ?? null;
  const fontPreview = pipeline?.font_config ?? null;

  return (
    <div className="inspector">
      {/* Status card */}
      <div className="panel status-card">
        <div className="status-card-head">
          <div>
            <div className="sc-k">處理進度</div>
            <div className="sc-v">
              {pct}
              <span className="u">%</span>
            </div>
          </div>
          <MoTitleStageBadge file={file} />
        </div>
        <div className="stages-track">
          {stagesSteps.map((step, i) => {
            // s-link sits between two s-step nodes. The link is "done" only
            // when both this step and the previous step are completed.
            const linkActive = i > 0 && stagesSteps[i - 1]?.stateKind === 'done';
            return (
              <span key={step.key} style={{ display: 'contents' }}>
                {i > 0 && <div className={`s-link ${linkActive ? 'done' : ''}`} />}
                <div className={`s-step ${step.stateKind}`}>
                  <div className={`dot ${step.pulse ? 'pulse' : ''}`}>
                    {step.showCheck && <Icon name="check" size={9} color="#fff" />}
                  </div>
                  <div className="lb">{step.label}</div>
                  <div className="sb">{step.sublabel}</div>
                </div>
              </span>
            );
          })}
        </div>
        <div
          style={{
            marginTop: 10,
            padding: '6px 10px',
            fontSize: 11,
            color: 'var(--text-dim)',
            borderTop: '1px dashed var(--border)',
            lineHeight: 1.5,
          }}
        >
          {allStagesDone
            ? '✓ 完成後可於工作台點擊「校對 →」與「匯出 →」'
            : '校對 / 燒字 為人手步驟，完成後從工作台啟動。'}
        </div>
      </div>

      {/* Tabbed panel */}
      <div className="panel inspector-tabs-panel">
        <div className="inspector-tabs">
          <button
            className={tab === 'transcript' ? 'on' : ''}
            onClick={() => setTab('transcript')}
          >
            <Icon name="waveform" size={12} /> 實時字幕
          </button>
          <button className={tab === 'tuning' ? 'on' : ''} onClick={() => setTab('tuning')}>
            <Icon name="cog" size={12} /> 字幕設定
          </button>
          <button className={tab === 'info' ? 'on' : ''} onClick={() => setTab('info')}>
            <Icon name="help" size={12} /> 資訊
          </button>
        </div>

        {tab === 'transcript' && (
          <div className="inspector-body transcript-body">
            <div className="transcript-sub">
              <div className="ts-head">
                <span className="counter">
                  <b>{file.approved}</b> / {file.segments} 段已批核
                </span>
                <Link
                  to={`/proofread/${file.id}`}
                  style={{ color: 'var(--accent-2)', fontSize: 11 }}
                >
                  校對頁 →
                </Link>
              </div>
              <InspectorTranscriptPreview segments={segments} currentTime={currentTime} />
            </div>
          </div>
        )}

        {tab === 'tuning' && (
          <div className="inspector-body subtitle-settings">
            <div className="sub-preview">
              <div className="sub-preview-label">預覽</div>
              <div
                className="sub-preview-stage"
                style={{
                  background: '#000',
                  display: 'flex',
                  alignItems: 'flex-end',
                  justifyContent: 'center',
                  minHeight: 70,
                  padding: '6px 12px',
                }}
              >
                <div
                  className="sub-preview-text"
                  style={{
                    fontFamily: fontPreview?.family
                      ? `"${fontPreview.family}", system-ui, sans-serif`
                      : undefined,
                    color: fontPreview?.color ?? '#fff',
                    fontSize: fontPreview ? Math.max(12, Math.round(fontPreview.size * 0.4)) : 18,
                    WebkitTextStroke: fontPreview
                      ? `${Math.max(0.5, fontPreview.outline_width * 0.5)}px ${fontPreview.outline_color}`
                      : undefined,
                    fontWeight: 600,
                  }}
                >
                  字幕樣式預覽
                </div>
              </div>
            </div>
            <div className="ss-group">
              <div className="ss-title">字幕設定 (唯讀)</div>
              {fontPreview ? (
                <dl className="info-dl">
                  <dt>字型</dt>
                  <dd title={fontPreview.family}>{fontPreview.family}</dd>
                  <dt>字號</dt>
                  <dd>{fontPreview.size}</dd>
                  <dt>顏色</dt>
                  <dd>
                    <span
                      style={{
                        display: 'inline-block',
                        width: 10,
                        height: 10,
                        background: fontPreview.color,
                        border: '1px solid var(--border)',
                        marginRight: 6,
                        verticalAlign: 'middle',
                      }}
                    />
                    {fontPreview.color}
                  </dd>
                  <dt>輪廓</dt>
                  <dd>
                    {fontPreview.outline_width}px / {fontPreview.outline_color}
                  </dd>
                </dl>
              ) : (
                <div style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.5 }}>
                  Pipeline 字型設定載入中…
                </div>
              )}
              <div
                style={{
                  marginTop: 10,
                  fontSize: 11,
                  color: 'var(--text-dim)',
                  lineHeight: 1.5,
                }}
              >
                此預覽為 Pipeline 預設。需要逐檔調整？
                <Link
                  to={`/proofread/${file.id}`}
                  style={{ color: 'var(--accent-2)', marginLeft: 4 }}
                >
                  編輯 →
                </Link>
              </div>
            </div>
          </div>
        )}

        {tab === 'info' && (
          <div className="inspector-body">
            <div className="info-group">
              <div className="info-title">檔案</div>
              <dl className="info-dl">
                <dt>檔名</dt>
                <dd title={file.name}>{file.name}</dd>
                {/* 時長 — 隱藏直到 backend 加 ffprobe duration 欄位 (audit Batch A) */}
                <dt>大小</dt>
                <dd>{file.size}</dd>
                <dt>段數</dt>
                <dd>{file.segments}</dd>
                <dt>上傳</dt>
                <dd>{file.uploaded}</dd>
              </dl>
            </div>
            <div className="info-group">
              <div className="info-title">Pipeline</div>
              <dl className="info-dl">
                <dt>ASR</dt>
                <dd>{asrEngineLine ?? '—'}</dd>
                <dt>MT</dt>
                <dd>{mtEngineLine ?? '—'}</dd>
                {langLine && (
                  <>
                    <dt>語言</dt>
                    <dd>{langLine}</dd>
                  </>
                )}
              </dl>
            </div>
          </div>
        )}
      </div>

      {/* Keyboard shortcuts */}
      <div className="panel">
        <div className="panel-head">
          <div className="title">
            <Icon name="keyboard" size={12} /> 捷徑
          </div>
        </div>
        <div className="panel-body" style={{ paddingTop: 10, paddingBottom: 12 }}>
          <div className="kbd-list">
            <div className="kl">批核 &amp; 下一句</div>
            <span>
              <span className="kbd">⏎</span>
            </span>
            <div className="kl">切換 Profile</div>
            <span>
              <span className="kbd">⌘</span>
              <span className="kbd">1–3</span>
            </span>
            <div className="kl">快速上傳</div>
            <span>
              <span className="kbd">⌘</span>
              <span className="kbd">U</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard (default export) — full-page Bold variant
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const { state, dispatch } = useSocket();
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [deleteCandidateId, setDeleteCandidateId] = useState<string | null>(null);
  const pipelineId = usePipelinePickerStore((s) => s.pipelineId);
  const pushToast = useUIStore((s) => s.pushToast);

  // Profile-lookup cache — Batch F shared piece for the inspector. Pipeline
  // resolves to its full shape (asr_profile_id + mt_stages + font_config),
  // which cascades to ASR profile + MT profile fetches below.
  const fetchPipeline = useProfileLookupStore((s) => s.fetchPipeline);
  const fetchAsr = useProfileLookupStore((s) => s.fetchAsr);
  const fetchMt = useProfileLookupStore((s) => s.fetchMt);
  const cachedPipelines = useProfileLookupStore((s) => s.pipelines);
  const cachedAsrProfiles = useProfileLookupStore((s) => s.asrProfiles);
  const cachedMtProfiles = useProfileLookupStore((s) => s.mtProfiles);

  // Sort newest first by uploaded_at (Unix epoch). Previous code read
  // `created_at` which backend never sets → undefined, causing every row to
  // resolve to 0 and the sort to be a no-op.
  const filesRaw = useMemo(
    () =>
      Object.values(state.files).sort((a, b) => {
        const ta = typeof a.uploaded_at === 'number' ? a.uploaded_at : 0;
        const tb = typeof b.uploaded_at === 'number' ? b.uploaded_at : 0;
        return tb - ta;
      }),
    [state.files],
  );
  const files: DesignFile[] = useMemo(
    () => filesRaw.map((f) =>
      toDesignFile(f, state.stageProgress[f.id], state.stageStatus[f.id], state.stagePhase[f.id])),
    [filesRaw, state.stageProgress, state.stageStatus, state.stagePhase],
  );

  // Auto-select first file when files load
  useEffect(() => {
    if (!selectedFileId && files.length > 0) {
      setSelectedFileId(files[0]?.id ?? null);
    }
  }, [files, selectedFileId]);

  const selectedFile = files.find((f) => f.id === selectedFileId) ?? null;
  const selectedFileRecord = selectedFileId ? filesRaw.find((r) => r.id === selectedFileId) ?? null : null;
  const deleteCandidate = deleteCandidateId
    ? files.find((f) => f.id === deleteCandidateId) ?? null
    : null;

  // Lift currentTime + segments here so the Workbench's <video> playhead
  // drives both the subtitle overlay (above the video) and the Inspector's
  // 實時字幕 preview (auto-scroll + highlight current line).
  const [currentTime, setCurrentTime] = useState(0);

  // Lang picker state — defaults to the file's source_lang once the hook
  // resolves; we reset on file change so old lang doesn't bleed across files.
  const [activeLang, setActiveLang] = useState<string>('zh');
  useEffect(() => {
    setCurrentTime(0);
    setActiveLang('zh');
  }, [selectedFileId]);

  // Replaces the legacy /api/files/<id>/segments fetch. The hook now sources
  // the live overlay from v5 by_lang (verifier-corrected + refined text) and
  // falls back to /segments only when translations are empty.
  const {
    segments,
    availableLangs,
    sourceLang,
  } = useDashboardTranslations(selectedFileId ?? null, activeLang);

  // Promote source_lang to activeLang once the hook discovers it, so the
  // first paint after a file change picks the right lang automatically.
  useEffect(() => {
    if (sourceLang && availableLangs.includes(sourceLang)) {
      setActiveLang(sourceLang);
    } else if (availableLangs.length > 0 && !availableLangs.includes(activeLang)) {
      const first = availableLangs[0];
      if (first) setActiveLang(first);
    }
    // Intentionally exclude activeLang to avoid resetting after the user picks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceLang, availableLangs.join('|')]);

  // Resolve the active pipeline (preferred: per-file pipeline_id; fall back to
  // the dashboard-level pipelineId from the picker). Cascade fetch ASR profile
  // + MT profiles so the inspector can render derived 引擎/模型/語言 rows.
  const activePipelineId =
    (selectedFileRecord && (selectedFileRecord.pipeline_id as string | null | undefined)) ||
    pipelineId ||
    null;

  useEffect(() => {
    if (activePipelineId) {
      void fetchPipeline(activePipelineId);
    }
  }, [activePipelineId, fetchPipeline]);

  const activePipeline = activePipelineId ? cachedPipelines[activePipelineId] ?? null : null;

  useEffect(() => {
    if (activePipeline?.asr_profile_id) {
      void fetchAsr(activePipeline.asr_profile_id);
    }
    if (activePipeline?.mt_stages) {
      for (const mtId of activePipeline.mt_stages) {
        void fetchMt(mtId);
      }
    }
  }, [activePipeline, fetchAsr, fetchMt]);

  const asrProfile = activePipeline?.asr_profile_id
    ? cachedAsrProfiles[activePipeline.asr_profile_id] ?? null
    : null;
  const mtProfiles = useMemo(
    () => (activePipeline?.mt_stages ?? []).map((id) => cachedMtProfiles[id] ?? null),
    [activePipeline, cachedMtProfiles],
  );

  const inspectorLiveStatus = selectedFileId ? state.stageStatus[selectedFileId] : undefined;
  const inspectorLiveProgress = selectedFileId ? state.stageProgress[selectedFileId] : undefined;

  const handleRun = useCallback(async () => {
    if (!selectedFileId) {
      pushToast({ title: '請先揀檔案', variant: 'destructive' });
      return;
    }
    if (!pipelineId) {
      pushToast({ title: '請先揀 Pipeline', variant: 'destructive' });
      return;
    }
    try {
      await apiFetch<{ job_id: string }>(`/api/pipelines/${pipelineId}/run`, {
        method: 'POST',
        body: JSON.stringify({ file_id: selectedFileId }),
      });
      // Optimistic — flip the row to 'queued' immediately so the user gets
      // sub-100ms visual confirmation of the click before backend pickup.
      dispatch({
        type: 'STAGE_START',
        ev: { file_id: selectedFileId, stage_index: 0, stage_type: 'asr', phase: 'queued' },
      });
      pushToast({ title: '✅ 已排隊' });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      pushToast({ title: '排隊失敗', description: msg, variant: 'destructive' });
    }
  }, [selectedFileId, pipelineId, pushToast, dispatch]);

  const handleRunFile = useCallback(async (fileId: string) => {
    if (!pipelineId) {
      pushToast({ title: '請先揀 Pipeline', variant: 'destructive' });
      return;
    }
    try {
      await apiFetch<{ job_id: string }>(`/api/pipelines/${pipelineId}/run`, {
        method: 'POST',
        body: JSON.stringify({ file_id: fileId }),
      });
      dispatch({
        type: 'STAGE_START',
        ev: { file_id: fileId, stage_index: 0, stage_type: 'asr', phase: 'queued' },
      });
      pushToast({ title: '✅ 已排隊' });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      pushToast({ title: '排隊失敗', description: msg, variant: 'destructive' });
    }
  }, [pipelineId, pushToast, dispatch]);

  const handleConfirmDelete = useCallback(async () => {
    if (!deleteCandidateId) return;
    const fileId = deleteCandidateId;
    setDeleteCandidateId(null);
    try {
      await apiFetch(`/api/files/${fileId}`, { method: 'DELETE' });
      // Backend has no FILE_REMOVED broadcast — dispatch locally so the queue
      // updates immediately without a full refetch.
      dispatch({ type: 'FILE_REMOVED', file_id: fileId });
      // If the deleted file was selected, clear selection.
      if (selectedFileId === fileId) setSelectedFileId(null);
      pushToast({ title: '已刪除檔案' });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      pushToast({ title: '刪除失敗', description: msg, variant: 'destructive' });
    }
  }, [deleteCandidateId, dispatch, pushToast, selectedFileId]);

  return (
    <div className="motitle-bold">
      <div className="bold">
        <BoldRail />
        <div className="b-main">
          <BoldTopbar onRun={handleRun} />
          <div className="b-body">
            {/* Left col: DropHero + Queue */}
            <div className="b-col">
              <DropHero onUploaded={setSelectedFileId} />
              <div className="panel queue-panel">
                <div className="panel-head">
                  <div className="title">
                    <Icon name="layers" size={12} /> 佇列{' '}
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--text-dim)',
                        fontWeight: 500,
                        letterSpacing: 0,
                        marginLeft: 4,
                      }}
                    >
                      · {files.length}
                    </span>
                  </div>
                  <div className="spacer" />
                  <button className="btn btn-ghost btn-sm">全部 ▾</button>
                </div>
                <div className="panel-body" style={{ paddingTop: 10 }}>
                  {files.length === 0 ? (
                    <div className="empty">
                      <div className="empty-icon">
                        <Icon name="film" size={24} color="var(--text-dim)" />
                      </div>
                      <div className="empty-title">佇列為空</div>
                      <div className="empty-sub">拖放影片或音訊檔案以開始。</div>
                    </div>
                  ) : (
                    files.map((f) => (
                      <QueueItem
                        key={f.id}
                        f={f}
                        onSelect={(df) => setSelectedFileId(df.id)}
                        active={f.id === selectedFileId}
                        onDelete={(fileId) => setDeleteCandidateId(fileId)}
                        onRun={handleRunFile}
                        pipelineId={pipelineId}
                      />
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* Middle col: Workbench */}
            <BoldWorkbench
              file={selectedFile}
              asrProfile={asrProfile}
              segments={segments}
              currentTime={currentTime}
              onTimeUpdate={setCurrentTime}
            />

            {/* Right col: Inspector */}
            <BoldInspector
              file={selectedFile}
              fileRecord={selectedFileRecord}
              pipeline={activePipeline}
              asrProfile={asrProfile}
              mtProfiles={mtProfiles}
              liveStatus={inspectorLiveStatus}
              liveProgress={inspectorLiveProgress}
              segments={segments}
              currentTime={currentTime}
            />
          </div>
        </div>
      </div>
      <ConfirmDialog
        open={deleteCandidateId !== null}
        title="刪除此檔案？"
        description={
          deleteCandidate
            ? `確定要刪除「${deleteCandidate.name}」？所有相關字幕同進度將會一併移除，無法復原。`
            : undefined
        }
        confirmLabel="刪除"
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteCandidateId(null)}
      />
    </div>
  );
}
