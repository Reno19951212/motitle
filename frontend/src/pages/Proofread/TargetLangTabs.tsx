// src/pages/Proofread/TargetLangTabs.tsx
// v5-A3 — switches which by_lang key the segment editor shows.
interface Props {
  availableLangs: string[];
  activeLang: string;
  onSelect: (lang: string) => void;
}

export function TargetLangTabs({ availableLangs, activeLang, onSelect }: Props) {
  if (availableLangs.length === 0) return null;
  return (
    <div className="lang-tabs" style={{ display: 'flex', gap: 4, padding: '4px 8px' }}>
      {availableLangs.map((l) => (
        <button
          key={l}
          type="button"
          className={`lang-tab action-chip ${l === activeLang ? 'primary' : ''}`}
          onClick={() => onSelect(l)}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
