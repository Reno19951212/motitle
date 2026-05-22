import { usePipelinePickerStore } from '../../stores/pipeline-picker';
import { Icon } from '../../lib/motitle-icons';
import type { IconName } from '../../lib/motitle-icons';

type StageCardSpec = {
  icon: IconName;
  name: string;
  meta: string;
};

export type PipelineStageCardsProps = Record<string, never>;

export function PipelineStageCards(_props: PipelineStageCardsProps) {
  const pipelines = usePipelinePickerStore(s => s.pipelines);
  const pipelineId = usePipelinePickerStore(s => s.pipelineId);
  const pipeline = pipelines.find(p => p.id === pipelineId);

  const cards: StageCardSpec[] = pipeline ? [
    { icon: 'waveform', name: `ASR · ${pipeline.name}`, meta: 'faster-whisper · GPU' },
    { icon: 'layers',   name: `MT · ${pipeline.name}`,  meta: 'Ollama local' },
    { icon: 'film',     name: '輸出 · H.264 MP4',       meta: 'CRF 20 · medium' },
  ] : [];

  return (
    <div className="blk" data-testid="aside-pipeline">
      <h3>
        <Icon name="flow" size={11} />
        <span>Pipeline</span>
        <span className="grow" />
      </h3>
      {pipeline ? cards.map((c, i) => (
        <div className="con-stage-card" key={i}>
          <div className="ic"><Icon name={c.icon} size={13} /></div>
          <div>
            <div className="nm">{c.name}</div>
            <div className="ms">{c.meta}</div>
          </div>
          <Icon name="caret" size={10} color="var(--text-dim)" />
        </div>
      )) : (
        <div className="con-empty-row">未揀 pipeline</div>
      )}
    </div>
  );
}
