import type { BacklogEntry } from '../../api/types';
import Sheet from './Sheet';

interface BacklogProps {
  entries: readonly BacklogEntry[];
  onClose: () => void;
}

/** Everything said in this campaign, oldest first. */
export default function Backlog({ entries, onClose }: BacklogProps): React.JSX.Element {
  return (
    <Sheet title="Backlog" subtitle="Everything said so far" onClose={onClose}>
      {entries.length === 0 ? (
        <p className="font-quest text-base">Nothing has been said yet.</p>
      ) : (
        <ol className="space-y-3">
          {entries.map((e) => (
            <li key={e.seq} className="font-quest text-base leading-snug">
              <b className="block font-quest-sans text-sm text-quest-lapis">{e.speaker}</b>
              {e.text}
            </li>
          ))}
        </ol>
      )}
    </Sheet>
  );
}
