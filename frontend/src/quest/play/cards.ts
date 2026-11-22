import type { DecisionBeat, DiceCard, LoanInfo, MarketCard, NewsCard, Offer, Purse, TradeAction, TradeCard } from '../../api/types';

const str = (v: unknown, fallback = ''): string => (typeof v === 'string' ? v : fallback);
const int = (v: unknown, fallback = 0): number => (typeof v === 'number' ? v : fallback);
const beats: readonly DecisionBeat[] = ['opening', 'news', 'decision', 'story', 'offer'];
const actions: readonly TradeAction[] = ['buy', 'sell', 'hold', 'loan', 'grant'];
const offerKinds: readonly Offer['kind'][] = ['buyback', 'loan', 'patron_grant', 'rescue_buyback', 'second_look'];

/** The offer of the all-in plot, as a card (who offers, on what terms). */
export interface OfferMomentCard extends Omit<Offer, 'kind'> {
  kind: 'offer';
  /** The offer's own kind (buyback / loan). */
  offer_kind: Offer['kind'];
  text: string;
  suggestions: string[];
  day_label: string;
  purse: Purse;
}

export type QuestCard = DiceCard | NewsCard | MarketCard | TradeCard | OfferMomentCard;

function purse(v: unknown): Purse {
  const p = (v && typeof v === 'object' ? v : {}) as Record<string, unknown>;
  return {
    cash_eur: int(p.cash_eur), position_eur: int(p.position_eur), total_eur: int(p.total_eur),
    loan: p.loan ? (p.loan as LoanInfo) : null,
  };
}

const beat = (v: unknown): DecisionBeat => (beats.includes(v as DecisionBeat) ? (v as DecisionBeat) : 'story');
const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []);

/** Accepts both `kind` (SSE card event) and `type` (JSON responses) as the discriminator. */
export function normalizeCard(raw: Record<string, unknown>): QuestCard | null {
  const kind = raw.kind ?? raw.type;
  if (kind === 'dice') {
    const challengeId = str(raw.challenge_id, str(raw.roll_id));
    return {
      kind: 'dice',
      roll_id: str(raw.roll_id, challengeId),
      challenge_id: challengeId,
      title: str(raw.title, 'A dice check'),
      dc: int(raw.dc),
      bonus: int(raw.bonus, 2),
      keen_eye_available: raw.keen_eye_available === true,
      keen_eye_left: int(raw.keen_eye_left),
      skill: typeof raw.skill === 'string' && raw.skill ? raw.skill : null,
    };
  }
  if (kind === 'news') {
    return {
      kind: 'news',
      headline: str(raw.headline),
      summary: str(raw.summary),
      time_skip_label: str(raw.time_skip_label),
      story_day: int(raw.story_day),
      framing_audio_text_id: typeof raw.framing_audio_text_id === 'number' ? raw.framing_audio_text_id : null,
    };
  }
  if (kind === 'market') {
    return {
      kind: 'market',
      beat: beat(raw.beat),
      text: str(raw.text),
      suggestions: strings(raw.suggestions),
      day_label: str(raw.day_label),
      purse: purse(raw.purse),
      audio_text_id: typeof raw.audio_text_id === 'number' ? raw.audio_text_id : null,
    };
  }
  if (kind === 'offer') {
    const by = (raw.by && typeof raw.by === 'object' ? raw.by : {}) as Record<string, unknown>;
    const terms = (raw.terms && typeof raw.terms === 'object' ? raw.terms : {}) as Offer['terms'];
    const offerKind = offerKinds.includes(raw.offer_kind as Offer['kind']) ? (raw.offer_kind as Offer['kind']) : 'buyback';
    const reason = typeof raw.reason === 'string' ? (raw.reason as Offer['reason']) : undefined;
    return {
      kind: 'offer', offer_kind: offerKind,
      by: { name: str(by.name), role: str(by.role) }, terms, ...(reason ? { reason } : {}),
      text: str(raw.text), suggestions: strings(raw.suggestions),
      day_label: str(raw.day_label), purse: purse(raw.purse),
    };
  }
  if (kind === 'trade') {
    return {
      kind: 'trade',
      ...(raw.loan ? { loan: raw.loan as LoanInfo } : {}),
      seq: int(raw.seq),
      beat: beat(raw.beat),
      action: actions.includes(raw.action as TradeAction) ? (raw.action as TradeAction) : 'hold',
      amount_eur: int(raw.amount_eur),
      day_label: str(raw.day_label),
      purse: purse(raw.purse),
    };
  }
  return null;
}
