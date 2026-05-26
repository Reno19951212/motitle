import { useMemo } from 'react';
import { PresetPills } from './PresetPills';
import { MetricsBar } from './MetricsBar';
import { VideoPanel } from './VideoPanel';
import { TransportBar } from './TransportBar';
import { TranscriptList } from './TranscriptList';
import { Icon } from '../../lib/motitle-icons';
import { useHotkeys } from '../../hooks/useHotkeys';
import { VideoControlProvider, useVideoControl } from './video-control-context';
import { useFileTranslations, findActiveTranslation } from './hooks/useFileTranslations';
import { useFilePipeline } from '../Proofread/hooks/useFilePipeline';
import { pickSubtitleText } from '../Proofread/SubtitleOverlay';
import { formatTimecode } from './format-timecode';
import type { FileRecord } from '../../lib/socket-events';

export type WorkbenchProps = {
  selectedFile?: FileRecord | null;
};

// Inner component — uses the context so MUST live inside the provider.
function WorkbenchInner({ selectedFile }: WorkbenchProps) {
  const { toggle, currentTime } = useVideoControl();

  useHotkeys({
    space: (e) => { e.preventDefault(); toggle(); },
  });

  const fileName =
    typeof selectedFile?.original_name === 'string'
      ? selectedFile.original_name
      : undefined;
  const fileId = selectedFile?.id ?? null;
  const pipelineId =
    typeof selectedFile?.pipeline_id === 'string' ? selectedFile.pipeline_id : null;

  // Translations + pipeline font_config drive the broadcast-grade SVG overlay.
  // Both hooks tolerate null id and return safe defaults so VideoPanel can
  // render even before data lands.
  const { translations } = useFileTranslations(fileId);
  const { font } = useFilePipeline(pipelineId);

  // Per-file subtitle source override > pipeline font_config > sensible default.
  // Same precedence ladder as Proofread; falls back to 'bilingual' when neither
  // file nor pipeline specifies a source (matches Proofread VideoPanel logic).
  // FileRecord has an [key: string]: unknown index signature for forward-compat
  // fields like subtitle_source / bilingual_order that backend writes via
  // PATCH /api/files/<id> but aren't in the strict type. Probe + narrow.
  const fileExt = selectedFile as unknown as Record<string, unknown> | null;
  const rawSubSrc = fileExt?.subtitle_source;
  const fileSubtitleSource: 'auto' | 'source' | 'target' | 'bilingual' | undefined =
    rawSubSrc === 'auto' || rawSubSrc === 'source' || rawSubSrc === 'target' || rawSubSrc === 'bilingual'
      ? rawSubSrc
      : undefined;
  const rawOrder = fileExt?.bilingual_order;
  const fileBilingualOrder: 'source_top' | 'target_top' | undefined =
    rawOrder === 'source_top' || rawOrder === 'target_top' ? rawOrder : undefined;
  const sourceMode = fileSubtitleSource ?? font?.subtitle_source ?? 'auto';
  const mode: 'source' | 'target' | 'bilingual' =
    !sourceMode || sourceMode === 'auto' ? 'bilingual' : sourceMode;
  const order: 'source_top' | 'target_top' =
    fileBilingualOrder ?? font?.bilingual_order ?? 'source_top';

  const overlayText = useMemo(() => {
    const active = findActiveTranslation(translations, currentTime);
    if (!active) return '';
    // pickSubtitleText needs en_text/zh_text + start/end shape, which our
    // ConsoleTranslation already satisfies (it's a structural subset).
    return pickSubtitleText(
      { ...active, idx: 0, status: 'pending', flags: [] },
      mode,
      order,
    );
  }, [translations, currentTime, mode, order]);

  const currentTimecode = useMemo(() => formatTimecode(currentTime), [currentTime]);

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
        <VideoPanel
          fileId={fileId}
          fileName={fileName}
          overlayText={overlayText}
          font={font}
          currentTimecode={currentTimecode}
        />
        <TransportBar />
        <div className="con-bottom">
          <TranscriptList fileId={fileId} activeLang="zh" />
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
