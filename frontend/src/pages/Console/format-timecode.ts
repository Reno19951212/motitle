// HH:MM:SS:FF (25 fps default) — broadcast-style frame-accurate timecode
// for the corner chip on VideoPanel. Frame count is rounded, not truncated,
// because operators visually align to whole frames.
export function formatTimecode(seconds: number, fps = 25): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00:00:00';
  const totalFrames = Math.round(seconds * fps);
  const f = totalFrames % fps;
  const totalSecs = Math.floor(totalFrames / fps);
  const s = totalSecs % 60;
  const m = Math.floor(totalSecs / 60) % 60;
  const h = Math.floor(totalSecs / 3600);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(h)}:${pad(m)}:${pad(s)}:${pad(f)}`;
}
