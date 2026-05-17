// src/pages/Proofread/index.tsx
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useSocket } from '@/providers/SocketProvider';
import { apiFetch } from '@/lib/api';
import { TopBar } from './TopBar';
import { VideoPanel } from './VideoPanel';
import { SegmentTable } from './SegmentTable';
import { FindReplaceToolbar } from './FindReplaceToolbar';
import { StageHistorySidebar } from './StageHistorySidebar';
import { PromptOverridesDrawer } from './PromptOverridesDrawer';
import { GlossaryApplyModal } from './GlossaryApplyModal';
import { GlossaryPanel } from './GlossaryPanel';
import { SubtitleSettingsPanel } from './SubtitleSettingsPanel';
import { useFileData } from './hooks/useFileData';
import { useActiveProfile } from './hooks/useActiveProfile';
import { useFindReplace } from './hooks/useFindReplace';
import type { Replacement } from './hooks/useFindReplace';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';

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
  const [renderOpen, setRenderOpen] = useState(false); // T14 wires modal
  const [historyOpenIdx, setHistoryOpenIdx] = useState<number | null>(null);
  const [glossaryApplyOpen, setGlossaryApplyOpen] = useState(false);

  void renderOpen;

  // Refresh when stage runs complete for this file
  const myStatus = socketState.files[fileId]?.status;
  useEffect(() => {
    if (myStatus === 'completed') refresh();
  }, [myStatus, refresh]);

  useKeyboardShortcuts({
    onFindOpen: () => setFindOpen(true),
    onEscape: () => {
      if (glossaryApplyOpen) setGlossaryApplyOpen(false);
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
    </div>
  );
}
