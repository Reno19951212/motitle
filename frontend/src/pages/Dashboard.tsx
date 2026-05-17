import { useSocket } from '@/providers/SocketProvider';
import { PipelinePicker } from '@/components/PipelinePicker';
import { UploadDropzone } from '@/components/UploadDropzone';

export default function Dashboard() {
  const { state } = useSocket();
  const fileCount = Object.keys(state.files).length;

  return (
    <div className="space-y-6">
      <div className="flex items-end gap-4">
        <PipelinePicker />
        <div className="flex-1">
          <UploadDropzone />
        </div>
      </div>
      <div className="space-y-3">
        {fileCount === 0 ? (
          <p className="text-muted-foreground text-sm">No files yet. Upload one above.</p>
        ) : (
          <p className="text-muted-foreground text-sm">{fileCount} file(s) — cards land in T14.</p>
        )}
      </div>
    </div>
  );
}
