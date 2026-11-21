import { useState } from 'react';
import { Compass } from 'lucide-react';
import { startQuest, useQuestMeta } from '../../quest/questStore';
import { HERO_CLASS_PATH } from '../../quest/setupNavigation';
import { unlockVoice } from '../../voice';
import NewGameDialog from './NewGameDialog';

interface QuestCardProps {
  variant: 'overview' | 'depot';
  onStart: (path: string) => void;
  onContinue: (resumePath: string) => void;
  /** Extra content under the subtitle (the overview shows today's personal quest here). */
  children?: React.ReactNode;
}

export default function QuestCard({
  variant,
  onStart,
  onContinue,
  children,
}: QuestCardProps): React.JSX.Element | null {
  const { inProgress, resumePath } = useQuestMeta();
  const [confirming, setConfirming] = useState(false);
  const handleClick = (): void => {
    unlockVoice();
    if (inProgress) {
      onContinue(resumePath);
      return;
    }
    startQuest();
    onStart('/quest');
  };
  const buttons = (
    <div className="flex flex-wrap gap-3">
      <button
        type="button"
        onClick={handleClick}
        className={`min-h-11 rounded-pill px-6 py-2 text-sm font-semibold ${variant === 'overview' ? 'bg-brand-yellow text-petrol hover:bg-brand-yellowHover' : 'bg-petrol text-white'}`}
      >
        {inProgress ? 'Continue' : variant === 'depot' ? 'Start your first quest' : 'Start'}
      </button>
      {inProgress && (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="min-h-11 rounded-pill border border-petrol px-6 py-2 text-sm font-semibold"
        >
          New Game
        </button>
      )}
      {confirming && (
        <NewGameDialog
          onCancel={() => setConfirming(false)}
          onStart={() => {
            setConfirming(false);
            onStart(HERO_CLASS_PATH);
          }}
        />
      )}
    </div>
  );

  if (variant === 'depot') {
    return (
      <section className="flex w-full flex-col gap-3 rounded-card bg-brand-yellow p-4 text-petrol">
        <h2 className="text-xl font-semibold">Practise before you invest</h2>
        {inProgress && <p className="text-sm">Quest in progress</p>}
        {buttons}
      </section>
    );
  }
  return (
    <section className="w-full rounded-xl border border-[#e0e7e9] bg-white p-4 text-petrol" aria-labelledby="overview-quest-title">
      <div className="flex items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-petrol text-brand-yellow">
          <Compass aria-hidden="true" size={22} strokeWidth={1.75} />
        </span>
        <h2 id="overview-quest-title" className="grow text-lg font-semibold leading-tight">Finance Quest</h2>
        <span className="rounded-pill bg-[#fff1a5] px-2.5 py-1 text-xs font-semibold">New</span>
      </div>
      <p className="mt-3 text-sm leading-5 text-petrol-muted">Learn to invest with real market history — risk-free</p>
      {inProgress && <p className="mt-1 text-sm font-semibold">Quest in progress</p>}
      {children}
      <div className="mt-4">{buttons}</div>
    </section>
  );
}
