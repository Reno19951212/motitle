import { useEffect } from 'react';

export type HotkeyHandler = (event: KeyboardEvent) => void;
export type HotkeyMap = Record<string, HotkeyHandler>;

function eventToCombo(e: KeyboardEvent): string[] {
  const mod = e.metaKey || e.ctrlKey;
  const candidates: string[] = [];
  const key = e.key.toLowerCase();
  const keyName =
    key === ' ' ? 'space' :
    key === 'escape' ? 'esc' :
    key === 'arrowup' ? 'arrow-up' :
    key === 'arrowdown' ? 'arrow-down' :
    key === 'arrowleft' ? 'arrow-left' :
    key === 'arrowright' ? 'arrow-right' :
    key === 'enter' ? 'enter' :
    key;
  if (mod) candidates.push(`mod+${keyName}`);
  candidates.push(keyName);
  return candidates;
}

function isInteractiveTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (target.isContentEditable) return true;
  return false;
}

export function useHotkeys(map: HotkeyMap, enabled: boolean = true): void {
  useEffect(() => {
    if (!enabled) return;
    function handler(e: KeyboardEvent) {
      const combos = eventToCombo(e);
      // Esc is universal dismiss — fires even when focus is on input/textarea.
      // Other hotkeys are skipped when the user is typing.
      const isEsc = combos.includes('esc');
      if (!isEsc && isInteractiveTarget(e.target)) return;
      for (const combo of combos) {
        const fn = map[combo];
        if (fn) {
          fn(e);
          return;
        }
      }
    }
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [map, enabled]);
}
