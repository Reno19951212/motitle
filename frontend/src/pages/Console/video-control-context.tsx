import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

export type VideoControlValue = {
  playing: boolean;
  currentTime: number;
  duration: number;
  setVideoEl: (el: HTMLVideoElement | null) => void;
  play: () => Promise<void>;
  pause: () => void;
  toggle: () => void;
  seek: (seconds: number) => void;
  seekPercent: (pct: number) => void;
};

const VideoControlCtx = createContext<VideoControlValue | null>(null);

export function useVideoControl(): VideoControlValue {
  const v = useContext(VideoControlCtx);
  if (!v) throw new Error('useVideoControl must be used inside <VideoControlProvider>');
  return v;
}

export type VideoControlProviderProps = {
  children: ReactNode;
};

export function VideoControlProvider({ children }: VideoControlProviderProps) {
  const elRef = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(NaN);

  // Store listener references so removeEventListener can match by identity
  const handlersRef = useRef<{
    play: () => void;
    pause: () => void;
    timeupdate: () => void;
    loadedmetadata: () => void;
  } | null>(null);

  const setVideoEl = useCallback((el: HTMLVideoElement | null) => {
    const prev = elRef.current;
    if (prev && handlersRef.current) {
      prev.removeEventListener('play', handlersRef.current.play);
      prev.removeEventListener('pause', handlersRef.current.pause);
      prev.removeEventListener('timeupdate', handlersRef.current.timeupdate);
      prev.removeEventListener('loadedmetadata', handlersRef.current.loadedmetadata);
      handlersRef.current = null;
    }
    elRef.current = el;
    setPlaying(false);
    setCurrentTime(0);
    setDuration(NaN);
    if (el) {
      const handlers = {
        play: () => { setPlaying(true); },
        pause: () => { setPlaying(false); },
        timeupdate: () => { if (elRef.current) setCurrentTime(elRef.current.currentTime); },
        loadedmetadata: () => { if (elRef.current) setDuration(elRef.current.duration); },
      };
      handlersRef.current = handlers;
      el.addEventListener('play', handlers.play);
      el.addEventListener('pause', handlers.pause);
      el.addEventListener('timeupdate', handlers.timeupdate);
      el.addEventListener('loadedmetadata', handlers.loadedmetadata);
    }
  }, []);

  const play = useCallback(async () => {
    const el = elRef.current;
    if (!el) return;
    try { await el.play(); }
    catch (e) { console.warn('[VideoControl] play() rejected:', e); }
  }, []);

  const pause = useCallback(() => {
    const el = elRef.current;
    if (el) el.pause();
  }, []);

  const toggle = useCallback(() => {
    const el = elRef.current;
    if (!el) return;
    if (el.paused) void play();
    else pause();
  }, [play, pause]);

  const seek = useCallback((seconds: number) => {
    const el = elRef.current;
    if (!el) return;
    const dur = el.duration;
    const clamped = Math.max(0, isFinite(dur) ? Math.min(seconds, dur) : seconds);
    el.currentTime = clamped;
  }, []);

  const seekPercent = useCallback((pct: number) => {
    const el = elRef.current;
    if (!el || !isFinite(el.duration)) return;
    seek(pct * el.duration);
  }, [seek]);

  const value = useMemo<VideoControlValue>(() => ({
    playing, currentTime, duration, setVideoEl, play, pause, toggle, seek, seekPercent,
  }), [playing, currentTime, duration, setVideoEl, play, pause, toggle, seek, seekPercent]);

  useEffect(() => {
    return () => { setVideoEl(null); };
  }, [setVideoEl]);

  return <VideoControlCtx.Provider value={value}>{children}</VideoControlCtx.Provider>;
}
