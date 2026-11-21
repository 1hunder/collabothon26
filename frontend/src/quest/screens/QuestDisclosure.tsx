import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys, useCreateCampaign } from '../../api/campaign';
import { ApiError } from '../../api/client';
import type { CampaignState, Hero } from '../../api/types';
import DisclosureNote from '../components/DisclosureNote';
import { unlockVoice } from '../../voice';
import { markDisclosureSeen } from '../questStore';
import { getQuestPick, interestFor, setQuestPick } from '../selectedQuest';

export default function QuestDisclosure(): React.JSX.Element {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const createCampaign = useCreateCampaign();
  const [failed, setFailed] = useState(false);
  // A personal quest chosen on the Finance Quest card (today's or an extra one), if any.
  const [questPick] = useState(getQuestPick);

  const gotIt = async (): Promise<void> => {
    unlockVoice();
    setFailed(false);
    try {
      const pickedInterest = questPick ? interestFor(questPick.category) : null;
      const interests = pickedInterest ? [pickedInterest] : [];
      let campaign: CampaignState;
      try {
        campaign = await createCampaign.mutateAsync(
          questPick ? { interests, scenario_id: questPick.scenarioId } : { interests },
        );
      } catch (e: unknown) {
        // The picked personal quest is gone (retired, or another player's): play the default one.
        if (!(questPick && e instanceof ApiError && e.status === 404)) throw e;
        campaign = await createCampaign.mutateAsync({ interests });
      }
      setQuestPick(null);
      markDisclosureSeen();
      qc.setQueryData<Hero | null>(queryKeys.hero, (h) => (h ? { ...h, active_campaign_id: campaign.id } : h));
      void navigate('/quest/play', { replace: true });
    } catch (e: unknown) {
      if (e instanceof ApiError && e.code === 'campaign_in_progress' && e.campaignId) {
        await qc.invalidateQueries({ queryKey: queryKeys.hero });
        void navigate('/quest', { replace: true });
        return;
      }
      setFailed(true);
    }
  };

  return (
    <>
      {questPick ? (
        <p className="font-quest-sans text-quest-vellum-dim">
          Your quest is ready: {questPick.categoryLabel}, picked from your spending.
        </p>
      ) : null}
      <DisclosureNote onDismiss={() => void gotIt()} pending={createCampaign.isPending} />
      {failed && <p role="alert">Could not find a quest. Please try again.</p>}
    </>
  );
}
