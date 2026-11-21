import { useContext } from 'react';
import { QueryClientContext } from '@tanstack/react-query';
import { useTransactions } from '../../api/personal';
import { formatEur } from '../lib/money';

const SHOWN = 6;

function List(): React.JSX.Element | null {
  const { data } = useTransactions();
  if (!data || data.length === 0) return null;
  return (
    <section aria-labelledby="recent-tx" className="rounded-card bg-white p-4 text-petrol">
      <h2 id="recent-tx" className="mb-2 text-base font-semibold">
        Recent transactions
      </h2>
      <ul className="divide-y divide-line">
        {data.slice(0, SHOWN).map((t, i) => {
          const amount = Number(t.amount_eur);
          return (
            <li key={`${t.date}-${t.merchant}-${i}`} className="flex items-center justify-between py-2 text-sm">
              <span>
                <span className="font-medium">{t.merchant}</span>
                <span className="block text-xs text-petrol-muted">
                  {t.category_label} · {t.date}
                </span>
              </span>
              <span className={amount < 0 ? '' : 'font-semibold text-green-700'}>{formatEur(amount)}</span>
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
