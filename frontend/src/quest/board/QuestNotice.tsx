import { Feather } from 'lucide-react';
import type { BoardDifficulty, QuestCard } from '../../api/types';
import { formatGold } from '../lib/gold';

const DIFFICULTY: Record<BoardDifficulty, { seals: number; label: string }> = {
  easy: { seals: 1, label: 'Easy' },
  medium: { seals: 2, label: 'Medium' },
  hard: { seals: 3, label: 'Hard' },
};

/** Difficulty as wax seals, with the word as text for everyone else. */
export function Difficulty({ level }: { level: BoardDifficulty }): React.JSX.Element {
  const d = DIFFICULTY[level];
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="qb-seals" aria-hidden="true">
        {[1, 2, 3].map((n) => <span key={n} className={n <= d.seals ? 'qb-seal on' : 'qb-seal'} />)}
      </span>
      <span>{d.label}</span>
      <span className="sr-only"> difficulty</span>
    </span>
  );
}

export function QuestMeta({ card }: { card: QuestCard }): React.JSX.Element {
  return (
    <span className="qb-meta">
      <Difficulty level={card.difficulty} />
      <span>{card.horizon_days} days</span>
      <span>{formatGold(card.budget_gp)}</span>
    </span>
  );
}

interface QuestNoticeProps {
  card: QuestCard;
  onOpen: (card: QuestCard) => void;
  onRetry: () => void;
}

/** One pinned notice. A ready notice opens its parchment; a generating one shows the ink drying. */
export default function QuestNotice({ card, onOpen, onRetry }: QuestNoticeProps): React.JSX.Element {
  const pin = <span className={card.kind === 'curated' ? 'qb-pin wax' : 'qb-pin'} aria-hidden="true" />;

  if (card.status === 'generating') {
    return (
      <div className="qb-wrap" role="status">
        {pin}
        <div className="qb-notice" style={{ cursor: 'default' }}>
          <p className="font-quest-title text-2xl leading-tight">
            <Feather aria-hidden="true" size={20} className="mr-1.5 inline-block align-[-3px]" />
            A quest is being written
          </p>
          <p className="qb-company">{card.step ?? 'The scribe is at work'}…</p>
          <div className="qb-ink" aria-hidden="true"><i /><i /><i /></div>
        </div>
      </div>
    );
  }

  if (card.status === 'failed') {
    return (
      <div className="qb-wrap">
        {pin}
        <div className="qb-notice qb-torn" style={{ cursor: 'default' }} role="alert">
          <p className="font-quest-title text-2xl leading-tight">This notice was torn</p>
          <p className="qb-teaser">The scribe could not finish this quest. Commission it again.</p>
          <div className="mt-3"><button type="button" className="qb-btn quiet" onClick={onRetry}>Try again</button></div>
        </div>
      </div>
    );
  }

  const stamp = card.finished ? 'Finished' : card.played ? 'Played' : null;
  return (
    <div className="qb-wrap">
      {pin}
      <button type="button" className="qb-notice" onClick={() => onOpen(card)} aria-label={`Open quest: ${card.title}`}>
        {stamp ? <span className={card.finished ? 'qb-stamp finished' : 'qb-stamp'}>{stamp}</span> : null}
        <span className="qb-title block font-quest-title">{card.title}</span>
        <span className="qb-company block">{card.company_name}, {card.trade}</span>
        <span className="qb-teaser block">{card.teaser}</span>
        <QuestMeta card={card} />
      </button>
    </div>
  );
}
