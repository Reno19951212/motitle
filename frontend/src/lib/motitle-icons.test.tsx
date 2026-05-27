import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MoTitleStageBadge } from './motitle-icons';

describe('<MoTitleStageBadge>', () => {
  it('asrPhase="queued" → 排隊中 badge with pulsing dot', () => {
    render(<MoTitleStageBadge file={{ stage: 'idle', asrPhase: 'queued' }} />);
    const badge = screen.getByText(/排隊中/);
    expect(badge).toBeInTheDocument();
    expect(badge.closest('.badge')).toHaveClass('badge--queued');
    expect(badge.closest('.badge')?.querySelector('.dot')).not.toBeNull();
  });

  it('asrPhase="starting" → 準備中 badge with pulsing dot', () => {
    render(<MoTitleStageBadge file={{ stage: 'idle', asrPhase: 'starting' }} />);
    const badge = screen.getByText(/準備中/);
    expect(badge).toBeInTheDocument();
    expect(badge.closest('.badge')).toHaveClass('badge--processing');
    expect(badge.closest('.badge')?.querySelector('.dot')).not.toBeNull();
  });

  it('asrPhase="queued" takes precedence over legacy file.stage="idle"', () => {
    render(<MoTitleStageBadge file={{ stage: 'idle', asrPhase: 'queued' }} />);
    expect(screen.getByText(/排隊中/)).toBeInTheDocument();
  });

  it('no asrPhase → falls through to legacy file.stage switch', () => {
    render(<MoTitleStageBadge file={{ stage: 'transcribing', transcribeProgress: 42 }} />);
    expect(screen.getByText(/轉錄中/)).toBeInTheDocument();
    expect(screen.getByText(/42/)).toBeInTheDocument();
  });
});
