import { describe, it, expect, vi } from 'vitest';
import { render, act } from '@testing-library/react';
import { useEffect } from 'react';
import { VideoControlProvider, useVideoControl, type VideoControlValue } from './video-control-context';

function Probe({ onValue }: { onValue: (v: VideoControlValue) => void }) {
  const v = useVideoControl();
  useEffect(() => { onValue(v); }, [v, onValue]);
  return null;
}

describe('VideoControlProvider', () => {
  it('initializes with playing=false, currentTime=0, duration=NaN', () => {
    const box = { current: null as VideoControlValue | null };
    render(
      <VideoControlProvider>
        <Probe onValue={v => { box.current = v; }} />
      </VideoControlProvider>
    );
    expect(box.current?.playing).toBe(false);
    expect(box.current?.currentTime).toBe(0);
    expect(Number.isNaN(box.current?.duration)).toBe(true);
  });

  it('toggle() with no element registered is a no-op (does not throw)', () => {
    const box = { current: null as VideoControlValue | null };
    render(
      <VideoControlProvider>
        <Probe onValue={v => { box.current = v; }} />
      </VideoControlProvider>
    );
    expect(() => box.current?.toggle()).not.toThrow();
    expect(box.current?.playing).toBe(false);
  });

  it('useVideoControl() outside provider throws', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe onValue={() => {}} />)).toThrow(
      /must be used inside <VideoControlProvider>/
    );
    spy.mockRestore();
  });

  it('setVideoEl(el) attaches play/pause listeners; firing play event flips playing=true', () => {
    const box = { current: null as VideoControlValue | null };
    const Wrapper = () => {
      const v = useVideoControl();
      useEffect(() => { box.current = v; }, [v]);
      return null;
    };
    const { container } = render(
      <VideoControlProvider>
        <Wrapper />
      </VideoControlProvider>
    );

    const video = document.createElement('video');
    container.appendChild(video);

    act(() => { box.current!.setVideoEl(video); });
    act(() => { video.dispatchEvent(new Event('play')); });
    expect(box.current?.playing).toBe(true);

    act(() => { video.dispatchEvent(new Event('pause')); });
    expect(box.current?.playing).toBe(false);
  });

  it('setVideoEl(null) detaches listeners and resets state', () => {
    const box = { current: null as VideoControlValue | null };
    const Wrapper = () => {
      const v = useVideoControl();
      useEffect(() => { box.current = v; }, [v]);
      return null;
    };
    const { container } = render(
      <VideoControlProvider>
        <Wrapper />
      </VideoControlProvider>
    );

    const video = document.createElement('video');
    container.appendChild(video);
    act(() => { box.current!.setVideoEl(video); });
    act(() => { video.dispatchEvent(new Event('play')); });
    expect(box.current?.playing).toBe(true);

    act(() => { box.current!.setVideoEl(null); });
    expect(box.current?.playing).toBe(false);
    expect(box.current?.currentTime).toBe(0);

    act(() => { video.dispatchEvent(new Event('play')); });
    expect(box.current?.playing).toBe(false);
  });
});
