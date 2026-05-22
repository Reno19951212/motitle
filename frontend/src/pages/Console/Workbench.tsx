import { useState } from 'react';
import { PresetPills } from './PresetPills';
import { MetricsBar } from './MetricsBar';
import { VideoPanel } from './VideoPanel';
import { TransportBar } from './TransportBar';
import { TranscriptList } from './TranscriptList';
import { Icon } from '../../lib/motitle-icons';
import { useHotkeys } from '../../hooks/useHotkeys';

export type WorkbenchProps = {
  selectedFileId?: string | null;
};

export function Workbench({ selectedFileId = null }: WorkbenchProps) {
  const [playing, setPlaying] = useState(false);

  useHotkeys({
    space: (e: KeyboardEvent) => { e.preventDefault(); setPlaying(p => !p); },
  });

  return (
    <section className="con-work">
      <div className="con-topbar">
        <PresetPills />
        <div className="con-actions">
          <button className="btn btn-secondary btn-sm">
            <Icon name="cog" size={11} /> 設定
          </button>
          <button className="btn btn-primary btn-sm">
            <Icon name="play" size={11} color="#fff" /> 執行佇列
          </button>
        </div>
      </div>
      <MetricsBar />
      <div className="con-stage">
        <VideoPanel fileName={selectedFileId ?? undefined} />
        <TransportBar
          playing={playing}
          onTogglePlay={() => setPlaying(p => !p)}
        />
        <div className="con-bottom">
          <TranscriptList fileId={selectedFileId} activeLang="zh" />
        </div>
      </div>
    </section>
  );
}
