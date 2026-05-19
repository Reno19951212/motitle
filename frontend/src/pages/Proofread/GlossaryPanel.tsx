// src/pages/Proofread/GlossaryPanel.tsx
// Bold-variant glossary panel that fills `.rv-b-glossary`. Shows the active
// pipeline's glossary entries as a compact table; supports inline add.
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';

interface Entry {
  source: string;
  target: string;
  target_aliases: string[];
}

interface Glossary {
  id: string;
  name: string;
  entries: Entry[];
}

interface Props {
  glossaryId: string | null;
}

export function GlossaryPanel({ glossaryId }: Props) {
  const [glossary, setGlossary] = useState<Glossary | null>(null);
  const [loading, setLoading] = useState(false);
  const [newSource, setNewSource] = useState('');
  const [newTarget, setNewTarget] = useState('');

  useEffect(() => {
    if (!glossaryId) {
      setGlossary(null);
      return;
    }
    setLoading(true);
    apiFetch<Glossary>(`/api/glossaries/${glossaryId}`)
      .then(setGlossary)
      .catch(() => setGlossary(null))
      .finally(() => setLoading(false));
  }, [glossaryId]);

  async function addEntry() {
    if (!glossaryId || !newSource.trim() || !newTarget.trim()) return;
    try {
      await apiFetch(`/api/glossaries/${glossaryId}/entries`, {
        method: 'POST',
        body: JSON.stringify({
          source: newSource.trim(),
          target: newTarget.trim(),
          target_aliases: [],
        }),
      });
      setNewSource('');
      setNewTarget('');
      const updated = await apiFetch<Glossary>(`/api/glossaries/${glossaryId}`);
      setGlossary(updated);
    } catch {
      /* swallow — toast wiring in later iter */
    }
  }

  return (
    <div className="rv-b-glossary" data-testid="glossary-panel">
      <div className="rv-b-glossary-head">
        <span className="rv-b-glossary-title">詞彙表</span>
        <span style={{ flex: 1, minWidth: 0, fontSize: 11, color: 'var(--text-mid)' }}>
          {glossary ? glossary.name : glossaryId ? '載入中…' : '尚未指派'}
        </span>
      </div>
      <div className="rv-b-glossary-body">
        {!glossaryId && (
          <div className="rv-b-rail-empty">未指派詞彙表至此 pipeline</div>
        )}
        {glossaryId && loading && <div className="rv-b-rail-empty">載入中…</div>}
        {glossaryId && !loading && glossary && glossary.entries.length === 0 && (
          <div className="rv-b-rail-empty">暫無條目</div>
        )}
        {glossaryId && !loading && glossary && glossary.entries.length > 0 && (
          <table className="rv-b-glossary-table">
            <thead>
              <tr>
                <th>原文</th>
                <th>譯文</th>
              </tr>
            </thead>
            <tbody>
              {glossary.entries.map((e, i) => (
                <tr key={i}>
                  <td>{e.source}</td>
                  <td>{e.target}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {glossaryId && !loading && (
          <div
            style={{
              borderTop: '1px solid var(--border)',
              padding: '6px 8px',
              display: 'flex',
              gap: 4,
            }}
          >
            <input
              className="rv-b-glossary-select"
              placeholder="source"
              value={newSource}
              onChange={(e) => setNewSource(e.target.value)}
              aria-label="New entry source"
              style={{ flex: 1 }}
            />
            <input
              className="rv-b-glossary-select"
              placeholder="target"
              value={newTarget}
              onChange={(e) => setNewTarget(e.target.value)}
              aria-label="New entry target"
              style={{ flex: 1 }}
            />
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void addEntry()}
              disabled={!newSource.trim() || !newTarget.trim()}
            >
              +
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
