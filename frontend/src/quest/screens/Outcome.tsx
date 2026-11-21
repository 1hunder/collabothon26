import { lazy, Suspense, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { patchCampaignCache, streamDebrief, useOutcome } from '../../api/campaign';
import { decisionLabel, formatEur, formatPct, formatSigned } from '../lib/commit';
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

  const decisions = o.decisions ?? [];
  const rows: [string, string][] = [
    ['Starting budget', formatEur(b.starting_budget)],
    ['Cash kept', formatEur(b.cash_kept)],
    ['Invested', formatEur(b.invested)],
    ['Value now', formatEur(b.value_now)],
    ['Fees', formatEur(b.fees)],
    ...(b.loan ? ([['Loan repayment', `−${formatEur(b.loan.repay_eur)} (${b.loan.lender})`]] as [string, string][]) : []),
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
        <StoryChart
          mode="story"
          points={o.series}
          markers={[
            ...decisions.filter((d) => d.story_day !== o.decision_day).map((d) => ({ at: d.story_day, label: `#${d.seq}` })),
            { at: o.decision_day, label: 'Locked' },
          ]}
        />
      </Suspense>
      {decisions.length > 0 ? (
        <section aria-label="Your decisions" className="space-y-2">
          <h2 className="font-quest-title text-2xl text-quest-gilt">Your decisions</h2>
          <ol className="space-y-2">
            {decisions.map((d) => (
              <li key={d.seq} className="rounded-md border border-quest-lapis bg-quest-lapis-deep p-3 font-quest-sans">
                <div className="flex justify-between gap-3">
                  <span>
                    <span className="text-quest-vellum-dim">#{d.seq} · {d.day_label} · </span>
                    <span className="font-bold">{decisionLabel(d)}</span>
                  </span>
                  {d.effect_eur !== undefined && d.action !== 'hold' ? (
                    <span className={d.effect_eur < 0 ? 'text-quest-wax-light' : 'text-quest-verdigris-light'}>
                      {formatSigned(d.effect_eur)}
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 font-quest italic text-quest-vellum-dim">&ldquo;{d.text}&rdquo;</p>
                {d.action !== 'loss' ? (
                  <p className="mt-1 font-quest-sans text-sm text-quest-vellum-dim" data-testid="decision-reasoning">
                    {d.reasoning ? <>Why: &ldquo;{d.reasoning}&rdquo;</> : 'No reason given'}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>
          <p className="font-quest-sans text-sm text-quest-vellum-dim">
            Each figure is what that decision did to your final result, compared with not making it.
          </p>
        </section>
      ) : null}
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
