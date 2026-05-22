export type VideoPanelProps = {
  fileName?: string;
  currentSubtitle?: string;
  currentTimecode?: string;
};

export function VideoPanel({ fileName, currentSubtitle, currentTimecode }: VideoPanelProps) {
  return (
    <div className="con-video" data-testid="video-panel">
      <div className="safe-grid" />
      <span className="preview-label">PVW · {fileName ?? '(未揀檔)'}</span>
      <span className="tc">{currentTimecode ?? '00:00:00:00'}</span>
      {currentSubtitle && (
        <div className="live-cap"><div>{currentSubtitle}</div></div>
      )}
    </div>
  );
}
