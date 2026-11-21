import { abandonCampaign, fetchHero, queryKeys } from '../api/campaign';
import { queryClient } from '../api/queryClient';
import { clearPlayDrafts } from './play/useSessionDraft';

/**
 * Abandon the server's active campaign (if any) so the next `/quest` entry starts a new one.
 * Without this, the quest entry resumes the old campaign instead of the newly picked quest.
 */
export async function endActiveQuest(): Promise<void> {
  const active = (await fetchHero())?.active_campaign_id ?? null;
  if (active !== null) {
    await abandonCampaign(active);
    queryClient.removeQueries({ queryKey: queryKeys.campaign(active) });
  }
  queryClient.removeQueries({ queryKey: queryKeys.hero });
  clearPlayDrafts();
}
