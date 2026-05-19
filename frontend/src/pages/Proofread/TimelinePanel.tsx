// src/pages/Proofread/TimelinePanel.tsx
// Bottom waveform + region overlay for the Bold Proofread page. Renders ~480
// vertical bars plus one region rect per segment (color-coded approved /
// flagged / current). Clicking outside a region seeks the video; clicking a
// region selects that segment AND seeks.
import { useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import type { Translation } from './types';

interface WaveformResp {
  peaks: number[];
  duration: number;
}

interface Props {
  fileId: string;
  translations: Translation[];
  cursorIdx: number | null;
  currentTime: number;
  /** Total media duration in seconds. */
  duration: number;
  onSeek: (seconds: number) => void;
  onSelect: (idx: number) => void;
  onPrev: () => void;
  onNext: () => void;
}

const WF_BINS = 480;

function fmtTs(seconds: number | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—:—';
  const m = Math.floor(seconds / 60);
  const s = (seconds - m * 60).toFixed(2).padStart(5, '0');
  return `${String(m).padStart(2, '0')}:${s}`;
}

function fmtTick(seconds: number): string {
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total - m * 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function TimelinePanel({
  fileId,
  translations,
  cursorIdx,
  currentTime,
  duration,
  onSeek,
  onSelect,
  onPrev,
  onNext,
}: Props) {
  const [peaks, setPeaks] = useState<number[] | null>(null);
  const waveRef = useRef<HTMLDivElement | null>(null);

  // Load waveform once per file. Backend probe failure → fallback to a
  // synthetic neutral pattern (rendered below).
  useEffect(() => {
    let cancelled = false;
    apiFetch<WaveformResp>(`/api/files/${fileId}/waveform?bins=${WF_BINS}`)
      .then((r) => {
        if (!cancelled) setPeaks(r.peaks ?? []);
      })
      .catch(() => {
        if (!cancelled) setPeaks(null);
      });
    return () => {
      cancelled = true;
    };
  }, [fileId]);

  const bars = useMemo(() => {
    if (peaks && peaks.length > 0) {
      return peaks.map((p) => Math.max(4, Math.round(p * 100)));
    }
    // Synthetic fallback so the panel always renders something.
    return Array.from({ length: WF_BINS }).map((_, i) => 20 + Math.abs(Math.sin(i * 0.31)) * 40);
  }, [peaks]);

  const playedRatio = duration > 0 ? Math.min(1, currentTime / duration) : 0;
  const playedN = Math.floor(playedRatio * bars.length);

  const handleWaveClick = (e: React.MouseEvent<HTMLDivElement>) => {
    // Region clicks are caught by region onClick first; this fires for empty
    // space between regions.
    const target = e.target as HTMLElement;
    if (target.closest('.rv-wave-region')) return;
    const el = waveRef.current;
    if (!el || !duration) return;
    const rect = el.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    onSeek(duration * ratio);
  };

  const ticks = useMemo(() => {
    if (!duration || duration < 0.1) return [];
    const n = 6;
    return Array.from({ length: n }).map((_, i) => ({
      pct: (i / (n - 1)) * 100,
      label: fmtTick((i / (n - 1)) * duration),
    }));
  }, [duration]);

  const current = cursorIdx != null ? translations[cursorIdx] : null;

  return (
    <div className="rv-b-timeline-panel" data-testid="timeline-panel">
      <div className="rv-b-timeline-head">
        <div className="rv-b-tlh-l">
          <span className="k">時間軸</span>
          <span className="dot">·</span>
          <span>撳條波形跳至該位置</span>
        </div>
        <div className="rv-b-tlh-r" />
      </div>
      <div
        className="rv-wave"
        ref={waveRef}
        style={{ height: 96 }}
        onClick={handleWaveClick}
        data-testid="waveform"
      >
        <div className="rv-wave-bars">
          {bars.map((h, i) => (
            <div
              key={i}
              className={`rv-wave-bar${i < playedN ? ' played' : ''}`}
              style={{ height: `${h}%` }}
            />
          ))}
        </div>
        <div className="rv-wave-regions">
          {duration > 0 &&
            translations.map((t, i) => {
              if (t.start == null || t.end == null) return null;
              const left = (t.start / duration) * 100;
              const width = ((t.end - t.start) / duration) * 100;
              const cur = i === cursorIdx;
              const ap = t.status === 'approved';
              const fl = t.flags.length > 0;
              return (
                <div
                  key={t.idx}
                  className={`rv-wave-region${cur ? ' cur' : ''}${ap ? ' approved' : ''}${
                    fl ? ' flagged' : ''
                  }`}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect(i);
                    if (t.start != null) onSeek(t.start);
                  }}
                  title={`#${t.idx + 1} · ${fmtTs(t.start)}`}
                  data-idx={i}
                >
                  <span className="rv-wave-region-label">{t.idx + 1}</span>
                </div>
              );
            })}
        </div>
        {duration > 0 && (
          <div className="rv-wave-playhead" style={{ left: `${playedRatio * 100}%` }}>
            <div className="rv-wave-playhead-dot" />
          </div>
        )}
        <div className="rv-wave-ticks">
          {ticks.map((t, i) => (
            <div key={i} className="rv-wave-tick" style={{ left: `${t.pct}%` }}>
              {t.label}
            </div>
          ))}
        </div>
      </div>
      <div className="rv-b-wave-ctrl">
        <div className="rv-b-wave-ctrl-l">
          <span>當前：段 #{current ? current.idx + 1 : '—'}</span>
          <span className="dot">·</span>
          <span className="mono">In {fmtTs(current?.start)}</span>
          <span className="dot">·</span>
          <span className="mono">Out {fmtTs(current?.end)}</span>
          <span className="dot">·</span>
          <span>
            {current && current.start != null && current.end != null
              ? (current.end - current.start).toFixed(2)
              : '—'}
            s
          </span>
        </div>
        <div className="rv-b-wave-ctrl-r">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onPrev}
            title="上一段 (J)"
            aria-label="Previous segment"
          >
            ◀
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onNext}
            title="下一段 (K)"
            aria-label="Next segment"
          >
            ▶
          </button>
        </div>
      </div>
    </div>
  );
}
