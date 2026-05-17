import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { GlossaryPanel } from './GlossaryPanel';
import type { ActiveProfile } from './hooks/useActiveProfile';

const profileWithGlossary: ActiveProfile = {
  id: 'p1',
  name: 'P',
  font: {
    family: 'X',
    size: 35,
    color: '#fff',
    outline_color: '#000',
    outline_width: 2,
    margin_bottom: 40,
    subtitle_source: 'auto',
    bilingual_order: 'source_top',
  },
  translation: { glossary_id: 'g1' },
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('GlossaryPanel', () => {
  it('shows "no glossary assigned" when profile has none', () => {
    render(<GlossaryPanel profile={{ ...profileWithGlossary, translation: {} }} />);
    fireEvent.click(screen.getByText('詞彙表對照'));
    expect(screen.getByText(/No glossary assigned/i)).toBeInTheDocument();
  });

  it('fetches glossary on expand + renders entries', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          id: 'g1',
          name: 'G1',
          entries: [{ source: 'AI', target: '人工智能', target_aliases: [] }],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    render(<GlossaryPanel profile={profileWithGlossary} />);
    fireEvent.click(screen.getByText('詞彙表對照'));
    await waitFor(() => expect(screen.getByText('AI')).toBeInTheDocument());
    expect(screen.getByText('人工智能')).toBeInTheDocument();
  });

  it('starts collapsed (entries not visible until expand)', () => {
    render(<GlossaryPanel profile={profileWithGlossary} />);
    expect(screen.queryByText(/No glossary assigned/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('New entry source')).not.toBeInTheDocument();
  });
});
