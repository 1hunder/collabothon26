import { lazy, Suspense, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { patchCampaignCache, streamDebrief, useOutcome } from '../../api/campaign';
import { formatEur, formatPct, formatSigned } from '../lib/commit';
import ScreenBuddy from '../play/ScreenBuddy';
import { useActiveCampaign } from '../lib/useActiveCampaign';

const StoryChart = lazy(() => import('../components/StoryChart'));

/** `/quest/outcome`: every figure comes from GET /campaigns/{id}/reveal, shown as received. */
export default function Outcome(): React.JSX.Element {
  const { id } = useActiveCampaign();
  if (id === null) return <p role="status">Loading…</p>;
  return <OutcomeView id={id} />;
}

function OutcomeView({ id }: { id: string }): React.JSX.Element {
  const outcome = useOutcome(id);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  if (outcome.isError) return <p role="alert">Could not load your result. Please try again.</p>;
  if (!outcome.data) return <p role="status">Loading…</p>;
  const o = outcome.data;
  const b = o.breakdown;

  const toDebrief = async (): Promise<void> => {
    setBusy(true);
    setFailed(false);
    try {
      const debrief = await streamDebrief(id);
      patchCampaignCache(qc, id, { phase: 'debrief', debrief });
      void navigate('/quest/debrief', { replace: true });
    } catch {
      setFailed(true);
      setBusy(false);
    }
  };

  const rows: [string, string][] = [
    ['Starting budget', formatEur(b.starting_budget)],
    ['Cash kept', formatEur(b.cash_kept)],
    ['Invested', formatEur(b.invested)],
    ['Value now', formatEur(b.value_now)],
    ['Fees', formatEur(b.fees)],
    ['Final value', formatEur(b.final_value)],
    ['Profit / loss', `${formatSigned(b.pl_eur)} (${formatPct(b.pl_pct)})`],
  ];

  return (
    <div className="space-y-5 pb-8">
      <ScreenBuddy campaignId={id} screen="outcome" />
      <h1 className="font-quest-title text-4xl text-quest-gilt">The outcome</h1>
      <p className="font-quest-sans text-quest-vellum-dim">
        Locked at {o.locked_at} · horizon {o.horizon_days} days
      </p>
      <Suspense fallback={<div className="h-60" aria-busy="true" />}>
        <StoryChart mode="story" points={o.series} markers={[{ at: o.decision_day, label: 'Locked' }]} />
      </Suspense>
      <dl className="divide-y divide-quest-lapis font-quest-sans">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between py-2">
            <dt className="text-quest-vellum-dim">{k}</dt>
            <dd className="font-bold">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="font-quest-title text-3xl text-quest-gilt">
        {o.hp_before} HP → {o.hp_after} HP
      </p>
      <p className="font-quest-sans text-sm text-quest-vellum-dim">{o.currency_note}</p>
      {failed ? (
        <p role="alert" className="font-quest-sans text-sm text-quest-wax-light">
          Could not prepare the debrief. Please try again.
        </p>
      ) : null}
      <button
        type="button"
        disabled={busy}
        onClick={() => void toDebrief()}
        className="min-h-11 w-full rounded-md border border-quest-gilt/70 bg-quest-lapis-deep px-5 font-quest-sans text-lg font-bold disabled:opacity-40"
      >
        {busy ? 'Preparing the debrief…' : 'See the debrief'}
      </button>
    </div>
  );
}
