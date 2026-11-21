import { useState } from 'react';
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
        className="min-h-11 rounded-pill bg-petrol px-6 py-2 text-sm font-semibold text-white"
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
    <section className="relative flex min-h-[200px] w-full flex-col justify-between rounded-card bg-brand-yellow p-4 text-petrol">
      <span className="absolute right-3 top-3 rounded-pill bg-petrol px-2 py-0.5 text-xs font-semibold text-white">
        New
      </span>
      <div className="pr-12">
        <h2 className="text-xl font-semibold">Finance Quest</h2>
        <p className="mt-1 text-sm">Learn to invest with real market history — risk-free</p>
        {inProgress && <p className="mt-1 text-sm font-semibold">Quest in progress</p>}
        {children}
      </div>
      <div className="mt-4">{buttons}</div>
    </section>
  );
}
