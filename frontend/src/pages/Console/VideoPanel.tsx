import { useEffect, useRef } from 'react';
import { useVideoControl } from './video-control-context';
import { SubtitleOverlay } from '../Proofread/SubtitleOverlay';
import type { FontConfig } from '../../lib/schemas/pipeline';

export type VideoPanelProps = {
  fileId?: string | null;
  fileName?: string;
  /** Pre-picked subtitle text for the current playhead; empty string hides
   *  the overlay (SubtitleOverlay returns null on empty text). */
  overlayText?: string;
  /** Pipeline font config for broadcast-grade SVG rendering. Null while
   *  the pipeline is still loading or the file has no pipeline_id. */
  font?: FontConfig | null;
  /** Pre-formatted HH:MM:SS:FF; passed in (instead of derived) so the
   *  parent decides fps + sentinel behaviour. */
  currentTimecode?: string;
};

export function VideoPanel({ fileId, fileName, overlayText, font, currentTimecode }: VideoPanelProps) {
  const ref = useRef<HTMLVideoElement | null>(null);
  const { setVideoEl } = useVideoControl();

  // Register/unregister the <video> element with the context on mount/unmount.
  // Re-runs when fileId changes because <video key={fileId}> forces remount.
  useEffect(() => {
    setVideoEl(ref.current);
    return () => { setVideoEl(null); };
  }, [setVideoEl, fileId]);

  return (
    <div className="con-video" data-testid="video-panel">
      {fileId ? (
        <>
          <video
            key={fileId}
            ref={ref}
            className="con-video-element"
            src={`/api/files/${fileId}/media`}
            controls
            preload="metadata"
            data-testid="video-element"
          />
          {/* SubtitleOverlay positions itself absolute+inset:0 inside .con-video.
              It renders nothing when text is empty or font is null, so we can
              mount unconditionally without an extra wrapper guard. */}
          <SubtitleOverlay text={overlayText ?? ''} font={font ?? null} />
        </>
      ) : (
        <div className="safe-grid" />
      )}
      <span className="preview-label">PVW · {fileName ?? '(未揀檔)'}</span>
      <span className="tc">{currentTimecode ?? '00:00:00:00'}</span>
    </div>
  );
}
