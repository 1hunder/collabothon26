import { useCampaign, useHero } from '../../api/campaign';

/** The hero's active campaign id and its cached state (null until loaded). */
export function useActiveCampaign(): { id: string | null; campaign: ReturnType<typeof useCampaign>['data'] } {
  const hero = useHero();
  const id = hero.data?.active_campaign_id ?? null;
  const q = useCampaign(id);
  return { id, campaign: q.data };
}
