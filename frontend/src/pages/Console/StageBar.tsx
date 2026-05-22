import type { ConsoleStageCells } from './types';
import type { CSSProperties } from 'react';

export type StageBarProps = {
  cells: ConsoleStageCells;
};

export function StageBar({ cells }: StageBarProps) {
  return (
    <div className="con-q-stages" data-testid="queue-stage-bar">
      {cells.map((c, i) => (
        <i
          key={i}
          className={c.state}
          style={c.percent != null ? ({ ['--p' as string]: c.percent + '%' } as CSSProperties) : undefined}
        />
      ))}
    </div>
  );
}
