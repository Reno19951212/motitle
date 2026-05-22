import { PipelineStageCards } from './PipelineStageCards';
import { GlossaryReadOnlyList } from './GlossaryReadOnlyList';
import { FileFactsBlock } from './FileFactsBlock';
import type { FileRecord } from '../../lib/socket-events';

export type AsideColumnProps = {
  selectedFile?: FileRecord | null;
};

export function AsideColumn({ selectedFile = null }: AsideColumnProps) {
  return (
    <aside className="con-aside">
      <PipelineStageCards />
      <GlossaryReadOnlyList />
      <FileFactsBlock file={selectedFile} />
    </aside>
  );
}
