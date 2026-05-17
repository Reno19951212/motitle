import { useEffect } from 'react';
import { usePipelinePickerStore } from '@/stores/pipeline-picker';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';

export function PipelinePicker() {
  const pipelineId = usePipelinePickerStore((s) => s.pipelineId);
  const pipelines = usePipelinePickerStore((s) => s.pipelines);
  const setPipelineId = usePipelinePickerStore((s) => s.setPipelineId);
  const refresh = usePipelinePickerStore((s) => s.refresh);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="space-y-1">
      <Label htmlFor="pipeline-picker">Pipeline</Label>
      <Select value={pipelineId ?? undefined} onValueChange={(v) => setPipelineId(v || null)}>
        <SelectTrigger id="pipeline-picker" className="w-64">
          <SelectValue placeholder="Select a pipeline…" />
        </SelectTrigger>
        <SelectContent>
          {pipelines.map((p) => (
            <SelectItem key={p.id} value={p.id}>
              {p.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
