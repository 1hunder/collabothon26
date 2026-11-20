import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { RevealData } from '../api/types';

interface RevealGuardProps {
  scenarioId: string;
  /** Where to send the player when the server says the reveal is still locked. */
  fallbackPath: string;
  children: (data: RevealData) => React.ReactNode;
}

type State =
  | { status: 'loading' }
  | { status: 'locked' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: RevealData };

export default function RevealGuard({
  scenarioId,
  fallbackPath,
  children,
}: RevealGuardProps): React.ReactNode {
  const [state, setState] = useState<State>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    api
      .reveal(scenarioId)
      .then((data) => {
        if (!cancelled) setState({ status: 'ready', data });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.kind === 'RevealLocked') setState({ status: 'locked' });
        else setState({ status: 'error', message: e instanceof Error ? e.message : 'Error' });
      });
    return () => {
      cancelled = true;
    };
  }, [scenarioId]);

  switch (state.status) {
    case 'loading':
      return <p role="status">Loading…</p>;
    case 'locked':
      return <Navigate to={fallbackPath} replace />;
    case 'error':
      return <p role="alert">{state.message}</p>;
    case 'ready':
      return children(state.data);
  }
}
