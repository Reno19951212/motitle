import { useCallback, useMemo } from 'react';
import { usePipelinePickerStore, type PipelineSummary } from '../../stores/pipeline-picker';
import { useHotkeys } from '../../hooks/useHotkeys';

type Slot = 1 | 2 | 3 | 4;
const SLOTS: ReadonlyArray<Slot> = [1, 2, 3, 4];

export type PresetPillsProps = Record<string, never>;

export function PresetPills(_props: PresetPillsProps) {
  const pipelines = usePipelinePickerStore(s => s.pipelines);
  const pipelineId = usePipelinePickerStore(s => s.pipelineId);
  const setPipelineId = usePipelinePickerStore(s => s.setPipelineId);

  const slotPipelines = useMemo(() => {
    const map: Record<Slot, PipelineSummary | undefined> = {
      1: undefined, 2: undefined, 3: undefined, 4: undefined,
    };
    for (const p of pipelines) {
      if (p.preset_slot && p.preset_slot >= 1 && p.preset_slot <= 4) {
        map[p.preset_slot as Slot] = p;
      }
    }
    return map;
  }, [pipelines]);

  const selectSlot = useCallback((slot: Slot) => {
    const p = slotPipelines[slot];
    if (p) setPipelineId(p.id);
  }, [slotPipelines, setPipelineId]);

  useHotkeys(
    useMemo(() => ({
      'mod+1': (e: KeyboardEvent) => { e.preventDefault(); selectSlot(1); },
      'mod+2': (e: KeyboardEvent) => { e.preventDefault(); selectSlot(2); },
      'mod+3': (e: KeyboardEvent) => { e.preventDefault(); selectSlot(3); },
      'mod+4': (e: KeyboardEvent) => { e.preventDefault(); selectSlot(4); },
    }), [selectSlot]),
  );

  return (
    <div className="con-presets">
      <span className="lbl">Preset</span>
      {SLOTS.map(slot => {
        const p = slotPipelines[slot];
        const active = p && p.id === pipelineId;
        return (
          <button
            key={slot}
            className={active ? 'on' : ''}
            data-testid={`preset-pill-${slot}`}
            data-active={active ? 'true' : 'false'}
            onClick={() => selectSlot(slot)}
            disabled={!p}
          >
            <span className="k">⌘{slot}</span>
            <span>{p ? p.name : '未設定'}</span>
          </button>
        );
      })}
    </div>
  );
}
