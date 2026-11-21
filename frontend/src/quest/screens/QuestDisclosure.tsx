import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys, useCreateCampaign } from '../../api/campaign';
import { ApiError } from '../../api/client';
import type { Hero } from '../../api/types';
import DisclosureNote from '../components/DisclosureNote';
import { unlockVoice } from '../../voice';
import { markDisclosureSeen } from '../questStore';

export default function QuestDisclosure(): React.JSX.Element {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const createCampaign = useCreateCampaign();
  const [failed, setFailed] = useState(false);

  const gotIt = async (): Promise<void> => {
    unlockVoice();
    setFailed(false);
    try {
      const campaign = await createCampaign.mutateAsync({ interests: [] });
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
      <DisclosureNote onDismiss={() => void gotIt()} pending={createCampaign.isPending} />
      {failed && <p role="alert">Could not find a quest. Please try again.</p>}
    </>
  );
}
