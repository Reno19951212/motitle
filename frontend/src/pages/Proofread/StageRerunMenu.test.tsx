import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StageRerunMenu } from './StageRerunMenu';
import type { FileDetail } from './types';

const file: FileDetail = {
  id: 'f1',
  original_name: 'x.mp4',
  status: 'completed',
  stage_outputs: [
    { stage_type: 'asr', stage_ref: 'asr-1', segments: [] },
    { stage_type: 'mt', stage_ref: 'mt-1', segments: [] },
  ],
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('StageRerunMenu', () => {
  it('renders the trigger button + stages on expand', () => {
    render(<StageRerunMenu file={file} />);
    const summary = screen.getByText('Re-run').closest('summary')!;
    fireEvent.click(summary);
    expect(screen.getByText(/Stage 0/)).toBeInTheDocument();
    expect(screen.getByText(/Stage 1/)).toBeInTheDocument();
  });

  it('clicking a stage POSTs rerun endpoint + invokes onTriggered', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    const onTriggered = vi.fn();
    render(<StageRerunMenu file={file} onTriggered={onTriggered} />);
    fireEvent.click(screen.getByText('Re-run').closest('summary')!);
    fireEvent.click(screen.getByText(/Stage 1/).closest('button')!);
    await new Promise((r) => setTimeout(r, 0));
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/files/f1/stages/1/rerun'),
      expect.objectContaining({ method: 'POST' }),
    );
    expect(onTriggered).toHaveBeenCalledWith(1);
  });

  it('shows empty state when no stages', () => {
    render(<StageRerunMenu file={{ ...file, stage_outputs: [] }} />);
    fireEvent.click(screen.getByText('Re-run').closest('summary')!);
    expect(screen.getByText('No stages yet.')).toBeInTheDocument();
  });
});
