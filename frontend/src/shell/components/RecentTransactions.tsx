import { useContext } from 'react';
import { QueryClientContext } from '@tanstack/react-query';
import { ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import { useTransactions } from '../../api/personal';
import { formatEur } from '../lib/money';

const SHOWN = 6;

function List(): React.JSX.Element | null {
  const { data } = useTransactions();
  if (!data || data.length === 0) return null;
  return (
    <section aria-labelledby="recent-tx" className="rounded-xl border border-[#e0e7e9] bg-white px-4 text-petrol">
      <h2 id="recent-tx" className="pb-1 pt-4 text-lg font-semibold">
        Recent transactions
      </h2>
      <ul className="divide-y divide-[#e0e7e9]">
        {data.slice(0, SHOWN).map((t, i) => {
          const amount = Number(t.amount_eur);
          const Direction = amount < 0 ? ArrowUpRight : ArrowDownLeft;
          return (
            <li key={`${t.date}-${t.merchant}-${i}`} className="flex items-center gap-3 py-3 text-sm">
              <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-[#edf2f3]">
                <Direction aria-hidden="true" size={18} />
              </span>
              <span className="min-w-0 grow break-words">
                <span className="font-semibold">{t.merchant}</span>
                <span className="mt-0.5 block text-xs leading-4 text-petrol-muted">
                  {t.category_label} · {t.date}
                </span>
              </span>
              <span className={`shrink-0 font-semibold tabular-nums ${amount < 0 ? '' : 'text-green-700'}`}>{formatEur(amount)}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Lena's (mock) spending, which the personal quests are built from. Needs a QueryClient. */
export default function RecentTransactions(): React.JSX.Element | null {
  return useContext(QueryClientContext) ? <List /> : null;
}
