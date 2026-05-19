// src/pages/Proofread/index.tsx
// Iter 1 of the Bold variant rollout — full-page motitle-bold layout matching
// Dashboard.tsx structure (b-rail + b-main > b-topbar + b-body 3-col grid).
// Preserves all v3 functionality (segment editing, find-replace, stage history,
// glossary apply, render modal, prompt overrides, keyboard shortcuts).
import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useSocket } from '@/providers/SocketProvider';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Icon } from '@/lib/motitle-icons';
import { BoldRail } from '@/components/BoldRail';
import { TopBar } from './TopBar';
import { VideoPanel } from './VideoPanel';
import { SegmentTable } from './SegmentTable';
import { FindReplaceToolbar } from './FindReplaceToolbar';
import { StageHistorySidebar } from './StageHistorySidebar';
import { PromptOverridesDrawer } from './PromptOverridesDrawer';
import { GlossaryApplyModal } from './GlossaryApplyModal';
import { GlossaryPanel } from './GlossaryPanel';
import { SubtitleSettingsPanel } from './SubtitleSettingsPanel';
import { RenderModal } from './RenderModal';
import { useFileData } from './hooks/useFileData';
import { useFilePipeline } from './hooks/useFilePipeline';
import { useFindReplace } from './hooks/useFindReplace';
import type { Replacement } from './hooks/useFindReplace';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { useRenderJob } from './hooks/useRenderJob';
import type { RenderOptions } from '@/lib/schemas/render-options';
import '@/styles/motitle-bold.css';

export default function Proofread() {
  const { fileId } = useParams<{ fileId: string }>();
  if (!fileId) return <p className="p-4 text-destructive">No file ID in route.</p>;
  return <ProofreadInner fileId={fileId} />;
}

function ProofreadInner({ fileId }: { fileId: string }) {
  const { file, translations, loading, error, refresh } = useFileData(fileId);
  const { font, glossaryId, refresh: refreshPipeline } = useFilePipeline(
    file?.pipeline_id ?? null,
  );
  const fr = useFindReplace(translations);
  const { state: socketState } = useSocket();

  const [findOpen, setFindOpen] = useState(false);
  const [overridesOpen, setOverridesOpen] = useState(false);
  const [renderOpen, setRenderOpen] = useState(false);
  const [historyOpenIdx, setHistoryOpenIdx] = useState<number | null>(null);
  const [glossaryApplyOpen, setGlossaryApplyOpen] = useState(false);

  // Playhead drives both the subtitle overlay (above <video>) and the active
  // row highlight in the SegmentTable. Lifted here so VideoPanel + SegmentTable
  // share the same source of truth.
  const [currentTime, setCurrentTime] = useState(0);

  const {
    currentJob,
    startRender,
    cancel: cancelRender,
    downloadWithPicker,
    clear: clearRender,
  } = useRenderJob();

  // Refresh when stage runs complete for this file
  const myStatus = socketState.files[fileId]?.status;
  useEffect(() => {
    if (myStatus === 'completed') refresh();
  }, [myStatus, refresh]);

  // Auto-download once when render completes
  const completedRenderId = useRef<string | null>(null);
  useEffect(() => {
    if (
      currentJob?.status === 'completed' &&
      currentJob.render_id !== completedRenderId.current
    ) {
      completedRenderId.current = currentJob.render_id;
      void downloadWithPicker().then(() => clearRender());
    }
  }, [currentJob, downloadWithPicker, clearRender]);

  useKeyboardShortcuts({
    onFindOpen: () => setFindOpen(true),
    onEscape: () => {
      if (renderOpen) setRenderOpen(false);
      else if (glossaryApplyOpen) setGlossaryApplyOpen(false);
      else if (overridesOpen) setOverridesOpen(false);
      else if (historyOpenIdx !== null) setHistoryOpenIdx(null);
      else if (findOpen) setFindOpen(false);
    },
  });

  async function handleReplace(mutations: Replacement[]) {
    if (mutations.length === 0) return;
    const zhMuts = mutations.filter((m) => m.field === 'zh');
    for (const m of zhMuts) {
      try {
        await apiFetch(`/api/files/${fileId}/translations/${m.idx}`, {
          method: 'PATCH',
          body: JSON.stringify({ zh_text: m.newText }),
        });
      } catch {
        /* surface via toast in later task */
      }
    }
    refresh();
  }

  if (loading) {
    return (
      <div className="motitle-bold">
        <div className="bold">
          <BoldRail activeId="proof" />
          <div className="b-main">
            <div className="empty" style={{ margin: 'auto' }}>
              <div className="empty-icon">
                <Icon name="film" size={24} color="var(--text-dim)" />
              </div>
              <div className="empty-title">Loading…</div>
            </div>
          </div>
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="motitle-bold">
        <div className="bold">
          <BoldRail activeId="proof" />
          <div className="b-main">
            <div className="empty" style={{ margin: 'auto', color: 'var(--danger)' }}>
              <div className="empty-icon">
                <Icon name="alert" size={24} color="var(--danger)" />
              </div>
              <div className="empty-title">Error: {error}</div>
            </div>
          </div>
        </div>
      </div>
    );
  }
  if (!file) {
    return (
      <div className="motitle-bold">
        <div className="bold">
          <BoldRail activeId="proof" />
          <div className="b-main">
            <div className="empty" style={{ margin: 'auto' }}>
              <div className="empty-icon">
                <Icon name="film" size={24} color="var(--text-dim)" />
              </div>
              <div className="empty-title">File not found.</div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const fileForTopbar = file;
  const segmentCount = translations.length;
  const approvedCount = translations.filter((t) => t.status === 'approved').length;

  return (
    <div className="motitle-bold">
      <div className="bold">
        <BoldRail activeId="proof" />
        <div className="b-main">
          <TopBar
            file={fileForTopbar}
            onOpenOverrides={() => setOverridesOpen(true)}
            onOpenRender={() => setRenderOpen(true)}
            onSubtitleSourceChanged={refresh}
          />

          <div className="b-body b-body-proofread">
            {/* Left col — Segment Table + Find/Replace */}
            <div className="b-col">
              <div className="panel" style={{ flex: 1, minHeight: 0 }}>
                <div className="panel-head">
                  <div className="title">
                    <Icon name="edit" size={12} /> 字幕段 Segments
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--text-dim)',
                        fontWeight: 500,
                        letterSpacing: 0,
                        marginLeft: 4,
                      }}
                    >
                      · {approvedCount}/{segmentCount}
                    </span>
                  </div>
                  <div className="spacer" />
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => setFindOpen((b) => !b)}
                    aria-label="Toggle find and replace"
                    style={{
                      padding: '4px 10px',
                      fontSize: 11,
                      color: 'var(--text-mid)',
                      background: 'var(--surface-2)',
                      border: '1px solid var(--border)',
                      borderRadius: 6,
                    }}
                  >
                    <Icon name="search" size={11} /> 搜尋 ⌘F
                  </button>
                </div>
                <div
                  className="panel-body"
                  style={{ padding: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}
                >
                  {findOpen && (
                    <FindReplaceToolbar
                      fr={fr}
                      onReplace={handleReplace}
                      onClose={() => setFindOpen(false)}
                    />
                  )}
                  <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                    <SegmentTable
                      fileId={fileId}
                      file={file}
                      translations={translations}
                      onShowHistory={(idx) => setHistoryOpenIdx(idx)}
                      onOpenGlossaryApply={() => setGlossaryApplyOpen(true)}
                      onStageRerun={() => {
                        /* SocketProvider drives UI; refresh on completion */
                      }}
                      currentTime={currentTime}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Middle col — Video preview */}
            <div className="b-col">
              <div className="panel" style={{ minHeight: 0 }}>
                <div className="panel-head">
                  <div className="title">
                    <Icon name="video" size={12} /> 預覽 Preview
                  </div>
                  <div className="spacer" />
                </div>
                <div className="panel-body" style={{ padding: 12 }}>
                  <VideoPanel
                    file={file}
                    translations={translations}
                    font={font}
                    currentTime={currentTime}
                    onTimeUpdate={setCurrentTime}
                  />
                </div>
              </div>
            </div>

            {/* Right col — Inspector */}
            <div className="b-col inspector">
              <div className="panel">
                <div className="panel-head">
                  <div className="title">
                    <Icon name="cog" size={12} /> 字幕設定
                  </div>
                </div>
                <div className="panel-body" style={{ padding: 12 }}>
                  <SubtitleSettingsPanel
                    pipelineId={file?.pipeline_id ?? null}
                    font={font}
                    onSaved={refreshPipeline}
                  />
                </div>
              </div>

              <div className="panel">
                <div className="panel-head">
                  <div className="title">
                    <Icon name="book" size={12} /> 詞彙表
                  </div>
                </div>
                <div className="panel-body" style={{ padding: 12 }}>
                  <GlossaryPanel glossaryId={glossaryId} />
                </div>
              </div>

              <div className="panel">
                <div className="panel-head">
                  <div className="title">
                    <Icon name="flow" size={12} /> 階段歷史
                  </div>
                </div>
                <div className="panel-body" style={{ padding: 12, display: 'grid', gap: 6 }}>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => setHistoryOpenIdx(0)}
                    style={{
                      padding: '6px 10px',
                      fontSize: 11,
                      color: 'var(--text-mid)',
                      background: 'var(--surface-2)',
                      border: '1px solid var(--border)',
                      borderRadius: 6,
                      width: '100%',
                      textAlign: 'left',
                    }}
                  >
                    開啟 stage history sidebar
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => setGlossaryApplyOpen(true)}
                    style={{
                      padding: '6px 10px',
                      fontSize: 11,
                      color: 'var(--text-mid)',
                      background: 'var(--surface-2)',
                      border: '1px solid var(--border)',
                      borderRadius: 6,
                      width: '100%',
                      textAlign: 'left',
                    }}
                  >
                    套用詞彙表 →
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Drawers + modals (Esc cascade managed by useKeyboardShortcuts) */}
      <StageHistorySidebar
        open={historyOpenIdx !== null}
        file={file}
        segmentIdx={historyOpenIdx}
        onClose={() => setHistoryOpenIdx(null)}
        onSaved={refresh}
      />
      <PromptOverridesDrawer
        open={overridesOpen}
        file={file}
        onClose={() => setOverridesOpen(false)}
        onSaved={refresh}
      />
      <GlossaryApplyModal
        open={glossaryApplyOpen}
        fileId={fileId}
        onClose={() => setGlossaryApplyOpen(false)}
        onApplied={refresh}
      />
      <RenderModal
        open={renderOpen}
        onClose={() => setRenderOpen(false)}
        onConfirm={(options: RenderOptions) => {
          setRenderOpen(false);
          void startRender({ file_id: fileId, ...options });
        }}
      />

      {currentJob && currentJob.status !== 'completed' && currentJob.status !== 'cancelled' && (
        <div
          role="status"
          aria-label="Render progress"
          className="fixed bottom-4 right-4 w-80 bg-background border rounded-lg shadow-lg p-3 z-50 space-y-2"
        >
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">Rendering</span>
            <span className="text-xs text-muted-foreground">{currentJob.status}</span>
          </div>
          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full transition-all',
                currentJob.status === 'failed' ? 'bg-destructive' : 'bg-primary',
              )}
              style={{ width: `${currentJob.progress ?? 0}%` }}
            />
          </div>
          {currentJob.error && (
            <p className="text-xs text-destructive">{currentJob.error}</p>
          )}
          <div className="flex gap-2 justify-end">
            {currentJob.status !== 'failed' && (
              <Button size="sm" variant="ghost" onClick={() => cancelRender()}>
                Cancel
              </Button>
            )}
            {currentJob.status === 'failed' && (
              <Button size="sm" variant="outline" onClick={() => clearRender()}>
                Dismiss
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
