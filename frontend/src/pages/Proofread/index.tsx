// src/pages/Proofread/index.tsx
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { TopBar } from './TopBar';

export default function Proofread() {
  const { fileId } = useParams<{ fileId: string }>();
  const [overridesOpen, setOverridesOpen] = useState(false);
  const [renderOpen, setRenderOpen] = useState(false);

  // Subsequent tasks (T2-T19) will replace these placeholders with real components.
  // setOverridesOpen / setRenderOpen are wired now so TopBar buttons compile.
  void overridesOpen;
  void renderOpen;

  if (!fileId) return <p className="p-4 text-destructive">No file ID in route.</p>;

  return (
    <div className="grid grid-rows-[auto_1fr] h-full">
      <TopBar
        file={null}
        onOpenOverrides={() => setOverridesOpen(true)}
        onOpenRender={() => setRenderOpen(true)}
      />
      <div className="grid grid-cols-2 overflow-hidden">
        <div className="border-r p-4 overflow-auto">
          <p className="text-muted-foreground text-sm">Video panel — wired in T4</p>
        </div>
        <div className="overflow-auto">
          <p className="text-muted-foreground text-sm p-4">Segment table — wired in T5</p>
        </div>
      </div>
    </div>
  );
}
