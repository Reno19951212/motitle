// src/pages/Proofread/hooks/useKeyboardShortcuts.test.ts
import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useKeyboardShortcuts } from './useKeyboardShortcuts';

describe('useKeyboardShortcuts', () => {
  it('Cmd+F invokes onFindOpen with preventDefault', () => {
    const onFindOpen = vi.fn();
    renderHook(() => useKeyboardShortcuts({ onFindOpen }));
    const ev = new KeyboardEvent('keydown', { key: 'f', metaKey: true, cancelable: true });
    document.dispatchEvent(ev);
    expect(onFindOpen).toHaveBeenCalled();
    expect(ev.defaultPrevented).toBe(true);
  });

  it('Ctrl+F also invokes onFindOpen', () => {
    const onFindOpen = vi.fn();
    renderHook(() => useKeyboardShortcuts({ onFindOpen }));
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'f', ctrlKey: true }));
    expect(onFindOpen).toHaveBeenCalled();
  });

  it('Esc invokes onEscape (no preventDefault)', () => {
    const onEscape = vi.fn();
    renderHook(() => useKeyboardShortcuts({ onEscape }));
    const ev = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true });
    document.dispatchEvent(ev);
    expect(onEscape).toHaveBeenCalled();
    expect(ev.defaultPrevented).toBe(false);
  });

  it('cleanup removes listener on unmount', () => {
    const onFindOpen = vi.fn();
    const { unmount } = renderHook(() => useKeyboardShortcuts({ onFindOpen }));
    unmount();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'f', metaKey: true }));
    expect(onFindOpen).not.toHaveBeenCalled();
  });

  it('non-bound keys are ignored', () => {
    const onFindOpen = vi.fn();
    const onEscape = vi.fn();
    renderHook(() => useKeyboardShortcuts({ onFindOpen, onEscape }));
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }));
    expect(onFindOpen).not.toHaveBeenCalled();
    expect(onEscape).not.toHaveBeenCalled();
  });

  it('missing callbacks do not throw', () => {
    renderHook(() => useKeyboardShortcuts({}));
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'f', metaKey: true }));
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(true).toBe(true);
  });
});
