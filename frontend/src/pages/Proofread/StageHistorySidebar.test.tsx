import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StageHistorySidebar } from './StageHistorySidebar';
import type { FileDetail } from './types';

const sampleFile: FileDetail = {
  id: 'a',
  original_name: 'x.mp4',
  status: 'completed',
  stage_outputs: [
    {
      stage_type: 'asr',
      stage_ref: 'asr-profile-1',
      segments: [{ id: 's0', start: 0, end: 1, text: 'ASR text' }],
    },
    {
      stage_type: 'mt',
      stage_ref: 'mt-profile-1',
      segments: [{ id: 's0', start: 0, end: 1, text: 'MT text' }],
    },
  ],
};

beforeEach(() => { vi.restoreAllMocks(); });

describe('StageHistorySidebar', () => {
  it('renders nothing when open=false', () => {
    const { container } = render(
      <StageHistorySidebar open={false} file={sampleFile} segmentIdx={0} onClose={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when file is null', () => {
    const { container } = render(
      <StageHistorySidebar open file={null} segmentIdx={0} onClose={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders all stages for a given segmentIdx', () => {
    render(<StageHistorySidebar open file={sampleFile} segmentIdx={0} onClose={vi.fn()} />);
    expect(screen.getByText('ASR text')).toBeInTheDocument();
    expect(screen.getByText('MT text')).toBeInTheDocument();
  });

  it('close button invokes onClose', () => {
    const onClose = vi.fn();
    render(<StageHistorySidebar open file={sampleFile} segmentIdx={0} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('Close sidebar'));
    expect(onClose).toHaveBeenCalled();
  });

  it('Edit button reveals textarea + Save invokes PATCH API', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    render(<StageHistorySidebar open file={sampleFile} segmentIdx={0} onClose={vi.fn()} />);
    fireEvent.click(screen.getByLabelText('Edit stage 0'));
    const textarea = screen.getByLabelText('Edit text for stage 0') as HTMLTextAreaElement;
    expect(textarea.value).toBe('ASR text');
    fireEvent.change(textarea, { target: { value: 'edited' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await new Promise((r) => setTimeout(r, 0));
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/files/a/stages/0/segments/0'),
      expect.objectContaining({ method: 'PATCH' }),
    );
  });
});
