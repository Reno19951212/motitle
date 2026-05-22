export type VideoPanelProps = {
  fileId?: string | null;
  fileName?: string;
  currentSubtitle?: string;
  currentTimecode?: string;
};

export function VideoPanel({ fileId, fileName, currentSubtitle, currentTimecode }: VideoPanelProps) {
  return (
    <div className="con-video" data-testid="video-panel">
      {fileId ? (
        <video
          key={fileId}
          className="con-video-element"
          src={`/api/files/${fileId}/media`}
          controls
          preload="metadata"
          data-testid="video-element"
        />
      ) : (
        <div className="safe-grid" />
      )}
      <span className="preview-label">PVW · {fileName ?? '(未揀檔)'}</span>
      <span className="tc">{currentTimecode ?? '00:00:00:00'}</span>
      {currentSubtitle && (
        <div className="live-cap"><div>{currentSubtitle}</div></div>
      )}
    </div>
  );
}
