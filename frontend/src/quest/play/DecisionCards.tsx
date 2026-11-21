import type { MarketCard, Offer, Purse, TradeCard } from '../../api/types';
import { formatEur } from '../lib/commit';
import type { OfferMomentCard } from './cards';

const beatTitle: Record<MarketCard['beat'], string> = {
  opening: 'An offer on the table',
  news: 'The market stirs',
  decision: 'The day of decision',
  story: 'A moment of decision',
  offer: 'An offer on the table',
};

/** The offer's terms in plain words, every figure from the server. */
export function offerTerms(offer: Pick<Offer, 'kind' | 'terms'>): string {
  const t = offer.terms;
  if (offer.kind === 'loan') {
    return `Up to ${formatEur(Number(t.principal_eur))} now, ${t.interest_pct}% flat interest: repay ${formatEur(Number(t.repay_eur))} ${t.due}.`;
  }
  return `Buys back up to ${formatEur(Number(t.max_eur))} of your coins at ${t.price}.`;
}

/** Cash and coins in the company, exactly as the server computed them. */
export function PurseLine({ purse, className = '' }: { purse: Purse; className?: string }): React.JSX.Element {
  return (
    <dl aria-label="Your purse" className={`flex flex-wrap gap-x-4 gap-y-1 font-quest-sans text-[15px] ${className}`}>
      <div>
        <dt className="inline text-quest-vellum-dim">Cash </dt>
        <dd className="inline font-bold">{formatEur(purse.cash_eur)}</dd>
      </div>
      <div>
        <dt className="inline text-quest-vellum-dim">In the company </dt>
        <dd className="inline font-bold">{formatEur(purse.position_eur)}</dd>
      </div>
      {purse.loan ? (
        <div className="basis-full">
          <dt className="inline text-quest-vellum-dim">Loan </dt>
          <dd className="inline font-bold">{purse.loan.label}</dd>
        </div>
      ) : null}
    </dl>
  );
}

interface MarketMomentProps {
  card: MarketCard;
  onAnswer: () => void;
}

/** The story puts an investment choice to the hero; their next written action answers it. */
export function MarketMoment({ card, onAnswer }: MarketMomentProps): React.JSX.Element {
  return (
    <div className="absolute inset-0 z-[26] flex items-center bg-quest-soot/75 px-5">
      <article
        aria-label="Decision scene"
        className="w-full rounded-lg border border-quest-gilt/60 bg-quest-lapis-deep/95 p-5 text-quest-vellum shadow-[0_20px_60px_rgba(0,0,0,0.6)]"
      >
        <p className="font-quest-sans text-xs font-bold uppercase tracking-widest text-quest-gilt">
          {card.day_label} · Your decision
        </p>
        <h2 className="mt-1 font-quest-title text-3xl leading-tight text-quest-gilt">{beatTitle[card.beat]}</h2>
        <p className="mt-3 font-quest text-[17px] leading-snug">{card.text}</p>
        <PurseLine purse={card.purse} className="mt-4 border-t border-quest-lapis pt-3" />
        <p className="mt-3 font-quest-sans text-sm text-quest-vellum-dim">
          Answer in your own words: put coins in, take coins out, or wait, and say why.
        </p>
        <button
          type="button"
          onClick={onAnswer}
          className="mt-4 min-h-11 rounded-full border border-quest-gilt bg-quest-lapis px-6 font-quest-sans font-bold"
        >
          Decide
        </button>
      </article>
    </div>
  );
}

const verb: Record<TradeCard['action'], string> = { buy: 'Put in', sell: 'Took out', hold: 'Held your coins', loan: 'Borrowed' };

interface OfferMomentProps {
  card: OfferMomentCard;
  onAnswer: () => void;
}

/** Someone in the world offers the hero a way out of being all in; the answer is typed, like every decision. */
export function OfferMoment({ card, onAnswer }: OfferMomentProps): React.JSX.Element {
  return (
    <div className="absolute inset-0 z-[26] flex items-center bg-quest-soot/75 px-5">
      <article
        aria-label="An offer"
        className="w-full rounded-lg border border-quest-gilt/60 bg-quest-lapis-deep/95 p-5 text-quest-vellum shadow-[0_20px_60px_rgba(0,0,0,0.6)]"
      >
        <p className="font-quest-sans text-xs font-bold uppercase tracking-widest text-quest-gilt">
          {card.day_label} · An offer
        </p>
        <h2 className="mt-1 font-quest-title text-3xl leading-tight text-quest-gilt">{card.by.name}</h2>
        <p className="font-quest-sans text-sm text-quest-vellum-dim">{card.by.role}</p>
        <p className="mt-3 font-quest text-[17px] leading-snug">{card.text}</p>
        <p className="mt-3 border-t border-quest-lapis pt-3 font-quest-sans text-[15px] font-bold">{offerTerms({ kind: card.offer_kind, terms: card.terms })}</p>
        <PurseLine purse={card.purse} className="mt-3" />
        <p className="mt-3 font-quest-sans text-sm text-quest-vellum-dim">Answer in your own words: accept, decline, or do something else.</p>
        <button
          type="button"
          onClick={onAnswer}
          className="mt-4 min-h-11 rounded-full border border-quest-gilt bg-quest-lapis px-6 font-quest-sans font-bold"
        >
          Answer
        </button>
      </article>
    </div>
  );
}

interface TradeReceiptProps {
  card: TradeCard;
  onContinue: () => void;
}

/** What the engine executed for the hero's written decision. */
export function TradeReceipt({ card, onContinue }: TradeReceiptProps): React.JSX.Element {
  return (
    <div className="absolute inset-0 z-[26] flex items-center bg-quest-soot/70 px-5">
      <article
        aria-label="Decision recorded"
        className="w-full rotate-[0.5deg] rounded-md bg-quest-vellum p-5 text-quest-soot shadow-[0_20px_60px_rgba(0,0,0,0.6)]"
      >
        <p className="font-quest-sans text-xs font-bold uppercase tracking-widest text-quest-lapis">
          {card.day_label} · Decision {card.seq}
        </p>
        <h2 className="mt-1 font-quest-title text-3xl leading-tight text-quest-lapis">
          {card.action === 'hold' ? verb.hold : `${verb[card.action]} ${formatEur(card.amount_eur)}`}
        </h2>
        <p className="mt-2 font-quest-sans text-sm">
          {card.loan ? card.loan.label : 'Done at today\u2019s price on the board.'}
        </p>
        <PurseLine purse={card.purse} className="mt-3 text-quest-soot [&_dt]:text-quest-lapis" />
        <button
          type="button"
          onClick={onContinue}
          className="mt-4 min-h-11 rounded-full bg-quest-lapis px-6 font-quest-sans font-bold text-quest-vellum"
        >
          Continue
        </button>
      </article>
    </div>
  );
}
