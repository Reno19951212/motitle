import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { usePipelinePickerStore } from '@/stores/pipeline-picker';
import { useUIStore } from '@/stores/ui';
import { cn } from '@/lib/utils';

const ACCEPTED = {
  'video/*': ['.mp4', '.mxf', '.mov', '.mkv'],
  'audio/*': ['.wav', '.mp3', '.m4a'],
};

export function UploadDropzone() {
  const pipelineId = usePipelinePickerStore((s) => s.pipelineId);
  const pushToast = useUIStore((s) => s.pushToast);

  const onDrop = useCallback(
    async (files: File[]) => {
      if (!files.length) return;
      for (const file of files) {
        const fd = new FormData();
        fd.append('file', file);
        if (pipelineId) fd.append('pipeline_id', pipelineId);
        try {
          const r = await fetch('/api/transcribe', { method: 'POST', body: fd, credentials: 'include' });
          if (!r.ok) {
            const body = await r.json().catch(() => ({ error: r.statusText }));
            pushToast({
              title: 'Upload failed',
              description: String((body as { error?: string }).error ?? r.statusText),
              variant: 'destructive',
            });
          }
        } catch (e) {
          pushToast({ title: 'Upload failed', description: String(e), variant: 'destructive' });
        }
      }
    },
    [pipelineId, pushToast]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: ACCEPTED });

  return (
    <div
      {...getRootProps()}
      className={cn(
        'border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors',
        isDragActive ? 'border-primary bg-primary/5' : 'border-muted-foreground/30 hover:bg-muted/30'
      )}
    >
      <input {...getInputProps()} />
      <p className="text-sm text-muted-foreground">
        {isDragActive ? 'Drop here…' : 'Drag video/audio file or click to browse'}
      </p>
    </div>
  );
}
