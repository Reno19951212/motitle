import { useState } from 'react';
import '../styles/motitle-bold.css';
import '../styles/console.css';
import { Rail } from './Console/Rail';
import { QueueColumn } from './Console/QueueColumn';
import { Workbench } from './Console/Workbench';
import { AsideColumn } from './Console/AsideColumn';
import { GlobalSearchModal } from './Console/GlobalSearchModal';
import { useHotkeys } from '../hooks/useHotkeys';
import { useSocket } from '../providers/SocketProvider';

export type ConsoleProps = Record<string, never>;

export function Console(_props: ConsoleProps) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const { state } = useSocket();
  const selectedFile = selectedFileId ? (state.files[selectedFileId] ?? null) : null;

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
        <Workbench selectedFileId={selectedFileId} />
      </div>
      <div data-testid="console-aside">
        <AsideColumn selectedFile={selectedFile} />
      </div>
      {searchOpen && <GlobalSearchModal onClose={() => setSearchOpen(false)} />}
    </div>
  );
}
