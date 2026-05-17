import { useSocket } from '@/providers/SocketProvider';
import { PipelinePicker } from '@/components/PipelinePicker';
import { UploadDropzone } from '@/components/UploadDropzone';
import { FileCard } from '@/components/FileCard';

export default function Dashboard() {
  const { state } = useSocket();
  const files = Object.values(state.files).sort((a, b) => {
    const ta = typeof a.created_at === 'number' ? a.created_at : 0;
    const tb = typeof b.created_at === 'number' ? b.created_at : 0;
    return tb - ta;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-end gap-4">
        <PipelinePicker />
        <div className="flex-1">
          <UploadDropzone />
        </div>
      </div>
      <div className="space-y-3">
        {files.length === 0 && (
          <p className="text-muted-foreground text-sm">No files yet. Upload one above.</p>
        )}
        {files.map((f) => (
          <FileCard
            key={f.id}
            file={f}
            progress={state.stageProgress[f.id] ?? {}}
            status={state.stageStatus[f.id] ?? {}}
          />
        ))}
      </div>
    </div>
  );
}
