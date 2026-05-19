// Dashboard — Bold variant redesign
// Pixel-faithful port of /tmp/v4-design/motitle/project/variant-bold.jsx
// This component renders a full-page layout that bypasses the parent Layout shell.
import { useState, useCallback, useEffect, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import { useSocket } from '@/providers/SocketProvider';
import { usePipelinePickerStore } from '@/stores/pipeline-picker';
import type { PipelineBrokenRefs, PipelineSummary } from '@/stores/pipeline-picker';
import { useUIStore } from '@/stores/ui';
import { useProfileLookupStore } from '@/stores/profile-lookup';
import type {
  AsrProfileLookup,
  MtProfileLookup,
  PipelineLookup,
} from '@/stores/profile-lookup';
import { apiFetch, ApiError } from '@/lib/api';
import type { FileRecord, StageStatus } from '@/lib/socket-events';
import { Icon, MoTitleStageBadge } from '@/lib/motitle-icons';
import type { IconName } from '@/lib/motitle-icons';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import '@/styles/motitle-bold.css';

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
  /** derived stage string for display */
  stage: string;
  transcribeProgress: number;
  renderProgress: number;
  size: string;
}

/**
 * Map a backend FileRecord (GET /api/files row) into the design shape consumed
 * by Bold-variant queue/workbench/inspector. Socket-derived live progress is
 * threaded in via `stageProgress`/`stageStatus` so we do not depend on backend
 * to set a per-record `transcribe_progress` field (it doesn't).
 */
function toDesignFile(
  f: FileRecord,
  stageProgress: Record<number, number> | undefined,
  stageStatus: Record<number, import('@/lib/socket-events').StageStatus> | undefined,
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

function stageForStagePill(stage: string): { asr: string; mt: string } {
  if (stage === 'error') return { asr: 'err', mt: 'err' };
  if (stage === 'transcribing') return { asr: 'warn', mt: 'idle' };
  if (stage === 'translating') return { asr: 'ok', mt: 'warn' };
  if (stage === 'proofreading' || stage === 'rendering' || stage === 'done') return { asr: 'ok', mt: 'ok' };
  return { asr: 'idle', mt: 'idle' };
}

// ---------------------------------------------------------------------------
// BoldRail
// ---------------------------------------------------------------------------

const RAIL_ITEMS: Array<{ id: string; icon: IconName; label: string; href: string }> = [
  { id: 'home',     icon: 'home',   label: '主頁',     href: '/' },
  { id: 'files',    icon: 'film',   label: '檔案',     href: '/' },
  { id: 'proof',    icon: 'edit',   label: '校對',     href: '/' },
  { id: 'pipeline', icon: 'flow',   label: 'Pipeline', href: '/pipelines' },
  { id: 'gloss',    icon: 'book',   label: '術語表',   href: '/glossaries' },
  { id: 'lang',     icon: 'layers', label: '語言配置', href: '/' },
];

function BoldRail() {
  return (
    <div className="b-rail">
      <div className="mark">M</div>
      {RAIL_ITEMS.map((it) => (
        <Link key={it.id} to={it.href} className={`rail-btn ${it.id === 'home' ? 'on' : ''}`}>
          <Icon name={it.icon} size={16} />
          <span className="tt">{it.label}</span>
        </Link>
      ))}
      <div className="flex1" />
      <button className="rail-btn" title="通知">
        <Icon name="bell" size={16} />
        <span className="tt">通知</span>
      </button>
      <button className="rail-btn" title="設定">
        <Icon name="cog" size={16} />
        <span className="tt">設定</span>
      </button>
      <button className="rail-btn" title="說明">
        <Icon name="help" size={16} />
        <span className="tt">說明</span>
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PipelineStrip — reads from usePipelinePickerStore
// ---------------------------------------------------------------------------

interface StepMenuOption {
  name: string;
  badge?: string;
  desc?: string;
  current?: boolean;
}

function PipelineStep({
  icon,
  k,
  v,
  options,
  width = 180,
  alignRight = false,
}: {
  icon: IconName;
  k: string;
  v: string;
  options: StepMenuOption[];
  width?: number;
  alignRight?: boolean;
}) {
  return (
    <div className="step" style={{ position: 'relative' }}>
      <Icon name={icon} size={12} color="var(--accent-2)" />
      <div>
        <div className="k">{k}</div>
        <div className="v">{v}</div>
      </div>
      <Icon name="caret" size={10} />
      <div className="step-menu" style={{ minWidth: width, ...(alignRight ? { left: 'auto', right: 0 } : {}) }}>
        <div className="step-menu-head">{k} · 選擇</div>
        {options.map((o, i) => (
          <button key={i} className={o.current ? 'on' : ''}>
            <div className="smn-main">
              <span className="smn-name">{o.name}</span>
              {o.badge && <span className="smn-badge">{o.badge}</span>}
            </div>
            {o.desc && <div className="smn-desc">{o.desc}</div>}
          </button>
        ))}
        <div className="split-divider" />
        <button className="smn-manage">
          <span className="fmt-badge outline">⚙</span>
          <span className="fmt-desc">管理 / 新增…</span>
        </button>
      </div>
    </div>
  );
}

function PipelineStrip() {
  const { pipelines, pipelineId, setPipelineId, refresh } = usePipelinePickerStore();

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const activePipeline = pipelines.find((p) => p.id === pipelineId) ?? pipelines[0];
  const activeName = activePipeline?.name ?? '新聞廣播 · TC';
  const activeBrokenTooltip = brokenRefsTooltip(activePipeline);

  return (
    <div className="pipeline-strip" title="當前 Pipeline 組合">
      <div className="pipeline-preset-wrap" style={{ position: 'relative' }}>
        <button className="pipeline-preset" title="切換 Pipeline 預設">
          <Icon name="flow" size={13} color="var(--accent)" />
          <div className="pp-text">
            <div className="pp-k">Pipeline</div>
            <div className="pp-v" style={{ display: 'inline-flex', alignItems: 'center' }}>
              {activeName}
              {hasBrokenRefs(activePipeline) && (
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
      <PipelineStep
        icon="waveform"
        k="ASR"
        v="large-v3"
        options={[
          { name: 'large-v3', badge: 'GPU', desc: '最高準確度 · 慢 1.0×', current: true },
          { name: 'medium', badge: 'GPU', desc: '平衡 · 0.4× RT' },
          { name: 'small', badge: 'CPU', desc: '快速 · 0.15× RT' },
        ]}
      />
      <span className="arrow">→</span>
      <PipelineStep
        icon="layers"
        k="MT"
        v="qwen3:235b"
        options={[
          { name: 'qwen3:235b', badge: '本地', desc: '142 tok/s · 香港中文最佳', current: true },
          { name: 'qwen3:32b', badge: '本地', desc: '380 tok/s · 日常稿件' },
          { name: 'DeepSeek V3', badge: 'API', desc: '成本較低 · 準確度高' },
          { name: 'GPT-4o', badge: 'API', desc: '高品質 · 較貴' },
        ]}
        width={220}
      />
      <span className="arrow">→</span>
      <PipelineStep
        icon="film"
        k="輸出"
        v="H.264 · MP4"
        options={[
          { name: 'H.264 · MP4', desc: '通用播放 · CRF 20', current: true },
          { name: 'ProRes · MOV', desc: '後期剪輯 · 大檔案' },
          { name: 'VP9 · WebM', desc: '網頁串流' },
          { name: '— 只輸出字幕 —', desc: '不重新編碼影片' },
        ]}
      />
      <span className="arrow">→</span>
      <div className="step step-gloss" title="執行時套用嘅術語表" style={{ position: 'relative' }}>
        <Icon name="book" size={12} color="var(--accent)" />
        <div>
          <div className="k">術語表</div>
          <div className="v">—</div>
        </div>
        <Icon name="caret" size={10} />
        <div className="step-menu" style={{ minWidth: 240, right: 0, left: 'auto' }}>
          <div className="step-menu-head">術語表 · 選擇</div>
          <button>
            <div className="smn-main">
              <span className="smn-name">— 不使用 —</span>
            </div>
            <div className="smn-desc">跳過術語校正</div>
          </button>
          <div className="split-divider" />
          <Link to="/glossaries" style={{ display: 'flex', gap: 8, padding: '7px 10px', borderRadius: 6, fontSize: 13, color: 'var(--text-mid)', alignItems: 'center' }}>
            <span className="fmt-badge outline">+</span>
            <span className="fmt-desc">新增 / 管理術語表…</span>
          </Link>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// BoldTopbar
// ---------------------------------------------------------------------------

function BoldTopbar({ onRun }: { onRun?: () => void }) {
  const { state: socketState } = useSocket();
  const [asrEngines, setAsrEngines] = useState<EngineProbeItem[] | null>(null);
  const [mtEngines, setMtEngines] = useState<EngineProbeItem[] | null>(null);

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
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DropHero — wired to upload handler
// ---------------------------------------------------------------------------

function DropHero() {
  const pipelineId = usePipelinePickerStore((s) => s.pipelineId);
  const pushToast = useUIStore((s) => s.pushToast);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (!acceptedFiles.length) return;
      for (const file of acceptedFiles) {
        const fd = new FormData();
        fd.append('file', file);
        if (pipelineId) fd.append('pipeline_id', pipelineId);
        try {
          const r = await fetch('/api/transcribe', {
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
          }
        } catch (e) {
          pushToast({ title: '上傳失敗', description: String(e), variant: 'destructive' });
        }
      }
    },
    [pipelineId, pushToast]
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
}: {
  f: DesignFile;
  onSelect: (f: DesignFile) => void;
  active: boolean;
  onDelete: (fileId: string) => void;
}) {
  const stages = stageForStagePill(f.stage);

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
        <div className={`stage-pill ${stages.asr}`}>
          <span className="lb">ASR</span>
          <span>
            {f.stage === 'transcribing'
              ? `${f.transcribeProgress}%`
              : stages.asr === 'ok'
              ? '完成'
              : stages.asr === 'err'
              ? '失敗'
              : '—'}
          </span>
        </div>
        <div className={`stage-pill ${stages.mt}`}>
          <span className="lb">MT</span>
          <span>
            {f.stage === 'translating'
              ? '翻譯中'
              : stages.mt === 'ok'
              ? '完成'
              : stages.mt === 'err'
              ? '失敗'
              : '—'}
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// BoldWorkbench — empty state when no file selected
// ---------------------------------------------------------------------------

function BoldWorkbench({ file }: { file: DesignFile | null }) {
  const navigate = useNavigate();

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

  return (
    <div className="workbench">
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
          <div>
            <span className="k">時長</span>
            {file.duration}
          </div>
          <div>
            <span className="k">段數</span>
            {file.segments}
          </div>
          <div>
            <span className="k">已批核</span>
            {file.approved}/{file.segments}
          </div>
          {/* 語言 row removed in Batch F — to be wired back via pipeline lookup in Batch E */}
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

      {/* Video preview panel — stub */}
      <div className="panel" style={{ minHeight: 0, display: 'grid', gridTemplateRows: '1fr auto' }}>
        <div style={{ position: 'relative', background: '#000', overflow: 'hidden' }}>
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'linear-gradient(135deg, #1a1a2a, #0a0a14)',
            }}
          >
            <div
              style={{
                position: 'absolute',
                top: 14,
                left: 16,
                fontSize: 10,
                color: 'rgba(255,255,255,0.4)',
                fontFamily: 'var(--font-mono)',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
              }}
            >
              [ video preview · coming next phase ]
            </div>
          </div>
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
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                background: '#fff',
                color: '#000',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Icon name="play" size={11} color="#000" />
            </div>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                minWidth: 110,
              }}
            >
              00:00 / {file.duration}
            </div>
            <div
              style={{
                flex: 1,
                height: 4,
                background: 'rgba(255,255,255,0.18)',
                borderRadius: 2,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: '0%',
                  background: 'linear-gradient(90deg, var(--accent), var(--accent-2))',
                }}
              />
            </div>
          </div>
        </div>
        <div
          style={{
            borderTop: '1px solid var(--border)',
            padding: '10px 16px',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            background: 'var(--surface)',
          }}
        >
          <Icon name="waveform" size={13} color="var(--text-mid)" />
          <div
            style={{
              flex: 1,
              display: 'flex',
              gap: 2,
              alignItems: 'center',
              height: 28,
            }}
          >
            {Array.from({ length: 80 }).map((_, i) => {
              const h = 8 + Math.abs(Math.sin(i * 0.31)) * 18;
              return (
                <div
                  key={i}
                  style={{
                    width: 3,
                    height: h,
                    background: 'var(--border-strong)',
                    borderRadius: 1,
                    flexShrink: 0,
                  }}
                />
              );
            })}
          </div>
          <span className="mono dim">波形預覽</span>
        </div>
      </div>
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

/** Squash threshold: more than this many MT stages collapses into one chip. */
const MT_SQUASH_THRESHOLD = 3;

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
}: {
  file: DesignFile | null;
  fileRecord: FileRecord | null;
  pipeline: PipelineLookup | null | undefined;
  asrProfile: AsrProfileLookup | null | undefined;
  mtProfiles: Array<MtProfileLookup | null | undefined>;
  liveStatus: Record<number, StageStatus> | undefined;
  liveProgress: Record<number, number> | undefined;
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
                <div className="ts-filter">
                  <button className="on">全部</button>
                  <button>未批核</button>
                  <button>已編輯</button>
                </div>
              </div>
              <div className="transcript-scroll">
                <div className="empty">
                  <div className="empty-sub">
                    前往
                    <Link
                      to={`/proofread/${file.id}`}
                      style={{ color: 'var(--accent-2)', margin: '0 4px' }}
                    >
                      校對頁面
                    </Link>
                    以查看完整字幕列表
                  </div>
                </div>
              </div>
              <div className="ts-foot">
                <span className="kbd">J</span>
                <span className="kbd">K</span>
                <span className="dim" style={{ fontSize: 11 }}>
                  上/下一句
                </span>
              </div>
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
    () => filesRaw.map((f) => toDesignFile(f, state.stageProgress[f.id], state.stageStatus[f.id])),
    [filesRaw, state.stageProgress, state.stageStatus],
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
      pushToast({ title: '✅ 已排隊' });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      pushToast({ title: '排隊失敗', description: msg, variant: 'destructive' });
    }
  }, [selectedFileId, pipelineId, pushToast]);

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
              <DropHero />
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
                      />
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* Middle col: Workbench */}
            <BoldWorkbench file={selectedFile} />

            {/* Right col: Inspector */}
            <BoldInspector
              file={selectedFile}
              fileRecord={selectedFileRecord}
              pipeline={activePipeline}
              asrProfile={asrProfile}
              mtProfiles={mtProfiles}
              liveStatus={inspectorLiveStatus}
              liveProgress={inspectorLiveProgress}
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
