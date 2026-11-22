import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys, useCreateCampaign } from '../../api/campaign';
import { ApiError } from '../../api/client';
import type { CampaignState, Hero } from '../../api/types';

/** Starts the campaign for the quest picked on the Quest Board (`state.scenarioId`). */
export default function QuestDisclosure(): React.JSX.Element {
  const qc = useQueryClient();
  const { mutateAsync: createCampaign } = useCreateCampaign();
  const scenarioId = (useLocation().state as { scenarioId?: string } | null)?.scenarioId;
  const started = useRef(false);
  const [failed, setFailed] = useState(false);

  const start = useCallback(async (): Promise<void> => {
    setFailed(false);
    try {
      const campaign: CampaignState = await createCampaign(scenarioId ? { scenario_id: scenarioId } : {});
      qc.setQueryData<Hero | null>(queryKeys.hero, (h) => (h ? { ...h, active_campaign_id: campaign.id } : h));
    } catch (e: unknown) {
      if (e instanceof ApiError && e.code === 'campaign_in_progress' && e.campaignId) {
        await qc.invalidateQueries({ queryKey: queryKeys.hero });
        return;
      }
      setFailed(true);
    }
  }, [createCampaign, qc, scenarioId]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void start();
  }, [start]);

  // PhaseGuard opens the active campaign as soon as the hero cache is updated.
  return failed ? (
    <div>
      <p role="alert">Could not start this quest. Please try again.</p>
      <button type="button" className="class-continue" onClick={() => void start()}>Try again</button>
    </div>
  ) : <p role="status">Starting your quest…</p>;
}
