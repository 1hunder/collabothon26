import { CreditCard, Headphones, Home, TrendingUp, User } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

interface Tab {
  label: string;
  root: string;
  Icon: LucideIcon;
}

const tabs: readonly Tab[] = [
  { label: 'Overview', root: '/overview', Icon: Home },
  { label: 'Payments', root: '/payments', Icon: CreditCard },
  { label: 'Investments', root: '/investments', Icon: TrendingUp },
  { label: 'Service', root: '/service', Icon: Headphones },
  { label: 'Profile', root: '/profile', Icon: User },
];

export default function TabBar(): React.JSX.Element {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const activeSegment = pathname.split('/')[1] ?? '';

  return (
    <nav
      aria-label="Main"
      className="fixed bottom-0 left-1/2 z-50 w-full max-w-[430px] -translate-x-1/2 border-t border-line bg-white pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="flex h-16">
        {tabs.map(({ label, root, Icon }) => {
          const isActive = root === `/${activeSegment}`;
          return (
            <li key={label} className="flex-1">
              <button
                type="button"
                aria-current={isActive ? 'page' : undefined}
                onClick={() => navigate(root, { replace: isActive })}
                className={`relative flex h-full w-full flex-col items-center justify-center gap-1 text-[11px] font-medium ${
                  isActive ? 'text-petrol' : 'text-petrol-muted'
                }`}
              >
                {pathname === '/overview' && isActive && (
                  <span aria-hidden="true" className="absolute inset-x-3 top-0 h-0.5 bg-petrol" />
                )}
                <Icon size={22} aria-hidden="true" />
                {label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
