import { Heart, Sparkles } from 'lucide-react';
import type { CampaignState } from '../../api/types';

const className = { guardian: 'the Guardian', analyst: 'the Analyst', investigator: 'the Investigator' } as const;

interface HeroStatusProps {
  campaign: CampaignState;
  onOpen?: () => void;
}

/** Compact status bar. Every number is shown exactly as the server sent it. */
export default function HeroStatus({ campaign, onOpen }: HeroStatusProps): React.JSX.Element {
  const { hero } = campaign;
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label="Hero status"
      className="flex min-h-11 w-full flex-col items-start gap-0.5 pr-12 text-left font-quest-sans text-[15px] text-quest-vellum"
    >
      <span className="font-quest text-[17px] italic">
        <b className="not-italic">{hero.name}</b>, {className[hero.class]}
      </span>
      <span className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
        <span className="inline-flex items-center gap-1 text-quest-gilt">
          <Heart aria-hidden="true" size={15} />
          {campaign.hp} HP <span className="text-quest-vellum-dim">· €{campaign.hp_eur.toLocaleString('en-US')}</span>
        </span>
        <span>XP {hero.total_xp}</span>
        <span className="inline-flex items-center gap-1">
          <Sparkles aria-hidden="true" size={15} />
          Focus: {campaign.focus_left}
        </span>
        {hero.class === 'analyst' ? <span>Rerolls: {campaign.rerolls_left}</span> : null}
        {hero.class === 'investigator' ? <span>Keen Eye: {campaign.keen_eye_left}</span> : null}
      </span>
    </button>
  );
}
