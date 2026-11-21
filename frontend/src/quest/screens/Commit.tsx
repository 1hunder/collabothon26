import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { lockDecision, patchCampaignCache, resumePlay, saveCommitDraft, useCampaign, useHero } from '../../api/campaign';
import type { CampaignState, CommitDraft, Confidence } from '../../api/types';
import ScreenBuddy from '../play/ScreenBuddy';
import { decisionLabel, emptyDraft, formatEur, toRequest } from '../lib/commit';

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
  const d = { ...emptyDraft, ...(readStored(c.id) ?? c.commit_draft ?? {}) };
  return { evidence: d.evidence ?? '', forecast_pct: d.forecast_pct ?? 50, confidence: d.confidence ?? null };
}

function CommitForm({ campaign }: { campaign: CampaignState }): React.JSX.Element {
  const campaignId = campaign.id;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const horizon = campaign.horizon_days ?? 0;
  const decisions = campaign.decisions ?? [];
  const purse = campaign.purse;

  const [draft, setDraft] = useState<CommitDraft>(() => initialDraft(campaign));
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
  const request = toRequest(draft);
  const valid = request !== null;

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
      <p className="font-quest-sans text-quest-vellum-dim">
        Your coins stay where your decisions put them until the horizon. Before the wait, say how you see it.
      </p>

      <section aria-label="Your decisions" className="space-y-2">
        <h2 className="font-quest-sans text-sm text-quest-vellum-dim">What you did with your coins</h2>
        {decisions.length === 0 ? (
          <p className="font-quest-sans">You made no investment decisions.</p>
        ) : (
          <ol className="space-y-2">
            {decisions.map((d) => (
              <li key={d.seq} className="rounded-md border border-quest-lapis bg-quest-lapis-deep p-3">
                <p className="font-quest-sans text-sm text-quest-vellum-dim">
                  {d.day_label} · <span className="font-bold text-quest-vellum">{decisionLabel(d)}</span>
                </p>
                <p className="mt-1 font-quest italic">&ldquo;{d.text}&rdquo;</p>
              </li>
            ))}
          </ol>
        )}
        {purse ? (
          <p className="font-quest-sans text-sm">
            Now: cash {formatEur(purse.cash_eur)} · in the company {formatEur(purse.position_eur)}
          </p>
        ) : null}
      </section>

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
                draft.confidence === c ? 'border-quest-gilt bg-quest-lapis' : 'border-quest-lapis bg-quest-lapis-deep'
              }`}
            >
              {c.charAt(0).toUpperCase() + c.slice(1)}
            </button>
          ))}
        </div>
      </fieldset>

      <div>
        <label htmlFor="evidence" className="mb-1 block font-quest-sans text-sm text-quest-vellum-dim">
          Anything to add to your reasoning? (optional)
        </label>
        <textarea
          id="evidence"
          rows={3}
          value={draft.evidence}
          onChange={(e) => set({ evidence: e.target.value })}
          className="w-full rounded-md border border-quest-gilt bg-quest-lapis-deep p-3 text-base"
        />
      </div>

      <section aria-label="Summary" className="rounded-lg border border-quest-lapis bg-quest-lapis-deep p-3 font-quest-sans text-sm">
        <h2 className="font-quest-title text-xl text-quest-gilt">Summary</h2>
        <dl className="space-y-1">
          <div><dt className="inline text-quest-vellum-dim">Decisions: </dt><dd className="inline">{decisions.length}</dd></div>
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
        className="min-h-11 w-full rounded-md border border-quest-wax-light bg-quest-lapis-deep px-5 font-quest-sans text-lg font-bold text-quest-vellum disabled:opacity-40"
      >
        Lock my decision
      </button>

      {stage === 'confirm' ? (
        <div role="alertdialog" aria-modal="true" aria-labelledby="lock-q" className="fixed inset-0 z-20 flex items-center justify-center bg-black/70 p-5">
          <div className="w-full max-w-sm space-y-4 rounded-lg bg-quest-lapis p-5">
            <p id="lock-q" className="text-lg">Once locked, you can&apos;t change it. Lock?</p>
            <div className="flex gap-3">
              <button type="button" onClick={() => void lock()} className="min-h-11 flex-1 rounded-md border border-quest-wax-light bg-quest-lapis-deep font-quest-sans font-bold">
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
      <span className="text-sm">Tap to continue</span>
    </button>
  );
}
