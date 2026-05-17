import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { GlossaryPanel } from './GlossaryPanel';

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('GlossaryPanel', () => {
  it('shows "no glossary assigned" when glossaryId is null', () => {
    render(<GlossaryPanel glossaryId={null} />);
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
    render(<GlossaryPanel glossaryId="g1" />);
    fireEvent.click(screen.getByText('詞彙表對照'));
    await waitFor(() => expect(screen.getByText('AI')).toBeInTheDocument());
    expect(screen.getByText('人工智能')).toBeInTheDocument();
  });

  it('starts collapsed (entries not visible until expand)', () => {
    render(<GlossaryPanel glossaryId="g1" />);
    expect(screen.queryByText(/No glossary assigned/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('New entry source')).not.toBeInTheDocument();
  });
});
