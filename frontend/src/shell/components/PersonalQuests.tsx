import { useContext, useEffect, useState } from 'react';
import { QueryClientContext } from '@tanstack/react-query';
import {
  isActive,
  useDailyQuest,
  useExtraQuests,
  useGenerateQuest,
  useRegenerateDaily,
} from '../../api/personal';
import type { QuestJob } from '../../api/types';
import { setQuestPick } from '../../quest/selectedQuest';
import { endActiveQuest } from '../../quest/endActiveQuest';

interface PersonalQuestsProps {
  /** A quest is in progress: new quests can be prepared but not started. */
  busy: boolean;
  /** Start the quest picked from the list (the card's own button starts today's quest). */
  onPlay: () => void;
}

function pickOf(job: QuestJob): Parameters<typeof setQuestPick>[0] {
  return job.scenario_id
    ? { scenarioId: job.scenario_id, category: job.category, categoryLabel: job.category_label }
    : null;
}

function statusLine(job: QuestJob): string {
  if (job.status === 'ready') return 'Ready';
  if (isActive(job)) return `${job.step}…`;
  return 'Could not be prepared';
}

function Spinner(): React.JSX.Element {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-petrol border-t-transparent motion-reduce:animate-none"
    />
  );
}

function Panel({ busy, onPlay }: PersonalQuestsProps): React.JSX.Element {
  const daily = useDailyQuest();
  const extras = useExtraQuests();
  const generate = useGenerateQuest();
  const regenerate = useRegenerateDaily();
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [switchFailed, setSwitchFailed] = useState(false);
  const today = daily.data;

  // The card's Start button plays today's quest once it is ready; until then, the default quest.
  useEffect(() => {
    if (busy) return;
    setQuestPick(today && today.status === 'ready' ? pickOf(today) : null);
  }, [busy, today]);

  return (
    <div className="mt-3 space-y-2 text-sm" aria-live="polite">
      {today ? (
        <p>
          <span className="font-semibold">Today&apos;s quest:</span> {today.category_label}
          <span className="block text-xs">
            {isActive(today) ? <Spinner /> : null} {statusLine(today)}
            {today.status === 'ready' ? ' · picked from your spending' : ''}
          </span>
        </p>
      ) : daily.isError ? (
        <p className="text-xs">Personal quests are unavailable right now.</p>
      ) : (
        <p className="text-xs">
          <Spinner /> Preparing today&apos;s quest…
        </p>
      )}

      {extras.data && extras.data.length > 0 ? (
        <ul className="space-y-1" aria-label="More quests">
          {extras.data.map((job) => (
            <li key={job.id} className="flex items-center justify-between gap-2 rounded-md bg-white/60 px-2 py-1">
              <span>
                {job.category_label}
                <span className="block text-xs">
                  {isActive(job) ? <Spinner /> : null} {statusLine(job)}
                </span>
              </span>
              {job.status === 'ready' && confirmId === job.id ? (
                <span className="flex items-center gap-1">
                  <button
                    type="button"
                    disabled={switching}
                    onClick={() => {
                      setSwitching(true);
                      setSwitchFailed(false);
                      endActiveQuest()
                        .then(() => {
                          setConfirmId(null);
                          setQuestPick(pickOf(job));
                          onPlay();
                        })
                        .catch(() => setSwitchFailed(true))
                        .finally(() => setSwitching(false));
                    }}
                    className="rounded-pill bg-petrol px-3 py-1 text-xs font-semibold text-white disabled:opacity-50"
                  >
                    End current and play
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmId(null)}
                    className="px-1 text-xs font-semibold underline"
                  >
                    Cancel
                  </button>
                </span>
              ) : job.status === 'ready' ? (
                <button
                  type="button"
                  onClick={() => {
                    if (busy) {
                      setConfirmId(job.id); // a quest is in progress: confirm before replacing it
                      return;
                    }
                    setQuestPick(pickOf(job));
                    onPlay();
                  }}
                  className="rounded-pill bg-petrol px-3 py-1 text-xs font-semibold text-white"
                >
                  Play
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      {today && !isActive(today) && !busy ? (
        <button
          type="button"
          disabled={regenerate.isPending}
          onClick={() => regenerate.mutate()}
          className="mr-3 text-xs font-semibold underline disabled:opacity-50"
        >
          Regenerate today&apos;s quest
        </button>
      ) : null}
      <button
        type="button"
        disabled={generate.isPending}
        onClick={() => generate.mutate()}
        className="text-xs font-semibold underline disabled:opacity-50"
      >
        Generate another quest
      </button>
      {switchFailed ? <p className="text-xs">Could not end your current quest. Try again.</p> : null}
      {regenerate.isError ? <p className="text-xs">Could not regenerate. Try again.</p> : null}
      {generate.isError ? <p className="text-xs">Could not start a new quest. Try again.</p> : null}
    </div>
  );
}

/** Today's personal quest and any extra ones, built from the player's spending. */
export default function PersonalQuests(props: PersonalQuestsProps): React.JSX.Element | null {
  return useContext(QueryClientContext) ? <Panel {...props} /> : null;
}
