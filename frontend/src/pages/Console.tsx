import { useEffect, useState } from 'react';
import '../styles/motitle-bold.css';
import '../styles/console.css';
import { Rail } from './Console/Rail';
import { QueueColumn } from './Console/QueueColumn';
import { Workbench } from './Console/Workbench';
import { AsideColumn } from './Console/AsideColumn';
import { GlobalSearchModal } from './Console/GlobalSearchModal';
import { useHotkeys } from '../hooks/useHotkeys';
import { useSocket } from '../providers/SocketProvider';
import { usePipelinePickerStore } from '../stores/pipeline-picker';

export type ConsoleProps = Record<string, never>;

export function Console(_props: ConsoleProps) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const { state } = useSocket();
  const selectedFile = selectedFileId ? (state.files[selectedFileId] ?? null) : null;

  // Hydrate pipelines on mount — picker store starts with empty pipelines
  // (only pipelineId persists to localStorage). Old Dashboard does this
  // already; Console forgot to, so preset pills showed "未設定" for all
  // slots even when user had pipelines with preset_slot set.
  const pipelines = usePipelinePickerStore(s => s.pipelines);
  const pipelineId = usePipelinePickerStore(s => s.pipelineId);
  const refreshPipelines = usePipelinePickerStore(s => s.refresh);
  const setPipelineId = usePipelinePickerStore(s => s.setPipelineId);
  useEffect(() => { void refreshPipelines(); }, [refreshPipelines]);

  // Auto-select preset_slot=1 pipeline on first render when no active
  // pipelineId — gives a sensible default so drop-zone upload works
  // without forcing user to hit ⌘1 first.
  useEffect(() => {
    if (pipelineId) return;
    const slot1 = pipelines.find(p => p.preset_slot === 1);
    if (slot1) setPipelineId(slot1.id);
  }, [pipelines, pipelineId, setPipelineId]);

  useHotkeys({
    'mod+k': (e: KeyboardEvent) => { e.preventDefault(); setSearchOpen(true); },
    'mod+u': (e: KeyboardEvent) => {
      e.preventDefault();
      document.querySelector<HTMLInputElement>('[data-testid="console-drop"] input')?.click();
    },
    'esc': () => { if (searchOpen) setSearchOpen(false); },
  });

  return (
    <div className="motitle-bold console" data-testid="console-root">
      <div data-testid="console-rail"><Rail /></div>
      <div data-testid="console-queue">
        <QueueColumn selectedId={selectedFileId} onSelect={setSelectedFileId} />
      </div>
      <div data-testid="console-workbench">
        <Workbench selectedFile={selectedFile} />
      </div>
      <div data-testid="console-aside">
        <AsideColumn selectedFile={selectedFile} />
      </div>
      {searchOpen && <GlobalSearchModal onClose={() => setSearchOpen(false)} />}
    </div>
  );
}
