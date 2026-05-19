// Dashboard — Bold variant redesign
// Pixel-faithful port of /tmp/v4-design/motitle/project/variant-bold.jsx
// This component renders a full-page layout that bypasses the parent Layout shell.
import { useState, useCallback, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import { useSocket } from '@/providers/SocketProvider';
import { usePipelinePickerStore } from '@/stores/pipeline-picker';
import { useUIStore } from '@/stores/ui';
import { apiFetch } from '@/lib/api';
import type { FileRecord } from '@/lib/socket-events';
import { Icon, MoTitleStageBadge } from '@/lib/motitle-icons';
import type { IconName } from '@/lib/motitle-icons';
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
  language: string;
  asrEngine: string;
  asrModel: string;
  mtEngine: string;
  mtModel: string;
}

function toDesignFile(f: FileRecord): DesignFile {
  // Derive stage from FileRecord.status
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
  const createdAt = typeof f.created_at === 'number' ? f.created_at : 0;
  const ageSec = createdAt > 0 ? (Date.now() / 1000 - createdAt) : 0;
  let uploaded = '—';
  if (ageSec < 120) uploaded = '剛剛';
  else if (ageSec < 3600) uploaded = `${Math.floor(ageSec / 60)} 分鐘前`;
  else if (ageSec < 86400) uploaded = `${Math.floor(ageSec / 3600)} 小時前`;
  else uploaded = `${Math.floor(ageSec / 86400)} 日前`;

  return {
    id: f.id,
    name,
    duration: String(f.duration ?? '?:??'),
    segments: typeof f.segments === 'number' ? f.segments : (typeof f.segment_count === 'number' ? f.segment_count as number : 0),
    approved: typeof f.approved_count === 'number' ? f.approved_count as number : 0,
    uploaded,
    stage,
    transcribeProgress: typeof f.transcribe_progress === 'number' ? f.transcribe_progress as number : 0,
    renderProgress: typeof f.render_progress === 'number' ? f.render_progress as number : 0,
    size: String(f.file_size ?? '—'),
    language: String(f.language ?? 'English → 繁體中文'),
    asrEngine: String(f.asr_engine ?? '—'),
    asrModel: String(f.asr_model ?? '—'),
    mtEngine: String(f.mt_engine ?? '—'),
    mtModel: String(f.mt_model ?? '—'),
  };
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

  return (
    <div className="pipeline-strip" title="當前 Pipeline 組合">
      <div className="pipeline-preset-wrap" style={{ position: 'relative' }}>
        <button className="pipeline-preset" title="切換 Pipeline 預設">
          <Icon name="flow" size={13} color="var(--accent)" />
          <div className="pp-text">
            <div className="pp-k">Pipeline</div>
            <div className="pp-v">{activeName}</div>
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
            pipelines.map((p) => (
              <button
                key={p.id}
                className={p.id === pipelineId ? 'on' : ''}
                onClick={() => setPipelineId(p.id)}
              >
                <div className="smn-main">
                  <span className="smn-name">{p.name}</span>
                  {p.id === pipelineId && <span className="smn-badge">當前</span>}
                </div>
                {p.description && <div className="smn-desc">{p.description}</div>}
              </button>
            ))
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
          <button className="save-btn" title="儲存當前 Pipeline 為預設">
            💾 儲存
          </button>
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
}: {
  f: DesignFile;
  onSelect: (f: DesignFile) => void;
  active: boolean;
}) {
  const stages = stageForStagePill(f.stage);
  const [confirm, setConfirm] = useState(false);

  return (
    <div
      className={`queue-item ${active ? 'active' : ''} ${confirm ? 'confirming' : ''}`}
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
          className={`qi-del ${confirm ? 'armed' : ''}`}
          title={confirm ? '再撳一次確認刪除' : '刪除此檔案'}
          onClick={(e) => {
            e.stopPropagation();
            if (confirm) {
              setConfirm(false);
              // TODO: call DELETE /api/files/<id>
            } else {
              setConfirm(true);
              setTimeout(() => setConfirm(false), 3000);
            }
          }}
        >
          {confirm ? <Icon name="check" size={10} /> : <Icon name="x" size={10} />}
        </button>
      </div>
      <div className="qm">
        <span>{f.duration}</span>
        <span style={{ color: 'var(--border-strong)' }}>·</span>
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
          <div>
            <span className="k">語言</span>
            {file.language}
          </div>
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

function BoldInspector({ file }: { file: DesignFile | null }) {
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

  // Derive stage step states
  const hasAsr = ['translating', 'proofreading', 'rendering', 'done'].includes(file.stage);
  const hasMt = ['proofreading', 'rendering', 'done'].includes(file.stage);
  const isProofreading = file.stage === 'proofreading';
  const isDone = file.stage === 'done';
  const isRendering = file.stage === 'rendering';

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
          <div className={`s-step ${hasAsr ? 'done' : file.stage === 'transcribing' ? 'active' : 'idle'}`}>
            <div className={`dot ${file.stage === 'transcribing' ? 'pulse' : ''}`}>
              {hasAsr && <Icon name="check" size={9} color="#fff" />}
            </div>
            <div className="lb">ASR</div>
            <div className="sb">whisper</div>
          </div>
          <div className={`s-link ${hasAsr ? 'done' : ''}`} />
          <div className={`s-step ${hasMt ? 'done' : file.stage === 'translating' ? 'active' : 'idle'}`}>
            <div className={`dot ${file.stage === 'translating' ? 'pulse' : ''}`}>
              {hasMt && <Icon name="check" size={9} color="#fff" />}
            </div>
            <div className="lb">MT</div>
            <div className="sb">ollama</div>
          </div>
          <div className={`s-link ${hasMt ? 'done' : isProofreading ? 'active' : ''}`} />
          <div className={`s-step ${isDone || isRendering ? 'done' : isProofreading ? 'active' : 'idle'}`}>
            <div className={`dot ${isProofreading ? 'pulse' : ''}`}>
              {(isDone || isRendering) && <Icon name="check" size={9} color="#fff" />}
            </div>
            <div className="lb">校對</div>
            <div className="sb">
              {file.approved}/{file.segments}
            </div>
          </div>
          <div className={`s-link ${isDone ? 'done' : isRendering ? 'active' : ''}`} />
          <div className={`s-step ${isDone ? 'done' : isRendering ? 'active' : 'idle'}`}>
            <div className={`dot ${isRendering ? 'pulse' : ''}`}>
              {isDone && <Icon name="check" size={9} color="#fff" />}
            </div>
            <div className="lb">燒字</div>
            <div className="sb">{isRendering ? `${file.renderProgress}%` : isDone ? '完成' : '—'}</div>
          </div>
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
              <div className="sub-preview-stage">
                <div className="sub-preview-text" style={{ fontSize: '18px' }}>
                  字幕樣式預覽
                </div>
              </div>
            </div>
            <div className="ss-group">
              <div className="ss-title">字幕設定</div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.5 }}>
                前往
                <Link
                  to={`/proofread/${file.id}`}
                  style={{ color: 'var(--accent-2)', margin: '0 4px' }}
                >
                  校對頁面
                </Link>
                以調整字幕字型、大小、顏色及位置。
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
                <dt>時長</dt>
                <dd>{file.duration}</dd>
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
                <dd>
                  {file.asrEngine} · {file.asrModel}
                </dd>
                <dt>MT</dt>
                <dd>
                  {file.mtEngine} · {file.mtModel}
                </dd>
                <dt>語言</dt>
                <dd>{file.language}</dd>
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
  const { state } = useSocket();
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);

  const files: DesignFile[] = Object.values(state.files)
    .sort((a, b) => {
      const ta = typeof a.created_at === 'number' ? a.created_at : 0;
      const tb = typeof b.created_at === 'number' ? b.created_at : 0;
      return tb - ta;
    })
    .map(toDesignFile);

  // Auto-select first file when files load
  useEffect(() => {
    if (!selectedFileId && files.length > 0) {
      setSelectedFileId(files[0]?.id ?? null);
    }
  }, [files, selectedFileId]);

  const selectedFile = files.find((f) => f.id === selectedFileId) ?? null;

  return (
    <div className="motitle-bold">
      <div className="bold">
        <BoldRail />
        <div className="b-main">
          <BoldTopbar />
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
                      />
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* Middle col: Workbench */}
            <BoldWorkbench file={selectedFile} />

            {/* Right col: Inspector */}
            <BoldInspector file={selectedFile} />
          </div>
        </div>
      </div>
    </div>
  );
}
