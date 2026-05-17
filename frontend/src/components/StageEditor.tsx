import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core';
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

export interface MtRefOption {
  id: string;
  name: string;
}

function SortableRow({
  id,
  refId,
  onRefChange,
  onRemove,
  options,
}: {
  id: string;
  refId: string;
  onRefChange: (newRef: string) => void;
  onRemove: () => void;
  options: MtRefOption[];
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id });
  const style = { transform: CSS.Transform.toString(transform), transition };
  return (
    <div
      ref={setNodeRef}
      style={style}
      className="grid grid-cols-[auto_1fr_auto] gap-2 items-center p-2 border rounded"
    >
      <button
        {...attributes}
        {...listeners}
        type="button"
        className="text-muted-foreground cursor-grab"
        aria-label="Drag"
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <select
        value={refId}
        onChange={(e) => onRefChange(e.target.value)}
        className="h-9 rounded-md border border-input bg-background px-2 text-sm"
      >
        <option value="">— select MT profile —</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
      <Button type="button" size="icon" variant="ghost" onClick={onRemove} aria-label="Remove">
        <Trash2 className="h-4 w-4 text-destructive" />
      </Button>
    </div>
  );
}

export function StageEditor({
  stages,
  onChange,
  options,
}: {
  stages: string[];
  onChange: (s: string[]) => void;
  options: MtRefOption[];
}) {
  const ids = stages.map((_, i) => `stage-${i}`);

  function handleDragEnd(e: DragEndEvent) {
    if (!e.over) return;
    const oldIdx = ids.indexOf(String(e.active.id));
    const newIdx = ids.indexOf(String(e.over.id));
    if (oldIdx !== newIdx && oldIdx !== -1 && newIdx !== -1) {
      onChange(arrayMove(stages, oldIdx, newIdx));
    }
  }

  return (
    <div className="space-y-2">
      {stages.length === 0 && (
        <p className="text-xs text-muted-foreground">No MT polish stages — add one or save without.</p>
      )}
      <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {stages.map((refId, i) => (
            <SortableRow
              key={`stage-${i}`}
              id={`stage-${i}`}
              refId={refId}
              onRefChange={(r) => onChange(stages.map((s, idx) => (idx === i ? r : s)))}
              onRemove={() => onChange(stages.filter((_, idx) => idx !== i))}
              options={options}
            />
          ))}
        </SortableContext>
      </DndContext>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={stages.length >= 8}
        onClick={() => onChange([...stages, ''])}
      >
        + Add MT stage
      </Button>
    </div>
  );
}
