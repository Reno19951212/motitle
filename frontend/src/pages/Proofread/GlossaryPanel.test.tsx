import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { GlossaryPanel } from './GlossaryPanel';

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('GlossaryPanel (Bold layout)', () => {
  it('shows "尚未指派" placeholder when glossaryId is null', () => {
    render(<GlossaryPanel glossaryId={null} />);
    expect(screen.getByText(/未指派詞彙表至此 pipeline/)).toBeInTheDocument();
    // Inline-add inputs are gated on a glossaryId, so should be absent.
    expect(screen.queryByLabelText('New entry source')).not.toBeInTheDocument();
  });

  it('fetches glossary + renders entries inline', async () => {
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
    await waitFor(() => expect(screen.getByText('AI')).toBeInTheDocument());
    expect(screen.getByText('人工智能')).toBeInTheDocument();
    // Inline-add inputs available now
    expect(screen.getByLabelText('New entry source')).toBeInTheDocument();
    expect(screen.getByLabelText('New entry target')).toBeInTheDocument();
  });

  it('renders the glossary panel landmark with the design class', () => {
    const { container } = render(<GlossaryPanel glossaryId={null} />);
    expect(container.querySelector('.rv-b-glossary')).not.toBeNull();
    expect(screen.getByText('詞彙表')).toBeInTheDocument();
  });
});
