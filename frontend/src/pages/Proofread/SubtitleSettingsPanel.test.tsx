import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { SubtitleSettingsPanel } from './SubtitleSettingsPanel';
import type { FontConfig } from '@/lib/schemas/pipeline';

const sampleFont: FontConfig = {
  family: 'Noto',
  size: 35,
  color: '#fff',
  outline_color: '#000',
  outline_width: 2,
  margin_bottom: 40,
  subtitle_source: 'auto',
  bilingual_order: 'source_top',
};

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.restoreAllMocks();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('SubtitleSettingsPanel', () => {
  it('shows "No pipeline assigned" when pipelineId is null', () => {
    render(<SubtitleSettingsPanel pipelineId={null} font={null} />);
    fireEvent.click(screen.getByText('字幕設定'));
    expect(screen.getByText('No pipeline assigned.')).toBeInTheDocument();
  });

  it('debounced PATCH after 500ms change', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    render(<SubtitleSettingsPanel pipelineId="p1" font={sampleFont} />);
    fireEvent.click(screen.getByText('字幕設定'));
    const sizeInput = screen.getByDisplayValue('35') as HTMLInputElement;
    fireEvent.change(sizeInput, { target: { value: '40' } });
    expect(fetchSpy).not.toHaveBeenCalled();
    await act(async () => {
      vi.advanceTimersByTime(500);
    });
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/pipelines/p1'),
      expect.objectContaining({ method: 'PATCH' }),
    );
  });

  it('starts collapsed (form not visible until expand)', () => {
    render(<SubtitleSettingsPanel pipelineId="p1" font={sampleFont} />);
    expect(screen.queryByDisplayValue('Noto')).not.toBeInTheDocument();
  });
});
