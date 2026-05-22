import { PresetPills } from './PresetPills';
import { MetricsBar } from './MetricsBar';
import { VideoPanel } from './VideoPanel';
import { TransportBar } from './TransportBar';
import { TranscriptList } from './TranscriptList';
import { Icon } from '../../lib/motitle-icons';
import { useHotkeys } from '../../hooks/useHotkeys';
import { VideoControlProvider, useVideoControl } from './video-control-context';
import type { FileRecord } from '../../lib/socket-events';

export type WorkbenchProps = {
  selectedFile?: FileRecord | null;
};

// Inner component — uses the context so MUST live inside the provider.
function WorkbenchInner({ selectedFile }: WorkbenchProps) {
  const { toggle } = useVideoControl();

  useHotkeys({
    space: (e) => { e.preventDefault(); toggle(); },
  });

  const fileName =
    typeof selectedFile?.original_name === 'string'
      ? selectedFile.original_name
      : undefined;

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
        <VideoPanel fileId={selectedFile?.id ?? null} fileName={fileName} />
        <TransportBar />
        <div className="con-bottom">
          <TranscriptList fileId={selectedFile?.id ?? null} activeLang="zh" />
        </div>
      </div>
    </section>
  );
}

export function Workbench({ selectedFile = null }: WorkbenchProps) {
  return (
    <VideoControlProvider>
      <WorkbenchInner selectedFile={selectedFile ?? null} />
    </VideoControlProvider>
  );
}
