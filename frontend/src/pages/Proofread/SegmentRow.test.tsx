// src/pages/Proofread/SegmentRow.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SegmentRow } from './SegmentRow';
import type { Translation } from './types';

function row(overrides: Partial<Translation> = {}): Translation {
  return { idx: 0, en_text: 'hello', zh_text: '你好', status: 'pending', flags: [], ...overrides };
}

function wrap(children: React.ReactNode) {
  return (
    <table>
      <tbody>{children}</tbody>
    </table>
  );
}

const noop = () => {};

describe('SegmentRow', () => {
  it('renders text + status', () => {
    render(
      wrap(
        <SegmentRow
          t={row()}
          isFocused={false}
          onEditDraft={noop}
          onSave={noop}
          onRevert={noop}
          onApprove={noop}
          onShowHistory={noop}
        />,
      ),
    );
    expect(screen.getByText('hello')).toBeInTheDocument();
    expect(screen.getByText('你好')).toBeInTheDocument();
    expect(screen.getByText('pending')).toBeInTheDocument();
  });

  it('shows Approve button when not approved', () => {
    render(
      wrap(
        <SegmentRow
          t={row()}
          isFocused={false}
          onEditDraft={noop}
          onSave={noop}
          onRevert={noop}
          onApprove={noop}
          onShowHistory={noop}
        />,
      ),
    );
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
  });

  it('hides Approve button when approved', () => {
    render(
      wrap(
        <SegmentRow
          t={row({ status: 'approved' })}
          isFocused={false}
          onEditDraft={noop}
          onSave={noop}
          onRevert={noop}
          onApprove={noop}
          onShowHistory={noop}
        />,
      ),
    );
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
  });

  it('shows "long" badge when flag present', () => {
    render(
      wrap(
        <SegmentRow
          t={row({ flags: ['long'] })}
          isFocused={false}
          onEditDraft={noop}
          onSave={noop}
          onRevert={noop}
          onApprove={noop}
          onShowHistory={noop}
        />,
      ),
    );
    expect(screen.getByText('long')).toBeInTheDocument();
  });

  it('double-click on zh cell enters edit mode + Enter commits via onSave', () => {
    const onSave = vi.fn();
    const onEditDraft = vi.fn();
    render(
      wrap(
        <SegmentRow
          t={row()}
          isFocused={false}
          onEditDraft={onEditDraft}
          onSave={onSave}
          onRevert={noop}
          onApprove={noop}
          onShowHistory={noop}
        />,
      ),
    );
    const cell = screen.getByText('你好');
    fireEvent.doubleClick(cell);
    const input = screen.getByLabelText('Edit segment 0') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '你好嗎' } });
    expect(onEditDraft).toHaveBeenCalledWith(0, '你好嗎');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSave).toHaveBeenCalledWith(0);
  });

  it('Escape reverts via onRevert', () => {
    const onRevert = vi.fn();
    render(
      wrap(
        <SegmentRow
          t={row()}
          isFocused={false}
          onEditDraft={noop}
          onSave={noop}
          onRevert={onRevert}
          onApprove={noop}
          onShowHistory={noop}
        />,
      ),
    );
    fireEvent.doubleClick(screen.getByText('你好'));
    const input = screen.getByLabelText('Edit segment 0');
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(onRevert).toHaveBeenCalledWith(0);
  });

  it('Approve click invokes onApprove', () => {
    const onApprove = vi.fn();
    render(
      wrap(
        <SegmentRow
          t={row()}
          isFocused={false}
          onEditDraft={noop}
          onSave={noop}
          onRevert={noop}
          onApprove={onApprove}
          onShowHistory={noop}
        />,
      ),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(onApprove).toHaveBeenCalledWith(0);
  });
});
