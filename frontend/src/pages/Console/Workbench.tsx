import { useState } from 'react';
import { PresetPills } from './PresetPills';
import { MetricsBar } from './MetricsBar';
import { VideoPanel } from './VideoPanel';
import { TransportBar } from './TransportBar';
import { TranscriptList } from './TranscriptList';
import { Icon } from '../../lib/motitle-icons';
import { useHotkeys } from '../../hooks/useHotkeys';
import { formatDuration } from '../../lib/format';
import type { FileRecord } from '../../lib/socket-events';

export type WorkbenchProps = {
  selectedFile?: FileRecord | null;
};

export function Workbench({ selectedFile = null }: WorkbenchProps) {
  const [playing, setPlaying] = useState(false);

  useHotkeys({
    space: (e: KeyboardEvent) => { e.preventDefault(); setPlaying(p => !p); },
  });

  const fileName =
    typeof selectedFile?.original_name === 'string'
      ? selectedFile.original_name
      : undefined;
  const durationSeconds =
    typeof selectedFile?.duration_seconds === 'number'
      ? selectedFile.duration_seconds
      : null;
  const totalTime = formatDuration(durationSeconds);

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
        <VideoPanel fileName={fileName} />
        <TransportBar
          playing={playing}
          onTogglePlay={() => setPlaying(p => !p)}
          totalTime={totalTime}
        />
        <div className="con-bottom">
          <TranscriptList fileId={selectedFile?.id ?? null} activeLang="zh" />
        </div>
      </div>
    </section>
  );
}
