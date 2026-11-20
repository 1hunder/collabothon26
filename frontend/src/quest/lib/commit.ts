import type { CommitDraft, CommitRequest, DecisionAction } from '../../api/types';

export const EVIDENCE_MIN = 20;
export const REFLECTION_MIN = 10;

export const emptyDraft: CommitDraft = {
  action: null,
  amount_eur: null,
  evidence: '',
  forecast_pct: 50,
  confidence: null,
};

export const needsAmount = (a: DecisionAction | null): boolean => a === 'invest' || a === 'spread';

export interface CommitErrors {
  amount?: string;
  evidence?: string;
}

/** Client-side form validation only; the server revalidates at lock. */
export function validateCommit(d: CommitDraft, budget: number, touched: { amount: boolean; evidence: boolean }): CommitErrors {
  const errors: CommitErrors = {};
  if (needsAmount(d.action) && touched.amount && !isValidAmount(d.amount_eur, budget)) {
    errors.amount = `Enter an amount from €1 to €${budget.toLocaleString('en-US')}.`;
  }
  if (touched.evidence && d.evidence.trim().length < EVIDENCE_MIN) {
    errors.evidence = 'Explain your reasoning in at least 20 characters.';
  }
  return errors;
}

export function isValidAmount(n: number | null, budget: number): n is number {
  return n !== null && Number.isInteger(n) && n >= 1 && n <= budget;
}

export function toRequest(d: CommitDraft, budget: number): CommitRequest | null {
  if (d.action === null || d.confidence === null) return null;
  if (d.evidence.trim().length < EVIDENCE_MIN) return null;
  if (needsAmount(d.action)) {
    if (!isValidAmount(d.amount_eur, budget)) return null;
    return { action: d.action, amount_eur: d.amount_eur, evidence: d.evidence.trim(), forecast_pct: d.forecast_pct, confidence: d.confidence };
  }
  return { action: d.action, evidence: d.evidence.trim(), forecast_pct: d.forecast_pct, confidence: d.confidence };
}

export const actionLabels: Record<DecisionAction, string> = {
  invest: 'Invest',
  dont_invest: "Don't invest",
  wait: 'Wait',
  spread: 'Spread the money',
};

export function formatEur(n: number): string {
  return `€${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatPct(n: number): string {
  return `${n < 0 ? '−' : n > 0 ? '+' : ''}${Math.abs(n).toFixed(1)}%`;
}

export function formatSigned(n: number): string {
  return `${n < 0 ? '−' : n > 0 ? '+' : ''}${formatEur(Math.abs(n))}`;
}
