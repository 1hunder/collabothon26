import type { WhatIfRow } from '../../api/types';
import { formatPct } from '../lib/commit';
import { formatGold } from '../lib/gold';

/** Rewind view: server-computed rows; the player's own choice is highlighted. */
export default function WhatIfPanel({ rows }: { rows: WhatIfRow[] }): React.JSX.Element {
  return (
    <section aria-labelledby="whatif-h" className="rounded-lg border border-quest-lapis bg-quest-lapis-deep p-3">
      <h2 id="whatif-h" className="font-quest-title text-2xl text-quest-gilt">
        What if…
      </h2>
      <ul className="mt-2 space-y-2 font-quest-sans">
        {rows.map((r) => (
          <li
            key={r.key}
            aria-current={r.is_yours ? 'true' : undefined}
            className={`flex justify-between rounded-md px-3 py-2 ${
              r.is_yours ? 'border-2 border-quest-gilt bg-quest-lapis' : 'border border-quest-lapis'
            }`}
          >
            <span>
              {r.label}
              {r.is_yours ? ' (your choice)' : ''}
            </span>
            <span>
              {formatGold(r.final_value)} · {formatPct(r.pct)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
