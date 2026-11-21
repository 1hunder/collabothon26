import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useCampaign, useHero } from '../api/campaign';
import { phaseToPath } from './phase';
import { saveProgress } from './questStore';

interface PhaseGuardProps {
  /** The route this screen lives at, or 'hero-new' for hero creation. */
  screen: string;
  children: React.ReactNode;
}

const HERO_NEW = '/quest/hero/new';

/**
 * Sends every screen to the route of the server's campaign phase (the server wins over a stale
 * lastPath). Redirects use `replace`.
 */
export default function PhaseGuard({ screen, children }: PhaseGuardProps): React.ReactNode {
  const location = useLocation();
  const hero = useHero();
  const activeId = hero.data?.active_campaign_id ?? null;
  const campaign = useCampaign(activeId);
  const here = screen === 'hero-new' ? HERO_NEW : screen;
  const allowed = hero.data !== undefined && (activeId === null || campaign.data !== undefined);

  useEffect(() => {
    if (allowed) saveProgress(location.pathname);
  }, [allowed, location.pathname]);

  if (hero.isError || campaign.isError) return <p role="alert">Could not load your quest. Please try again.</p>;
  if (hero.isPending || (activeId !== null && campaign.isPending)) return <p role="status">Loading…</p>;

  const go = (to: string): React.ReactNode => <Navigate to={to} replace state={location.state} />;
  if (hero.data === null) return here === HERO_NEW ? children : go(HERO_NEW);
  if (here === HERO_NEW) return go('/quest');
  if (campaign.data) {
    const target = phaseToPath(campaign.data.phase);
    // The server never stores `reflect`: the reflection screen is a client-only step of `debrief`.
    const reflecting = campaign.data.phase === 'debrief' && here === '/quest/reflect';
    return target === here || reflecting ? children : go(target);
  }
  return here === '/quest/interests' ? children : go('/quest/interests');
}
