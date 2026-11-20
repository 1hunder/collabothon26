import { ArrowLeft } from 'lucide-react';
import { useMatches, useNavigate, useLocation } from 'react-router-dom';
import Logo from './Logo';
import { isShellRouteHandle, type ShellRouteHandle } from './routeHandle';

export default function TopBar(): React.JSX.Element {
  const matches = useMatches();
  const navigate = useNavigate();
  const location = useLocation();
  const handle: ShellRouteHandle = matches.reduce<ShellRouteHandle>(
    (acc, m) => (isShellRouteHandle(m.handle) ? { ...acc, ...m.handle } : acc),
    {},
  );

  const goBack = (): void => {
    if (location.key === 'default') navigate('/overview', { replace: true });
    else navigate(-1);
  };

  return (
    <header className="sticky top-0 z-40 flex min-h-14 items-center gap-2 border-b border-line bg-white px-4 pt-[env(safe-area-inset-top)]">
      {handle.back ? (
        <button type="button" aria-label="Back" onClick={goBack} className="-ml-2 p-2 text-petrol">
          <ArrowLeft size={22} aria-hidden="true" />
        </button>
      ) : null}
      {handle.title ? (
        <h1 className="text-lg font-bold text-petrol">{handle.title}</h1>
      ) : (
        <Logo />
      )}
    </header>
  );
}
