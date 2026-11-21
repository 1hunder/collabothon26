import type { CommitDraft, CommitRequest, DecisionEntry } from '../../api/types';

export const REFLECTION_MIN = 10;

/** The seal: forecast and confidence. What the hero did with their coins comes from the
 * decisions they wrote during the campaign; the closing note is optional. */
export const emptyDraft: CommitDraft = {
  evidence: '',
  forecast_pct: 50,
  confidence: null,
};

export function toRequest(d: CommitDraft): CommitRequest | null {
  if (d.confidence === null) return null;
  const note = d.evidence.trim();
  return { ...(note ? { evidence: note } : {}), forecast_pct: d.forecast_pct, confidence: d.confidence };
}

/** One decision in plain words: "Put in €300", "Took out €120", "Held". */
export function decisionLabel(d: Pick<DecisionEntry, 'action' | 'amount_eur'>): string {
  if (d.action === 'buy') return `Put in ${formatEur(d.amount_eur)}`;
  if (d.action === 'sell') return `Took out ${formatEur(d.amount_eur)}`;
  if (d.action === 'loan') return `Borrowed ${formatEur(d.amount_eur)}`;
  if (d.action === 'loss') return `Lost ${formatEur(d.amount_eur)} to damage`;
  return 'Held';
}

export function formatEur(n: number): string {
  return `€${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatPct(n: number): string {
  return `${n < 0 ? '−' : n > 0 ? '+' : ''}${Math.abs(n).toFixed(1)}%`;
}

export function formatSigned(n: number): string {
  return `${n < 0 ? '−' : n > 0 ? '+' : ''}${formatEur(Math.abs(n))}`;
}
