import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { fetchXp, patchCampaignCache, useCampaign, useHero } from '../../api/campaign';
import RevealGuard from '../RevealGuard';
import { useQuestMeta } from '../questStore';
import Reveal from './Reveal';

/** `/quest/reveal`: spec 002's company reveal for the campaign's scenario, then on to XP. */
export default function RevealRoute(): React.ReactNode {
  const meta = useQuestMeta();
  const hero = useHero();
  const campaignId = hero.data?.active_campaign_id ?? null;
  const campaign = useCampaign(campaignId);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const scenarioId = meta.scenarioId ?? campaign.data?.scenario_id ?? null;
  if (scenarioId === null) return <p role="status">Loading…</p>;

  const next = async (): Promise<void> => {
    if (campaignId === null) return;
    setBusy(true);
    setFailed(false);
    try {
      const xp = await fetchXp(campaignId);
      patchCampaignCache(qc, campaignId, { phase: 'xp', xp });
      void navigate('/quest/xp', { replace: true });
    } catch {
      setFailed(true);
      setBusy(false);
    }
  };

  return (
    <RevealGuard scenarioId={scenarioId} fallbackPath="/quest">
      {(data) => (
        <div className="bg-quest-soot pb-8">
          <Reveal data={data} />
          <div className="px-4">
            {failed ? (
              <p role="alert" className="mb-2 font-quest-sans text-sm text-quest-wax-light">
                Could not score your reasoning. Please try again.
              </p>
            ) : null}
            <button
              type="button"
              disabled={busy}
              onClick={() => void next()}
              className="min-h-11 w-full rounded-md border border-quest-gilt/70 bg-quest-lapis-deep px-5 font-quest-sans text-lg font-bold text-quest-vellum disabled:opacity-40"
            >
              Continue to XP
            </button>
          </div>
        </div>
      )}
    </RevealGuard>
  );
}
