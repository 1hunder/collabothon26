import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys, useCreateCampaign } from '../../api/campaign';
import { ApiError } from '../../api/client';
import type { CampaignState, Hero } from '../../api/types';
import { getQuestPick, interestFor, setQuestPick } from '../selectedQuest';

export default function QuestDisclosure(): React.JSX.Element {
  const qc = useQueryClient();
  const { mutateAsync: createCampaign } = useCreateCampaign();
  const started = useRef(false);
  const [failed, setFailed] = useState(false);
  // A personal quest chosen on the Finance Quest card (today's or an extra one), if any.
  const [questPick] = useState(getQuestPick);

  const start = useCallback(async (): Promise<void> => {
    setFailed(false);
    try {
      const pickedInterest = questPick ? interestFor(questPick.category) : null;
      const interests = pickedInterest ? [pickedInterest] : [];
      let campaign: CampaignState;
      try {
        campaign = await createCampaign(
          questPick ? { interests, scenario_id: questPick.scenarioId } : { interests },
        );
      } catch (e: unknown) {
        // The picked personal quest is gone (retired, or another player's): play the default one.
        if (!(questPick && e instanceof ApiError && e.status === 404)) throw e;
        campaign = await createCampaign({ interests });
      }
      setQuestPick(null);
      qc.setQueryData<Hero | null>(queryKeys.hero, (h) => (h ? { ...h, active_campaign_id: campaign.id } : h));
    } catch (e: unknown) {
      if (e instanceof ApiError && e.code === 'campaign_in_progress' && e.campaignId) {
        await qc.invalidateQueries({ queryKey: queryKeys.hero });
        return;
      }
      setFailed(true);
    }
  }, [createCampaign, qc, questPick]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void start();
  }, [start]);

  // PhaseGuard opens the active campaign as soon as the hero cache is updated.
  return failed ? (
    <div>
      <p role="alert">Could not find a quest. Please try again.</p>
      <button type="button" className="class-continue" onClick={() => void start()}>Try again</button>
    </div>
  ) : <p role="status">Starting your quest…</p>;
}
