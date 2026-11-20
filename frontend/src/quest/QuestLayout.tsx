import { X } from 'lucide-react';
import { Outlet, useBlocker, useLocation, useNavigate } from 'react-router-dom';
import LeaveDialog from './LeaveDialog';

function isQuestPath(pathname: string): boolean {
  return pathname === '/quest' || pathname.startsWith('/quest/');
}

interface OriginState {
  origin?: string;
}

export default function QuestLayout(): React.JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isQuestPath(currentLocation.pathname) && !isQuestPath(nextLocation.pathname),
  );

  const close = (): void => {
    if (location.key === 'default') {
      const origin = (location.state as OriginState | null)?.origin ?? '/overview';
      void navigate(origin, { replace: true });
    } else {
      void navigate(-1);
    }
  };

  return (
    <div className="relative min-h-dvh bg-warm px-4 pb-[env(safe-area-inset-bottom)] pt-[calc(1rem+env(safe-area-inset-top))]">
      <button
        type="button"
        aria-label="Close quest"
        onClick={close}
        className="absolute right-3 top-[calc(0.75rem+env(safe-area-inset-top))] flex h-11 w-11 items-center justify-center rounded-full"
      >
        <X aria-hidden="true" size={24} />
      </button>
      <main className="pt-10">
        <Outlet />
      </main>
      {blocker.state === 'blocked' ? (
        <LeaveDialog onLeave={() => blocker.proceed()} onStay={() => blocker.reset()} />
      ) : null}
    </div>
  );
}
