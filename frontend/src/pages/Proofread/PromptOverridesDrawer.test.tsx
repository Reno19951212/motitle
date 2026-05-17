import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PromptOverridesDrawer } from './PromptOverridesDrawer';
import type { FileDetail } from './types';

const file: FileDetail = {
  id: 'f1',
  original_name: 'x.mp4',
  status: 'completed',
  pipeline_id: 'p1',
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('PromptOverridesDrawer', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <PromptOverridesDrawer open={false} file={file} onClose={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('fetches templates on open + populates dropdown', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          templates: [
            { id: 't1', name: 'Broadcast', overrides: { anchor_system_prompt: 'tpl-anchor' } },
          ],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    render(<PromptOverridesDrawer open file={file} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Broadcast')).toBeInTheDocument());
  });

  it('applying template fills textareas', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          templates: [{ id: 't1', name: 'B', overrides: { anchor_system_prompt: 'TPLA' } }],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    render(<PromptOverridesDrawer open file={file} onClose={vi.fn()} />);
    await waitFor(() => screen.getByText('B'));
    fireEvent.change(screen.getByLabelText('Template picker'), { target: { value: 't1' } });
    fireEvent.click(screen.getByRole('button', { name: '套用模板' }));
    const anchor = screen.getByLabelText('anchor_system_prompt') as HTMLTextAreaElement;
    expect(anchor.value).toBe('TPLA');
  });

  it('Save POSTs with overrides + invokes onClose', async () => {
    const onClose = vi.fn();
    const fetchSpy = vi
      .spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ templates: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
      );
    render(<PromptOverridesDrawer open file={file} onClose={onClose} />);
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const postCall = fetchSpy.mock.calls.find(
      (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
    );
    expect(postCall?.[0]).toContain('/api/files/f1/pipeline_overrides');
  });
});
