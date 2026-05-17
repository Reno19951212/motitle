import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { GlossaryApplyModal } from './GlossaryApplyModal';

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('GlossaryApplyModal', () => {
  it('does not scan when closed', () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    render(<GlossaryApplyModal open={false} fileId="f1" onClose={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('scans on open + shows violations', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          strict_violations: [
            {
              segment_idx: 0,
              term_source: 'AI',
              term_target: '人工智能',
              glossary_id: 'g1',
              glossary_name: 'Tech',
              current_zh: 'AI已普及',
              status: 'pending',
            },
          ],
          loose_violations: [],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    render(<GlossaryApplyModal open fileId="f1" onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('AI')).toBeInTheDocument());
    expect(screen.getByText('人工智能')).toBeInTheDocument();
  });

  it('checks pending violations by default + unchecks approved', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          strict_violations: [
            {
              segment_idx: 0,
              term_source: 'A',
              term_target: 'a',
              glossary_id: 'g1',
              current_zh: 'x',
              status: 'pending',
            },
            {
              segment_idx: 1,
              term_source: 'B',
              term_target: 'b',
              glossary_id: 'g1',
              current_zh: 'y',
              status: 'approved',
            },
          ],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    render(<GlossaryApplyModal open fileId="f1" onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('A')).toBeInTheDocument());
    const [cb0, cb1] = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(cb0?.checked).toBe(true);
    expect(cb1?.checked).toBe(false);
  });

  it('Apply POSTs selected violations and invokes onApplied + onClose', async () => {
    const onClose = vi.fn();
    const onApplied = vi.fn();
    const fetchSpy = vi
      .spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            strict_violations: [
              {
                segment_idx: 0,
                term_source: 'A',
                term_target: 'a',
                glossary_id: 'g1',
                current_zh: 'x',
                status: 'pending',
              },
            ],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
      );
    render(<GlossaryApplyModal open fileId="f1" onClose={onClose} onApplied={onApplied} />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Apply/ })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /Apply/ }));
    await waitFor(() => expect(onApplied).toHaveBeenCalled());
    const applyCall = fetchSpy.mock.calls.find(
      (c) => typeof c[0] === 'string' && c[0].includes('/glossary-apply'),
    );
    expect(applyCall).toBeTruthy();
    expect(onClose).toHaveBeenCalled();
  });
});
