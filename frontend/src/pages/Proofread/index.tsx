// src/pages/Proofread/index.tsx
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useSocket } from '@/providers/SocketProvider';
import { apiFetch } from '@/lib/api';
import { TopBar } from './TopBar';
import { VideoPanel } from './VideoPanel';
import { SegmentTable } from './SegmentTable';
import { FindReplaceToolbar } from './FindReplaceToolbar';
import { useFileData } from './hooks/useFileData';
import { useActiveProfile } from './hooks/useActiveProfile';
import { useFindReplace } from './hooks/useFindReplace';
import type { Replacement } from './hooks/useFindReplace';

export default function Proofread() {
  const { fileId } = useParams<{ fileId: string }>();
  const [overridesOpen, setOverridesOpen] = useState(false);
  const [renderOpen, setRenderOpen] = useState(false);
  const [findOpen, setFindOpen] = useState(false);

  // setOverridesOpen / setRenderOpen consumed in T10 / T13. Wire stub callbacks for now.
  void overridesOpen;
  void renderOpen;

  if (!fileId) return <p className="p-4 text-destructive">No file ID in route.</p>;

  return <ProofreadInner fileId={fileId} findOpen={findOpen} setFindOpen={setFindOpen} setOverridesOpen={setOverridesOpen} setRenderOpen={setRenderOpen} />;
}

interface InnerProps {
  fileId: string;
  findOpen: boolean;
  setFindOpen: (b: boolean) => void;
  setOverridesOpen: (b: boolean) => void;
  setRenderOpen: (b: boolean) => void;
}

function ProofreadInner({ fileId, findOpen, setFindOpen, setOverridesOpen, setRenderOpen }: InnerProps) {
  const { file, translations, loading, error, refresh } = useFileData(fileId);
  const { profile } = useActiveProfile();
  const fr = useFindReplace(translations);
  const { state: socketState } = useSocket();

  // When a stage run completes for this file (status transitions to 'completed'), refresh.
  const myStatus = socketState.files[fileId]?.status;
  useEffect(() => {
    if (myStatus === 'completed') refresh();
  }, [myStatus, refresh]);

  async function handleReplace(mutations: Replacement[]) {
    if (mutations.length === 0) return;
    // Only target zh edits via the translations API; en mutations are no-op for now.
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

  if (loading) return <div className="p-8 text-muted-foreground">Loading…</div>;
  if (error) return <div className="p-8 text-destructive">Error: {error}</div>;
  if (!file) return <div className="p-8 text-muted-foreground">File not found.</div>;

  return (
    <div className="grid grid-rows-[auto_1fr] h-full">
      <TopBar file={file} onOpenOverrides={() => setOverridesOpen(true)} onOpenRender={() => setRenderOpen(true)} />
      <div className="grid grid-cols-2 overflow-hidden">
        <div className="border-r overflow-auto">
          <VideoPanel file={file} translations={translations} profile={profile} />
        </div>
        <div className="flex flex-col overflow-hidden">
          {findOpen && <FindReplaceToolbar fr={fr} onReplace={handleReplace} onClose={() => setFindOpen(false)} />}
          <div className="flex-1 overflow-hidden">
            <SegmentTable
              fileId={fileId}
              translations={translations}
              onShowHistory={(idx) => {
                // T8 wires StageHistorySidebar here
                void idx;
              }}
            />
          </div>
        </div>
      </div>
      {/* T17 will add a ⌘F handler to flip setFindOpen(true) */}
      {/* Temporary keyboard handler for development — replace in T17 */}
      <input
        type="hidden"
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'f') {
            e.preventDefault();
            setFindOpen(true);
          }
        }}
      />
    </div>
  );
}
