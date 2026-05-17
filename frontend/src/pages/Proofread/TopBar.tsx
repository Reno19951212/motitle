// src/pages/Proofread/TopBar.tsx
import { useNavigate } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { FileDetail } from './types';

interface Props {
  file: FileDetail | null;
  onOpenOverrides: () => void;
  onOpenRender: () => void;
}

export function TopBar({ file, onOpenOverrides, onOpenRender }: Props) {
  const navigate = useNavigate();
  return (
    <div className="flex items-center justify-between px-4 h-12 border-b bg-background">
      <div className="flex items-center gap-2">
        <Button size="sm" variant="ghost" onClick={() => navigate('/')}>
          <ChevronLeft className="h-4 w-4 mr-1" /> Back
        </Button>
        <h2 className="text-sm font-medium">{file?.original_name ?? 'Loading…'}</h2>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" onClick={onOpenOverrides}>⚙ Overrides</Button>
        <Button size="sm" onClick={onOpenRender}>▶ Render</Button>
      </div>
    </div>
  );
}
