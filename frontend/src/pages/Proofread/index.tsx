// src/pages/Proofread/index.tsx
import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useSocket } from '@/providers/SocketProvider';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
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
import { useActiveProfile } from './hooks/useActiveProfile';
import { useFindReplace } from './hooks/useFindReplace';
import type { Replacement } from './hooks/useFindReplace';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { useRenderJob } from './hooks/useRenderJob';
import type { RenderOptions } from '@/lib/schemas/render-options';

export default function Proofread() {
  const { fileId } = useParams<{ fileId: string }>();
  if (!fileId) return <p className="p-4 text-destructive">No file ID in route.</p>;
  return <ProofreadInner fileId={fileId} />;
}

function ProofreadInner({ fileId }: { fileId: string }) {
  const { file, translations, loading, error, refresh } = useFileData(fileId);
  const { profile, refresh: refreshProfile } = useActiveProfile();
  const fr = useFindReplace(translations);
  const { state: socketState } = useSocket();

  const [findOpen, setFindOpen] = useState(false);
  const [overridesOpen, setOverridesOpen] = useState(false);
  const [renderOpen, setRenderOpen] = useState(false);
  const [historyOpenIdx, setHistoryOpenIdx] = useState<number | null>(null);
  const [glossaryApplyOpen, setGlossaryApplyOpen] = useState(false);

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
      } catch { /* surface via toast in later task */ }
    }
    refresh();
  }

  if (loading) return <div className="p-8 text-muted-foreground">Loading…</div>;
  if (error) return <div className="p-8 text-destructive">Error: {error}</div>;
  if (!file) return <div className="p-8 text-muted-foreground">File not found.</div>;

  return (
    <div className="grid grid-rows-[auto_1fr] h-full">
      <TopBar
        file={file}
        onOpenOverrides={() => setOverridesOpen(true)}
        onOpenRender={() => setRenderOpen(true)}
        onSubtitleSourceChanged={refresh}
      />
      <div className="grid grid-cols-2 overflow-hidden">
        <div className="border-r overflow-auto p-3 space-y-3">
          <VideoPanel file={file} translations={translations} profile={profile} />
          <GlossaryPanel profile={profile} />
          <SubtitleSettingsPanel profile={profile} onSaved={refreshProfile} />
        </div>
        <div className="flex flex-col overflow-hidden">
          {findOpen && <FindReplaceToolbar fr={fr} onReplace={handleReplace} onClose={() => setFindOpen(false)} />}
          <div className="flex-1 overflow-hidden">
            <SegmentTable
              fileId={fileId}
              file={file}
              translations={translations}
              onShowHistory={(idx) => setHistoryOpenIdx(idx)}
              onOpenGlossaryApply={() => setGlossaryApplyOpen(true)}
              onStageRerun={() => { /* SocketProvider drives UI; refresh on completion via myStatus effect */ }}
            />
          </div>
        </div>
      </div>

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
          {currentJob.error && <p className="text-xs text-destructive">{currentJob.error}</p>}
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
