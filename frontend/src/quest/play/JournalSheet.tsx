import { useQuery } from '@tanstack/react-query';
import { Lightbulb } from 'lucide-react';
import { request } from '../../api/client';
import type { JournalEntry } from '../../api/types';
import { useVeteran } from '../../api/veteran';
import Sheet from './Sheet';

interface JournalSheetProps {
  campaignId: string;
  onBacklog: () => void;
  onClose: () => void;
}

const text = (v: unknown): string => (typeof v === 'string' ? v : '');
const num = (v: unknown): string => (typeof v === 'number' ? String(v) : '');

function Entry({ e }: { e: JournalEntry }): React.JSX.Element | null {
  switch (e.type) {
    case 'move':
      return <li>Visited <b>{text(e.name)}</b></li>;
    case 'action':
      return <li>You: {text(e.text)}</li>;
    case 'dice_roll':
      return (
        <li>
          Dice check, {text(e.title)}: {num(e.used)} + {num(e.bonus)} = {num(e.total)} against {num(e.dc)}.{' '}
          <b>{e.result === 'success' ? 'Success' : 'Setback'}</b>
        </li>
      );
    case 'clue_found':
      return (
        <li className="flex gap-2">
          <Lightbulb aria-label="Clue" size={18} className="mt-0.5 shrink-0 text-quest-gilt" />
          <span>
            <b>{text(e.title)}</b>. {text(e.text)}
          </span>
        </li>
      );
    case 'buddy_q':
      return <li>You asked CommerzBuddy: {text(e.text)}</li>;
    case 'buddy_a':
      return <li>CommerzBuddy: {text(e.text)}</li>;
    case 'news':
      return (
        <li className="flex gap-2">
          <Lightbulb aria-label="Clue" size={18} className="mt-0.5 shrink-0 text-quest-gilt" />
          <span>
            Breaking news: <b>{text(e.headline)}</b>
          </span>
        </li>
      );
    case 'focus_spend':
      return <li>Spent 1 Focus ({e.kind === 'hint' ? 'a hint' : 'a bonus lead'})</li>;
    default:
      return null;
  }
}

export default function JournalSheet({ campaignId, onBacklog, onClose }: JournalSheetProps): React.JSX.Element {
  const journal = useQuery({
    queryKey: ['journal', campaignId],
    queryFn: () => request<{ entries: JournalEntry[] }>('GET', `/campaigns/${campaignId}/journal`),
    staleTime: 0,
  });
  const lessons = useVeteran().data?.lessons ?? [];
  return (
    <Sheet title="Journal" subtitle="In the order it happened" onClose={onClose}>
      <button type="button" onClick={onBacklog} className="mb-3 min-h-11 rounded-full bg-quest-lapis-deep px-4">
        Open the backlog
      </button>
      {lessons.length > 0 ? (
        <section aria-label="Lessons learned" className="mb-4 rounded-lg border border-quest-wax/30 bg-white/40 p-3">
          <h3 className="font-quest-title text-xl text-quest-wax">Lessons learned</h3>
          <ul className="mt-1 space-y-1.5 font-quest text-base leading-snug">
            {lessons.map((l) => (
              <li key={l.id}>
                {l.text}
                {l.quest_title ? <span className="block font-quest-sans text-[12px] text-[#6E5C43]">from {l.quest_title}, kept with Brannoc</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {journal.isPending ? <p role="status" className="font-quest">Loading…</p> : null}
      {journal.isError ? <p role="alert" className="font-quest">Could not load the journal.</p> : null}
      {journal.data && journal.data.entries.length === 0 ? <p className="font-quest">Nothing yet. Your story starts here.</p> : null}
      {journal.data && journal.data.entries.length > 0 ? (
        <ol className="space-y-2.5 font-quest text-base leading-snug">
          {journal.data.entries.map((e) => (
            <Entry key={e.seq} e={e} />
          ))}
        </ol>
      ) : null}
    </Sheet>
  );
}
