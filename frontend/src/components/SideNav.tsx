import { NavLink } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import { cn } from '@/lib/utils';

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/pipelines', label: 'Pipelines' },
  { to: '/asr_profiles', label: 'ASR Profiles' },
  { to: '/mt_profiles', label: 'MT Profiles' },
  { to: '/glossaries', label: 'Glossaries' },
];

export function SideNav() {
  const isAdmin = useAuthStore((s) => !!s.user?.is_admin);
  const items = isAdmin ? [...NAV, { to: '/admin', label: 'Admin' }] : NAV;
  return (
    <nav className="flex flex-col gap-1 p-3">
      {items.map((i) => (
        <NavLink
          key={i.to}
          to={i.to}
          end={i.to === '/'}
          className={({ isActive }) =>
            cn('rounded px-3 py-2 text-sm', isActive ? 'bg-accent font-medium' : 'hover:bg-accent/50')
          }
        >
          {i.label}
        </NavLink>
      ))}
    </nav>
  );
}
