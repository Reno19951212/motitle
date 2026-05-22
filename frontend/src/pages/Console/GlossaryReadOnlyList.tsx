import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../../lib/api';
import { Icon } from '../../lib/motitle-icons';
import { usePipelinePickerStore } from '../../stores/pipeline-picker';
import { useProfileLookupStore } from '../../stores/profile-lookup';

type GlossaryRow = { id: string; name: string; entry_count?: number };

export type GlossaryReadOnlyListProps = Record<string, never>;

export function GlossaryReadOnlyList(_props: GlossaryReadOnlyListProps) {
  const navigate = useNavigate();
  const pipelineId = usePipelinePickerStore(s => s.pipelineId);
  const fetchPipeline = useProfileLookupStore(s => s.fetchPipeline);
  const [glossaries, setGlossaries] = useState<GlossaryRow[]>([]);
  const [activeIds, setActiveIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    apiFetch<{ glossaries?: GlossaryRow[] }>('/api/glossaries')
      .then(r => setGlossaries(r.glossaries ?? []))
      .catch(() => setGlossaries([]));
  }, []);

  useEffect(() => {
    if (!pipelineId) { setActiveIds(new Set()); return; }
    fetchPipeline(pipelineId).then((p) => {
      const ids: string[] = p?.glossary_stage?.glossary_ids ?? [];
      setActiveIds(new Set(ids));
    }).catch(() => setActiveIds(new Set()));
  }, [pipelineId, fetchPipeline]);

  return (
    <div className="blk" data-testid="aside-glossary">
      <h3>
        <Icon name="book" size={11} />
        <span>術語表 · {activeIds.size} 啟用</span>
      </h3>
      <div className="con-gloss-list">
        {glossaries.map(g => {
          const on = activeIds.has(g.id);
          return (
            <div
              key={g.id}
              className={`con-gloss-row ${on ? 'on' : ''}`}
              onClick={() => navigate(`/glossaries/${g.id}`)}
            >
              {on ? (
                <Icon name="check" size={10} color="var(--accent-2)" />
              ) : (
                <span className="r-dot r-dot--idle" />
              )}
              <span className="nm" style={!on ? { color: 'var(--text-dim)' } : undefined}>
                {g.name}
              </span>
              <span className="ct">{g.entry_count ?? 0} 條</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
