// src/components/LangPicker.tsx
// Shared lang-tab strip — switches between by_lang keys. Used by both the
// Proofread page (TargetLangTabs re-export) and the Dashboard live overlay.
interface Props {
  availableLangs: string[];
  activeLang: string;
  onSelect: (lang: string) => void;
}

export function LangPicker({ availableLangs, activeLang, onSelect }: Props) {
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
