import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys, useCreateCampaign, useHero } from '../../api/campaign';
import type { CampaignState, Hero, Interest } from '../../api/types';
import DisclosureNote from '../components/DisclosureNote';
import { unlockVoice } from '../../voice';
import { markDisclosureSeen } from '../questStore';

const interests: readonly Interest[] = ['Gaming', 'Fashion', 'Sports', 'Mobility', 'Music', 'Tech'];

export default function WhatAreYouInto(): React.JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const hero = useHero();
  const createCampaign = useCreateCampaign();
  const [picked, setPicked] = useState<readonly Interest[]>([]);
  const [campaign, setCampaign] = useState<CampaignState | null>(null);
  const [failed, setFailed] = useState(false);
  const isNewHero = (location.state as { newHero?: boolean } | null)?.newHero === true;

  const toggle = (i: Interest): void =>
    setPicked((cur) => (cur.includes(i) ? cur.filter((x) => x !== i) : [...cur, i]));

  const find = async (): Promise<void> => {
    unlockVoice();
    setFailed(false);
    try {
      setCampaign(await createCampaign.mutateAsync({ interests: [...picked] }));
    } catch {
      setFailed(true);
    }
  };

  const gotIt = (): void => {
    if (campaign === null) return;
    markDisclosureSeen();
    // Record the active campaign locally so the phase guard on /quest/play lets us through.
    qc.setQueryData<Hero | null>(queryKeys.hero, (h) => (h ? { ...h, active_campaign_id: campaign.id } : h));
    void navigate('/quest/play', { replace: true });
  };

  if (campaign !== null) return <DisclosureNote onDismiss={gotIt} />;

  return (
    <div className="space-y-5 font-quest text-quest-vellum">
      {hero.data && !isNewHero ? (
        <p className="font-quest-sans text-quest-vellum-dim">Welcome back, {hero.data.name}</p>
      ) : null}
      <h1 className="font-quest-title text-4xl text-quest-gilt">What are you into?</h1>
      <div className="flex flex-wrap gap-3" role="group" aria-label="Interests">
        {interests.map((i) => {
          const on = picked.includes(i);
          return (
            <button
              key={i}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(i)}
              className={`min-h-11 rounded-full border-2 px-5 font-quest-sans text-lg ${
                on
                  ? 'border-quest-gilt bg-quest-verdigris text-quest-vellum'
                  : 'border-quest-lapis bg-quest-lapis-deep text-quest-vellum'
              }`}
            >
              {i}
            </button>
          );
        })}
      </div>
      {failed ? (
        <p role="alert" className="font-quest-sans text-sm text-quest-wax-light">
          Could not find a quest. Please try again.
        </p>
      ) : null}
      <button
        type="button"
        disabled={picked.length === 0 || createCampaign.isPending}
        onClick={() => void find()}
        className="min-h-11 w-full rounded-md bg-quest-verdigris px-5 font-quest-sans text-lg font-bold text-quest-vellum disabled:opacity-40"
      >
        Find my quest
      </button>
    </div>
  );
}
