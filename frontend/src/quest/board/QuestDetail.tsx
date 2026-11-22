import { useBoardQuest } from '../../api/board';
import type { QuestCard } from '../../api/types';
import ParchmentSheet from './ParchmentSheet';
import { QuestMeta } from './QuestNotice';

interface QuestDetailProps {
  card: QuestCard;
  onClose: () => void;
  onStart: (card: QuestCard) => void;
}

/** A quest unrolled: everything to read before taking it, then the Start button. */
export default function QuestDetail({ card, onClose, onStart }: QuestDetailProps): React.JSX.Element {
  const detail = useBoardQuest(card.id);
  const d = detail.data?.details;
  const ready = card.status === 'ready' && card.scenario_id !== null;
  return (
    <ParchmentSheet
      title={card.title}
      onClose={onClose}
      footer={
        <button
          type="button"
          data-autofocus
          className="qb-btn w-full"
          disabled={!ready}
          onClick={() => onStart(card)}
        >
          {card.finished ? 'Play again' : 'Start this quest'}
        </button>
      }
    >
      <p className="mt-1 text-lg italic text-[#5b4630]">{card.company_name}, {card.trade}</p>
      <p className="mt-3 text-lg leading-snug">{card.teaser}</p>
      <div className="mt-3"><QuestMeta card={card} /></div>

      {detail.isError ? (
        <p role="alert" className="mt-4 text-lg">The rest of this notice could not be read. Close it and open it again.</p>
      ) : !d ? (
        <p role="status" className="mt-4 text-lg italic">Unrolling the parchment…</p>
      ) : (
        <>
          <h3 className="qb-h">The briefing</h3>
          <p className="text-lg leading-snug">{d.briefing}</p>
          {d.characters.length > 0 ? (
            <>
              <h3 className="qb-h">Who you will meet</h3>
              <ul className="qb-list">
                {d.characters.map((c) => <li key={c.name}><strong>{c.name}</strong>, {c.role}</li>)}
              </ul>
            </>
          ) : null}
          {d.places.length > 0 ? (
            <>
              <h3 className="qb-h">Where it happens</h3>
              <ul className="qb-list">{d.places.map((p) => <li key={p}>{p}</li>)}</ul>
            </>
          ) : null}
          <h3 className="qb-h">What you&apos;ll do</h3>
          <ol className="qb-list">{d.what_you_do.map((s) => <li key={s}>{s}</li>)}</ol>
        </>
      )}
      {card.learn.length > 0 ? (
        <>
          <h3 className="qb-h">What you&apos;ll learn</h3>
          <ul className="qb-chips">{card.learn.map((l) => <li key={l}>{l}</li>)}</ul>
        </>
      ) : null}
    </ParchmentSheet>
  );
}
