import { Feather } from 'lucide-react';
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useBoard, useCommissionQuest } from '../../api/board';
import type { QuestCard } from '../../api/types';
import CommissionSheet from './CommissionSheet';
import QuestDetail from './QuestDetail';
import QuestNotice from './QuestNotice';
import './QuestBoard.css';

/** `/quest/board`: pick a quest from the guild notices or commission one of your own. */
export default function QuestBoard(): React.JSX.Element {
  const board = useBoard();
  const commission = useCommissionQuest();
  const navigate = useNavigate();
  const location = useLocation();
  const [openId, setOpenId] = useState<string | null>(null);
  const [commissioning, setCommissioning] = useState(false);

  if (board.isError) return <p role="alert">Could not load the Quest Board. Please try again.</p>;
  if (!board.data) return <p role="status">Reading the notices…</p>;
  const { curated, mine, suggestion } = board.data;
  const open = [...curated, ...mine].find((c) => c.id === openId) ?? null;

  const start = (card: QuestCard): void => {
    if (!card.scenario_id) return;
    void navigate('/quest/disclosure', { state: { ...(location.state as object | null), scenarioId: card.scenario_id } });
  };
  const submit = (theme?: string): void =>
    commission.mutate(theme, {
      onSuccess: () => setCommissioning(false),
    });

  const notices = (cards: QuestCard[]): React.JSX.Element => (
    <ul className="qb-grid">
      {cards.map((c) => (
        <li key={c.id}>
          <QuestNotice card={c} onOpen={(card) => setOpenId(card.id)} onRetry={() => submit()} />
        </li>
      ))}
    </ul>
  );

  return (
    <div className="qb-board">
      <div className="qb-plank">
        <h1 className="font-quest-title text-4xl leading-none text-quest-gilt">Quest Board</h1>
      </div>
      <p className="mb-4 text-center text-lg italic text-quest-vellum">Choose a notice, read it, then take the quest.</p>

      <section aria-labelledby="qb-guild">
        <h2 id="qb-guild" className="qb-section-title font-quest-title">Guild notices</h2>
        {notices(curated)}
      </section>

      <section aria-labelledby="qb-mine">
        <h2 id="qb-mine" className="qb-section-title font-quest-title">Your quests</h2>
        <ul className="qb-grid">
          <li>
            <div className="qb-wrap">
              <button type="button" className="qb-notice qb-commission" onClick={() => setCommissioning(true)}>
                <Feather aria-hidden="true" className="mx-auto mb-1 text-quest-gilt" size={26} />
                <span className="block font-quest-title text-2xl text-quest-gilt">Commission a new quest</span>
                <span className="block text-base">Built from your spending, or from what you ask for.</span>
              </button>
            </div>
          </li>
        </ul>
        {mine.length > 0 ? <div className="mt-5">{notices(mine)}</div> : null}
      </section>

      {open ? <QuestDetail card={open} onClose={() => setOpenId(null)} onStart={start} /> : null}
      {commissioning ? (
        <CommissionSheet
          suggestion={suggestion}
          busy={commission.isPending}
          failed={commission.isError}
          onCommission={submit}
          onClose={() => setCommissioning(false)}
        />
      ) : null}
    </div>
  );
}
