import { useEffect, useState } from 'react';
import { Icon } from '../../lib/motitle-icons';
import { useVideoControl } from './video-control-context';
import { formatDuration } from '../../lib/format';

export type TransportBarProps = Record<string, never>;

function VUMeter() {
  const [heights, setHeights] = useState<number[]>([6, 9, 12, 8, 11, 7]);
  useEffect(() => {
    const t = setInterval(() => {
      setHeights(Array.from({ length: 6 }, () => 6 + Math.floor(Math.random() * 8)));
    }, 200);
    return () => clearInterval(t);
  }, []);
  return (
    <span className="r-vu live" data-testid="vu-meter">
      {heights.map((h, i) => <b key={i} style={{ height: h + 'px' }} />)}
    </span>
  );
}

export function TransportBar(_props: TransportBarProps) {
  const { playing, currentTime, duration, toggle, seekPercent } = useVideoControl();

  const totalTime = isFinite(duration) ? formatDuration(duration) : '—';
  const currentDisplay = formatDuration(currentTime);
  const scrubPercent = isFinite(duration) && duration > 0
    ? Math.max(0, Math.min(100, (currentTime / duration) * 100))
    : 0;

  return (
    <div className="con-transport" data-testid="transport-bar">
      <button
        className="pp"
        onClick={() => toggle()}
        data-testid="transport-toggle"
      >
        <Icon name={playing ? 'pause' : 'play'} size={11} color="var(--bg)" />
      </button>
      <span className="tc">
        {currentDisplay}
        <span className="total"> / {totalTime}</span>
      </span>
      <div
        className="scrub"
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const pct = (e.clientX - rect.left) / rect.width;
          seekPercent(pct);
        }}
        data-testid="transport-scrub"
      >
        <i style={{ width: `${scrubPercent}%` }} />
        <b style={{ left: `${scrubPercent}%` }} />
      </div>
      <span className="vol-toggle">−24 dB</span>
      <VUMeter />
      <button className="btn-icon">
        <Icon name="cog" size={13} />
      </button>
    </div>
  );
}
