import { Icon } from '../../lib/motitle-icons';
import type { IconName } from '../../lib/motitle-icons';

const NAV_ITEMS: ReadonlyArray<{ id: string; icon: IconName; href: string }> = [
  { id: 'home',   icon: 'home',   href: '/' },
  { id: 'files',  icon: 'film',   href: '/console?console=1' },
  { id: 'edit',   icon: 'edit',   href: '/proofread' },
  { id: 'flow',   icon: 'flow',   href: '/pipelines' },
  { id: 'book',   icon: 'book',   href: '/glossaries' },
  { id: 'layers', icon: 'layers', href: '/transcribe_profiles' },
];

const BOTTOM_ITEMS: ReadonlyArray<{ id: string; icon: IconName }> = [
  { id: 'bell', icon: 'bell' },
  { id: 'cog',  icon: 'cog' },
  { id: 'user', icon: 'user' },
];

export type RailProps = {
  activeId?: string;
};

export function Rail({ activeId = 'files' }: RailProps) {
  return (
    <nav className="con-rail">
      <div className="mark">M</div>
      <div className="sep" />
      {NAV_ITEMS.map(item => (
        <a
          key={item.id}
          href={item.href}
          className={item.id === activeId ? 'on' : ''}
          data-testid={`rail-nav-${item.id}`}
          title={item.id}
        >
          <Icon name={item.icon} size={16} />
        </a>
      ))}
      <div className="grow" />
      {BOTTOM_ITEMS.map(item => (
        <a key={item.id} data-testid={`rail-bottom-${item.id}`}>
          <Icon name={item.icon} size={16} />
        </a>
      ))}
    </nav>
  );
}
