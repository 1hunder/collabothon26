import { Navigate, useLocation } from 'react-router-dom';
import { useCampaign, useHero } from '../api/campaign';
import { phaseToPath } from './phase';

/** `/quest`: decides where the player goes from the hero and the active campaign. */
export default function QuestEntry(): React.ReactNode {
  const location = useLocation();
  const hero = useHero();
  const activeId = hero.data?.active_campaign_id ?? null;
  const campaign = useCampaign(activeId);

  if (hero.isError || campaign.isError) return <p role="alert">Could not load your quest. Please try again.</p>;
  if (hero.isPending || (activeId !== null && campaign.isPending)) return <p role="status">Loading…</p>;

  const go = (to: string): React.ReactNode => <Navigate to={to} replace state={location.state} />;
  if (hero.data === null) return go('/quest/hero/new');
  if (campaign.data) return go(phaseToPath(campaign.data.phase));
  return go('/quest/interests');
}
