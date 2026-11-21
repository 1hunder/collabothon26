import { Coins, Heart, Sparkles } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { CampaignState } from '../../api/types';
import { formatGold } from '../lib/gold';

const className = { guardian: 'the Guardian', analyst: 'the Analyst', investigator: 'the Investigator' } as const;

function reducedMotion(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Counts down to the target one step at a time (instantly with reduced motion). Only falls; never invents a number. */
function useTickedDown(target: number): number {
  const [shown, setShown] = useState(target);
  const value = shown < target || reducedMotion() ? target : shown;
  useEffect(() => {
    if (shown <= target) return;
    const t = window.setTimeout(() => setShown((n) => Math.max(target, n - Math.max(1, Math.ceil((n - target) / 6)))), 70);
    return () => window.clearTimeout(t);
  }, [shown, target]);
  return value;
}

interface HeroStatusProps {
  campaign: CampaignState;
  /** Changes every time the hero takes damage: replays the red pulse and shake. */
  hitKey?: number;
  onOpen?: () => void;
}

/** Compact status bar. Every number is shown exactly as the server sent it. */
export default function HeroStatus({ campaign, hitKey = 0, onOpen }: HeroStatusProps): React.JSX.Element {
  const { hero } = campaign;
  const hp = useTickedDown(campaign.hp);
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label="Hero status"
      className="flex min-h-11 w-full flex-col items-start gap-0.5 pr-12 text-left font-quest-sans text-[15px] text-quest-vellum"
    >
      <span className="text-[17px]">
        <span>{hero.name}</span>, {className[hero.class]}
      </span>
      <span className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
        <span
          key={hitKey}
          data-testid="hp"
          data-hit={hitKey > 0 ? 'true' : undefined}
          className={`inline-flex items-center gap-1 text-quest-gilt ${hitKey > 0 ? 'motion-safe:animate-hp-hit' : ''}`}
        >
          <Heart aria-hidden="true" size={15} />
          {hp} HP <span>· {formatGold(campaign.hp_eur)}</span>
        </span>
        <span>XP {hero.total_xp}</span>
        <span className="inline-flex items-center gap-1">
          <Sparkles aria-hidden="true" size={15} />
          Focus: {campaign.focus_left}
        </span>
        {hero.class === 'analyst' ? <span>Rerolls: {campaign.rerolls_left}</span> : null}
        {hero.class === 'investigator' ? <span>Keen Eye: {campaign.keen_eye_left}</span> : null}
      </span>
      {campaign.purse && campaign.purse.position_eur > 0 ? (
        <span className="inline-flex items-center gap-1 text-quest-vellum-dim">
          <Coins aria-hidden="true" size={15} />
          Cash {formatGold(campaign.purse.cash_eur)} · In the company {formatGold(campaign.purse.position_eur)}
        </span>
      ) : null}
    </button>
  );
}
