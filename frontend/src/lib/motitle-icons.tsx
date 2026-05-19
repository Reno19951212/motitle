// MoTitle icon set — ported from /tmp/v4-design/motitle/project/primitives.jsx
// SVG paths are verbatim from the designer source.

export type IconName =
  | 'upload' | 'play' | 'pause' | 'search' | 'plus' | 'check' | 'x' | 'dots'
  | 'caret' | 'arrow' | 'file' | 'film' | 'waveform' | 'cog' | 'book'
  | 'layers' | 'flow' | 'download' | 'edit' | 'trash' | 'keyboard' | 'bell'
  | 'help' | 'home' | 'video' | 'profile' | 'arrow-left' | 'zap' | 'hash'
  | 'copy' | 'alert' | 'user' | 'clock' | 'zoom-in' | 'zoom-out' | 'scissors'
  | 'merge' | 'magnet' | 'chevron-left' | 'chevron-right' | 'pin' | 'activity';

interface IconProps {
  name: IconName;
  size?: number;
  color?: string;
}

export function Icon({ name, size = 14, color = 'currentColor' }: IconProps) {
  const s = size;
  const stroke: React.SVGAttributes<SVGElement> = {
    stroke: color,
    strokeWidth: 1.75,
    fill: 'none',
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
  };

  const paths: Record<IconName, React.ReactNode> = {
    upload:   <><path {...stroke} d="M8 10V2M4 6l4-4 4 4M2 11v2h12v-2" /></>,
    play:     <><path fill={color} d="M3 2l10 6-10 6z" /></>,
    pause:    <><rect x="3" y="2" width="3" height="12" fill={color}/><rect x="10" y="2" width="3" height="12" fill={color}/></>,
    search:   <><circle cx="7" cy="7" r="4" {...stroke}/><path {...stroke} d="M10 10l3 3"/></>,
    plus:     <><path {...stroke} d="M8 3v10M3 8h10"/></>,
    check:    <><path {...stroke} d="M3 8l3 3 7-7"/></>,
    x:        <><path {...stroke} d="M4 4l8 8M12 4l-8 8"/></>,
    dots:     <><circle cx="3" cy="8" r="1" fill={color}/><circle cx="8" cy="8" r="1" fill={color}/><circle cx="13" cy="8" r="1" fill={color}/></>,
    caret:    <><path {...stroke} d="M4 6l4 4 4-4"/></>,
    arrow:    <><path {...stroke} d="M3 8h10M9 4l4 4-4 4"/></>,
    file:     <><path {...stroke} d="M3 2h7l3 3v9H3z M10 2v3h3"/></>,
    film:     <><rect x="2" y="3" width="12" height="10" rx="1" {...stroke}/><path {...stroke} d="M2 6h12M2 10h12M5 3v10M11 3v10"/></>,
    waveform: <><path {...stroke} d="M2 8h1M4 5v6M6 3v10M8 6v4M10 4v8M12 7v2M14 8h0"/></>,
    cog:      <><circle cx="8" cy="8" r="2.5" {...stroke}/><path {...stroke} d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6L13 13M3 13l1.4-1.4M11.6 4.4L13 3"/></>,
    book:     <><path {...stroke} d="M3 3h4a3 3 0 013 3v8a2 2 0 00-2-2H3z M13 3H9a3 3 0 00-3 3v8a2 2 0 012-2h5z"/></>,
    layers:   <><path {...stroke} d="M8 2l6 3-6 3-6-3zM2 8l6 3 6-3M2 11l6 3 6-3"/></>,
    flow:     <><rect x="1" y="5" width="4" height="6" rx="1" {...stroke}/><rect x="11" y="5" width="4" height="6" rx="1" {...stroke}/><circle cx="8" cy="2" r="1.5" {...stroke}/><circle cx="8" cy="14" r="1.5" {...stroke}/><path {...stroke} d="M5 8h6 M8 3.5v3 M8 9.5v3"/></>,
    download: <><path {...stroke} d="M8 2v8M4 7l4 4 4-4M2 13h12"/></>,
    edit:     <><path {...stroke} d="M11 2l3 3-8 8H3v-3z"/></>,
    trash:    <><path {...stroke} d="M3 4h10M6 4V2h4v2M5 4v10h6V4"/></>,
    keyboard: <><rect x="1" y="4" width="14" height="8" rx="1" {...stroke}/><path {...stroke} d="M3 7h1M6 7h1M9 7h1M12 7h1M4 10h8"/></>,
    bell:     <><path {...stroke} d="M4 12V8a4 4 0 118 0v4l1 1H3zM6 13a2 2 0 004 0"/></>,
    help:     <><circle cx="8" cy="8" r="6" {...stroke}/><path {...stroke} d="M6.5 6a1.5 1.5 0 013 0c0 1-1.5 1.5-1.5 2.5M8 11v0.5"/></>,
    home:     <><path {...stroke} d="M2 8l6-5 6 5v6H2z M6 14V9h4v5"/></>,
    video:    <><rect x="1" y="4" width="10" height="8" rx="1" {...stroke}/><path {...stroke} d="M11 7l4-2v6l-4-2z"/></>,
    profile:  <><circle cx="8" cy="5" r="2.5" {...stroke}/><path {...stroke} d="M3 14c0-3 2.5-5 5-5s5 2 5 5"/></>,
    'arrow-left': <><path {...stroke} d="M13 8H3M7 4L3 8l4 4"/></>,
    zap:      <><path {...stroke} d="M9 1L3 9h4l-1 6 6-8H8z"/></>,
    hash:     <><path {...stroke} d="M5 2L4 14M12 2l-1 12M2 5h12M2 11h12"/></>,
    copy:     <><rect x="4" y="4" width="9" height="10" rx="1" {...stroke}/><path {...stroke} d="M3 11V3a1 1 0 011-1h8"/></>,
    alert:    <><path {...stroke} d="M8 2l6 11H2zM8 6v4M8 12v0.5"/></>,
    user:     <><circle cx="8" cy="5" r="2.5" {...stroke}/><path {...stroke} d="M3 14c0-3 2.5-5 5-5s5 2 5 5"/></>,
    clock:    <><circle cx="8" cy="8" r="6" {...stroke}/><path {...stroke} d="M8 4v4l3 2"/></>,
    'zoom-in':  <><circle cx="7" cy="7" r="4" {...stroke}/><path {...stroke} d="M10 10l3 3M5 7h4M7 5v4"/></>,
    'zoom-out': <><circle cx="7" cy="7" r="4" {...stroke}/><path {...stroke} d="M10 10l3 3M5 7h4"/></>,
    scissors: <><circle cx="4" cy="4" r="2" {...stroke}/><circle cx="4" cy="12" r="2" {...stroke}/><path {...stroke} d="M6 5l8 7M6 11l8-7"/></>,
    merge:    <><path {...stroke} d="M3 3l5 5v5M13 3l-5 5"/></>,
    magnet:   <><path {...stroke} d="M3 3v6a5 5 0 0010 0V3h-3v6a2 2 0 01-4 0V3z"/></>,
    'chevron-left':  <><path {...stroke} d="M10 3l-5 5 5 5"/></>,
    'chevron-right': <><path {...stroke} d="M6 3l5 5-5 5"/></>,
    pin:      <><path {...stroke} d="M8 1l3 3-1 1 2 4-3 1-1-1-3 5-1-1 3-3-1-2-2-1z"/></>,
    activity: <><path {...stroke} d="M2 8h3l2-5 3 10 2-5h2"/></>,
  };

  return (
    <svg width={s} height={s} viewBox="0 0 16 16" style={{ flexShrink: 0 }}>
      {paths[name] ?? null}
    </svg>
  );
}

// Badge primitive
interface BadgeProps {
  kind?: 'idle' | 'processing' | 'queued' | 'done' | 'done-solid' | 'error' | 'accent';
  children: React.ReactNode;
}

export function MoTitleBadge({ kind = 'idle', children }: BadgeProps) {
  return <span className={`badge badge--${kind}`}>{children}</span>;
}

// StageBadge derived from file status
export interface StageBadgeFile {
  stage: string;
  transcribeProgress?: number;
  renderProgress?: number;
}

export function MoTitleStageBadge({ file }: { file: StageBadgeFile }) {
  switch (file.stage) {
    case 'transcribing':
      return (
        <span className="badge badge--processing">
          <span className="dot" style={{ animation: 'pulse 1.3s infinite' }} />
          轉錄中 {file.transcribeProgress ?? 0}%
        </span>
      );
    case 'translating':
      return (
        <span className="badge badge--processing">
          <span className="dot" /> 翻譯中
        </span>
      );
    case 'proofreading':
      return (
        <span className="badge badge--queued">
          <span className="dot" /> 待校對
        </span>
      );
    case 'rendering':
      return (
        <span className="badge badge--processing">
          <span className="dot" /> 燒字中 {file.renderProgress ?? 0}%
        </span>
      );
    case 'done':
      return (
        <span className="badge badge--done-solid">
          <Icon name="check" size={10} /> 完成
        </span>
      );
    case 'error':
      return (
        <span className="badge badge--error">
          <Icon name="x" size={10} /> 錯誤
        </span>
      );
    default:
      return <span className="badge badge--idle">待處理</span>;
  }
}
