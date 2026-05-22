import { useEffect, useState } from 'react';
import { Icon } from '../../lib/motitle-icons';

export type TransportBarProps = {
  playing?: boolean;
  onTogglePlay?: () => void;
  currentTime?: string;
  totalTime?: string;
  scrubPercent?: number;
};

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

export function TransportBar({
  playing = false,
  onTogglePlay,
  currentTime = '00:00',
  totalTime = '00:00',
  scrubPercent = 0,
}: TransportBarProps) {
  return (
    <div className="con-transport" data-testid="transport-bar">
      <button className="pp" onClick={onTogglePlay} data-testid="transport-toggle">
        <Icon name={playing ? 'pause' : 'play'} size={11} color="var(--bg)" />
      </button>
      <span className="tc">{currentTime}<span className="total"> / {totalTime}</span></span>
      <div className="scrub">
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
