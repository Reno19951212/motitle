import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { SubtitleSettingsPanel } from './SubtitleSettingsPanel';
import type { ActiveProfile } from './hooks/useActiveProfile';

const sample: ActiveProfile = {
  id: 'p1',
  name: 'P',
  font: {
    family: 'Noto',
    size: 35,
    color: '#fff',
    outline_color: '#000',
    outline_width: 2,
    margin_bottom: 40,
    subtitle_source: 'auto',
    bilingual_order: 'source_top',
  },
};

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.restoreAllMocks();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('SubtitleSettingsPanel', () => {
  it('shows "No active profile" when profile is null', () => {
    render(<SubtitleSettingsPanel profile={null} />);
    fireEvent.click(screen.getByText('字幕設定'));
    expect(screen.getByText('No active profile.')).toBeInTheDocument();
  });

  it('debounced PATCH after 500ms change', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    render(<SubtitleSettingsPanel profile={sample} />);
    fireEvent.click(screen.getByText('字幕設定'));
    const sizeInput = screen.getByDisplayValue('35') as HTMLInputElement;
    fireEvent.change(sizeInput, { target: { value: '40' } });
    expect(fetchSpy).not.toHaveBeenCalled();
    await act(async () => {
      vi.advanceTimersByTime(500);
    });
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/profiles/p1'),
      expect.objectContaining({ method: 'PATCH' }),
    );
  });

  it('starts collapsed (form not visible until expand)', () => {
    render(<SubtitleSettingsPanel profile={sample} />);
    expect(screen.queryByDisplayValue('Noto')).not.toBeInTheDocument();
  });
});
