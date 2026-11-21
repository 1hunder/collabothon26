import { useEffect, useId, useRef, useState } from 'react';
import { abandonCampaign, fetchHero, queryKeys } from '../../api/campaign';
import { queryClient } from '../../api/queryClient';
import { clearPlayDrafts } from '../../quest/play/useSessionDraft';
import { startQuest } from '../../quest/questStore';
import { HERO_CLASS_PATH } from '../../quest/setupNavigation';

interface NewGameDialogProps {
  onCancel: () => void;
  onStart: () => void;
}

export default function NewGameDialog({ onCancel, onStart }: NewGameDialogProps): React.JSX.Element {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const target = useRef<string | null | undefined>(undefined);
  const titleId = useId();
  const descriptionId = useId();
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  const confirm = async (): Promise<void> => {
    setPending(true);
    setFailed(false);
    try {
      if (target.current === undefined) {
        target.current = (await fetchHero())?.active_campaign_id ?? null;
      }
      if (target.current !== null) {
        await abandonCampaign(target.current);
        queryClient.removeQueries({ queryKey: queryKeys.campaign(target.current) });
      }
    } catch {
      setFailed(true);
      setPending(false);
      return;
    }
    queryClient.removeQueries({ queryKey: queryKeys.hero });
    clearPlayDrafts();
    startQuest(HERO_CLASS_PATH);
    onStart();
  };

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        event.preventDefault();
        if (!pending) onCancel();
      }}
      className="m-auto w-[calc(100%-2rem)] max-w-sm rounded-card bg-white p-5 text-petrol shadow-xl backdrop:bg-black/40"
    >
      <h2 id={titleId} className="text-lg font-semibold">Start a new game?</h2>
      <p id={descriptionId} className="mt-2 text-sm">
        Progress in your current quest will be lost. Your hero and completed quests will carry over.
      </p>
      {failed && <p role="alert" className="mt-3 text-sm">Could not start a new game. Please try again.</p>}
      <div className="mt-4 flex justify-end gap-3">
        <button
          type="button"
          onClick={onCancel}
          disabled={pending}
          className="min-h-11 rounded-pill border border-petrol px-4 text-sm font-semibold disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => void confirm()}
          disabled={pending}
          className="min-h-11 rounded-pill bg-petrol px-4 text-sm font-semibold text-white disabled:opacity-50"
        >
          {pending ? 'Starting…' : 'Start new game'}
        </button>
      </div>
    </dialog>
  );
}
