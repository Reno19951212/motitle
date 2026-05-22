// frontend/src/lib/format.ts

export function formatDuration(seconds: number | null): string {
  if (seconds === null || !isFinite(seconds)) return '—';
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => n.toString().padStart(2, '0');
  if (h > 0) return `${h}:${pad(m)}:${pad(sec)}`;
  return `${pad(m)}:${pad(sec)}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

export function formatRelativeTime(epochSeconds: number, nowSeconds?: number): string {
  const now = nowSeconds ?? Math.floor(Date.now() / 1000);
  const delta = now - epochSeconds;
  if (delta < 60) return '剛剛';
  if (delta < 3600) return `${Math.floor(delta / 60)} 分鐘前`;
  if (delta < 86400) return `${Math.floor(delta / 3600)} 小時前`;
  return `${Math.floor(delta / 86400)} 日前`;
}
