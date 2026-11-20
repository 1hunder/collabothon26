import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useSession } from './lib/session';

export default function ShellGuard({ children }: { children: ReactNode }): React.JSX.Element {
  const { unlocked } = useSession();
  return unlocked ? <>{children}</> : <Navigate to="/" replace />;
}
