import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { lockDecision, patchCampaignCache, resumePlay, saveCommitDraft, useCampaign, useHero } from '../../api/campaign';
import type { CampaignState, CommitDraft, Confidence, DecisionAction } from '../../api/types';
import ScreenBuddy from '../play/ScreenBuddy';
import {
  actionLabels,
  emptyDraft,
  formatEur,
  isValidAmount,
  needsAmount,
  toRequest,
  validateCommit,
} from '../lib/commit';

const DRAFT_KEY = 'fq.commit.v1';
const SEAL_MS = 800;
const SKIP_MS = 1800;
const confidences: readonly Confidence[] = ['low', 'medium', 'high'];

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function readStored(campaignId: string): Partial<CommitDraft> | null {
  try {
    const raw = sessionStorage.getItem(`${DRAFT_KEY}.${campaignId}`);
    return raw ? (JSON.parse(raw) as Partial<CommitDraft>) : null;
  } catch {
    return null;
  }
}

function writeStored(campaignId: string, d: CommitDraft): void {
  try {
    sessionStorage.setItem(`${DRAFT_KEY}.${campaignId}`, JSON.stringify(d));
  } catch {
    // the server draft is the backup
  }
}

type Stage = 'form' | 'confirm' | 'sealing' | 'skip';

/** `/quest/commit`: the SealScroll. */
export default function Commit(): React.JSX.Element {
  const hero = useHero();
  const campaignId = hero.data?.active_campaign_id ?? null;
  const campaign = useCampaign(campaignId);
  if (!campaign.data) return <p role="status">Loading…</p>;
  return (
    <>
      <CommitForm campaign={campaign.data} />
      <ScreenBuddy campaignId={campaign.data.id} screen="commit" />
    </>
  );
}

function initialDraft(c: CampaignState): CommitDraft {
  return { ...emptyDraft, ...(readStored(c.id) ?? c.commit_draft ?? {}) };
}

function CommitForm({ campaign }: { campaign: CampaignState }): React.JSX.Element {
  const campaignId = campaign.id;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const budget = campaign.budget_eur ?? campaign.scenario?.budget_eur ?? campaign.hp_eur;
  const horizon = campaign.horizon_days ?? 0;
  const offersSpread = campaign.offers_spread === true;

  const [draft, setDraft] = useState<CommitDraft>(() => initialDraft(campaign));
  const [amountText, setAmountText] = useState(() => {
    const a = initialDraft(campaign).amount_eur;
    return typeof a === 'number' && !Number.isNaN(a) ? String(a) : '';
  });
  const [touched, setTouched] = useState({ amount: false, evidence: false });
  const [stage, setStage] = useState<Stage>('form');
  const [lockedHorizon, setLockedHorizon] = useState<number | null>(null);
  const [skipLabel, setSkipLabel] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    writeStored(campaignId, draft);
  }, [campaignId, draft]);

  const proceed = useCallback((): void => {
    patchCampaignCache(qc, campaignId, { phase: 'reveal' });
    void navigate('/quest/outcome', { replace: true });
  }, [qc, campaignId, navigate]);

  const set = (patch: Partial<CommitDraft>): void => setDraft((d) => ({ ...d, ...patch }));
  const errors = validateCommit(draft, budget, touched);
  const request = toRequest(draft, budget);
  const valid = request !== null;
  const choices: DecisionAction[] = offersSpread
    ? ['invest', 'spread', 'dont_invest', 'wait']
    : ['invest', 'dont_invest', 'wait'];

  const back = async (): Promise<void> => {
    try {
      await saveCommitDraft(campaignId, draft);
    } catch {
      // sessionStorage already holds the draft
    }
    try {
      await resumePlay(campaignId);
    } catch {
      // the server stays in commit; a reload would reopen the commit screen
    }
    patchCampaignCache(qc, campaignId, { phase: 'play' });
    void navigate('/quest/play', { replace: true });
  };

  const lock = async (): Promise<void> => {
    if (request === null) return;
    setFailed(false);
    setStage('sealing');
    try {
      const [res] = await Promise.all([
        lockDecision(campaignId, request),
        new Promise((r) => setTimeout(r, prefersReducedMotion() ? 0 : SEAL_MS)),
      ]);
      setLockedHorizon(res.horizon_days);
      setSkipLabel(res.time_skip_label ?? null);
      setStage('skip');
    } catch {
      setStage('form');
      setFailed(true);
    }
  };

  if (stage === 'sealing') {
    return (
      <div className="flex min-h-[60dvh] flex-col items-center justify-center gap-4" role="status">
        <div
          aria-hidden="true"
          className="flex h-28 w-28 items-center justify-center rounded-full bg-quest-wax font-quest-title text-4xl text-quest-vellum shadow-lg motion-safe:animate-seal-press"
        >
          FQ
        </div>
        <p className="font-quest-sans text-quest-vellum-dim">Sealing your decision…</p>
      </div>
    );
  }
  if (stage === 'skip') return <TimeSkip label={skipLabel ?? `${lockedHorizon ?? horizon} days later…`} onDone={proceed} />;

  return (
    <form
      className="space-y-5 pb-8"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) setStage('confirm');
      }}
    >
      <button
        type="button"
        onClick={() => void back()}
        className="min-h-11 font-quest-sans text-quest-vellum-dim underline"
      >
        Back to investigating
      </button>
      <h1 className="font-quest-title text-4xl text-quest-gilt">Seal your decision</h1>

      <fieldset className="space-y-2">
        <legend className="mb-1 font-quest-sans text-sm text-quest-vellum-dim">Decision</legend>
        <div role="radiogroup" aria-label="Decision" className="grid grid-cols-2 gap-2">
          {choices.map((a) => (
            <button
              key={a}
              type="button"
              role="radio"
              aria-checked={draft.action === a}
              onClick={() => set({ action: a, amount_eur: needsAmount(a) ? draft.amount_eur : null })}
              className={`min-h-11 rounded-md border-2 px-3 font-quest-sans ${
                draft.action === a ? 'border-quest-gilt bg-quest-verdigris' : 'border-quest-lapis bg-quest-lapis-deep'
              }`}
            >
              {actionLabels[a]}
            </button>
          ))}
        </div>
      </fieldset>

      {needsAmount(draft.action) ? (
        <div>
          <label htmlFor="amount" className="mb-1 block font-quest-sans text-sm text-quest-vellum-dim">
            Amount in euros
          </label>
          <input
            id="amount"
            type="text"
            inputMode="numeric"
            autoComplete="off"
            value={amountText}
            onChange={(e) => {
              const raw = e.target.value.trim();
              setAmountText(e.target.value);
              set({ amount_eur: raw === '' ? null : /^\d+$/.test(raw) ? Number(raw) : Number.NaN });
              setTouched((t) => ({ ...t, amount: true }));
            }}
            aria-invalid={errors.amount !== undefined}
            className="min-h-11 w-full rounded-md border border-quest-gilt bg-quest-lapis-deep px-3 text-base"
          />
          {errors.amount ? (
            <p role="alert" className="mt-1 font-quest-sans text-sm text-quest-wax-light">
              {errors.amount}
            </p>
          ) : null}
        </div>
      ) : null}

      <div>
        <label htmlFor="evidence" className="mb-1 block font-quest-sans text-sm text-quest-vellum-dim">
          Evidence: which facts, risks and alternatives drove your choice?
        </label>
        <textarea
          id="evidence"
          rows={4}
          value={draft.evidence}
          onChange={(e) => {
            set({ evidence: e.target.value });
            setTouched((t) => ({ ...t, evidence: true }));
          }}
          aria-invalid={errors.evidence !== undefined}
          className="w-full rounded-md border border-quest-gilt bg-quest-lapis-deep p-3 text-base"
        />
        {errors.evidence ? (
          <p role="alert" className="mt-1 font-quest-sans text-sm text-quest-wax-light">
            {errors.evidence}
          </p>
        ) : null}
      </div>

      <div>
        <label htmlFor="forecast" className="mb-1 block">
          How likely is it that the company&apos;s share price is higher at the end of about {horizon} days than
          today?
        </label>
        <input
          id="forecast"
          type="range"
          min={0}
          max={100}
          step={5}
          value={draft.forecast_pct}
          onChange={(e) => set({ forecast_pct: Number(e.target.value) })}
          className="w-full accent-quest-gilt"
        />
        <output htmlFor="forecast" className="block font-quest-sans text-quest-gilt">
          {draft.forecast_pct}%
        </output>
      </div>

      <fieldset>
        <legend className="mb-1 font-quest-sans text-sm text-quest-vellum-dim">Confidence in my reasoning</legend>
        <div role="radiogroup" aria-label="Confidence in my reasoning" className="grid grid-cols-3 gap-2">
          {confidences.map((c) => (
            <button
              key={c}
              type="button"
              role="radio"
              aria-checked={draft.confidence === c}
              onClick={() => set({ confidence: c })}
              className={`min-h-11 rounded-md border-2 font-quest-sans capitalize ${
                draft.confidence === c ? 'border-quest-gilt bg-quest-verdigris' : 'border-quest-lapis bg-quest-lapis-deep'
              }`}
            >
              {c.charAt(0).toUpperCase() + c.slice(1)}
            </button>
          ))}
        </div>
      </fieldset>

      <section aria-label="Summary" className="rounded-lg border border-quest-lapis bg-quest-lapis-deep p-3 font-quest-sans text-sm">
        <h2 className="font-quest-title text-xl text-quest-gilt">Summary</h2>
        <dl className="space-y-1">
          <div><dt className="inline text-quest-vellum-dim">Decision: </dt><dd className="inline">{draft.action ? actionLabels[draft.action] : '—'}</dd></div>
          {needsAmount(draft.action) ? (
            <div><dt className="inline text-quest-vellum-dim">Amount: </dt><dd className="inline">{isValidAmount(draft.amount_eur, budget) ? formatEur(draft.amount_eur) : '—'}</dd></div>
          ) : null}
          <div><dt className="inline text-quest-vellum-dim">Forecast: </dt><dd className="inline">{draft.forecast_pct}% likely higher</dd></div>
          <div><dt className="inline text-quest-vellum-dim">Confidence: </dt><dd className="inline capitalize">{draft.confidence ?? '—'}</dd></div>
        </dl>
      </section>

      {failed ? (
        <p role="alert" className="font-quest-sans text-sm text-quest-wax-light">
          Could not lock your decision. Please try again.
        </p>
      ) : null}
      <button
        type="submit"
        disabled={!valid}
        className="min-h-11 w-full rounded-md bg-quest-wax px-5 font-quest-sans text-lg font-bold text-quest-vellum disabled:opacity-40"
      >
        Lock my decision
      </button>

      {stage === 'confirm' ? (
        <div role="alertdialog" aria-modal="true" aria-labelledby="lock-q" className="fixed inset-0 z-20 flex items-center justify-center bg-black/70 p-5">
          <div className="w-full max-w-sm space-y-4 rounded-lg bg-quest-lapis p-5">
            <p id="lock-q" className="text-lg">Once locked, you can&apos;t change it. Lock?</p>
            <div className="flex gap-3">
              <button type="button" onClick={() => void lock()} className="min-h-11 flex-1 rounded-md bg-quest-wax font-quest-sans font-bold">
                Lock
              </button>
              <button type="button" onClick={() => setStage('form')} className="min-h-11 flex-1 rounded-md border border-quest-vellum-dim font-quest-sans">
                Go back
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </form>
  );
}

function TimeSkip({ label, onDone }: { label: string; onDone: () => void }): React.JSX.Element {
  useEffect(() => {
    const t = setTimeout(onDone, SKIP_MS);
    return () => clearTimeout(t);
  }, [onDone]);
  return (
    <button
      type="button"
      onClick={onDone}
      className="flex min-h-[60dvh] w-full flex-col items-center justify-center gap-2 text-center"
    >
      <span className="font-quest-title text-5xl text-quest-gilt">{label}</span>
      <span className="font-quest-sans text-sm text-quest-vellum-dim">Tap to continue</span>
    </button>
  );
}
