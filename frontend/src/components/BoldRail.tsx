// BoldRail — left-edge icon rail shared by all Bold full-page layouts.
// Extracted from Dashboard.tsx during iter 1 of the Bold variant rollout.
// All pages that use motitle-bold.css should reuse this component to avoid
// drift in nav items / hover tooltips / icon spacing.
import { Link } from 'react-router-dom';
import { Icon } from '@/lib/motitle-icons';
import type { IconName } from '@/lib/motitle-icons';

export const RAIL_ITEMS: Array<{
  id: string;
  icon: IconName;
  label: string;
  href: string;
}> = [
  { id: 'home',     icon: 'home',     label: '主頁',     href: '/' },
  { id: 'files',    icon: 'film',     label: '檔案',     href: '/' },
  { id: 'proof',    icon: 'edit',     label: '校對',     href: '/' },
  { id: 'pipeline', icon: 'flow',     label: 'Pipeline', href: '/pipelines' },
  { id: 'asr',      icon: 'waveform', label: 'ASR',      href: '/asr_profiles' },
  { id: 'mt',       icon: 'layers',   label: 'MT',       href: '/mt_profiles' },
  { id: 'gloss',    icon: 'book',     label: '術語表',   href: '/glossaries' },
  { id: 'admin',    icon: 'user',     label: '管理員',   href: '/admin' },
];

interface BoldRailProps {
  /** Which rail item should render with the .on active marker. Defaults to 'home'. */
  activeId?: string;
}

export function BoldRail({ activeId = 'home' }: BoldRailProps) {
  return (
    <div className="b-rail">
      <div className="mark">M</div>
      {RAIL_ITEMS.map((it) => (
        <Link
          key={it.id}
          to={it.href}
          className={`rail-btn ${it.id === activeId ? 'on' : ''}`}
        >
          <Icon name={it.icon} size={16} />
          <span className="tt">{it.label}</span>
        </Link>
      ))}
      <div className="flex1" />
      <button className="rail-btn" title="通知">
        <Icon name="bell" size={16} />
        <span className="tt">通知</span>
      </button>
      <button className="rail-btn" title="設定">
        <Icon name="cog" size={16} />
        <span className="tt">設定</span>
      </button>
      <button className="rail-btn" title="說明">
        <Icon name="help" size={16} />
        <span className="tt">說明</span>
      </button>
    </div>
  );
}
