import { Link, useNavigate } from 'react-router-dom';
import { useHero } from '../../api/campaign';
import type { HeroClass } from '../../api/types';

const advantages: Record<HeroClass, string> = {
  guardian: 'Safety Cushion — start each campaign with 120 HP (€1,200)',
  analyst: 'Second Look — reroll one failed dice check per campaign',
  investigator: 'Keen Eye — roll one dice check per campaign with advantage',
};

/** `/quest/hero`: class advantage, items and learning history. */
export default function HeroScreen(): React.JSX.Element {
  const hero = useHero();
  const navigate = useNavigate();
  if (hero.isError) return <p role="alert">Could not load your hero.</p>;
  if (!hero.data) return <p role="status">Loading…</p>;
  const h = hero.data;
  return (
    <div className="space-y-5 pb-8">
      <button type="button" onClick={() => void navigate(-1)} className="min-h-11 font-quest-sans text-quest-vellum-dim underline">
        Back
      </button>
      <h1 className="font-quest-title text-4xl text-quest-gilt">{h.name}</h1>
      <p className="font-quest-sans capitalize text-quest-vellum-dim">
        {h.class} · {h.total_xp} XP
      </p>
      <section>
        <h2 className="font-quest-title text-2xl text-quest-gilt">Class advantage</h2>
        <p>{advantages[h.class]}</p>
      </section>
      <section>
        <h2 className="font-quest-title text-2xl text-quest-gilt">Items</h2>
        {h.items.length === 0 ? (
          <p className="font-quest-sans text-quest-vellum-dim">No items yet. Earn 70 XP in a quest to win one.</p>
        ) : (
          <ul className="space-y-2">
            {h.items.map((i) => (
              <li key={i.id}>
                <span className="font-bold">{i.name}</span>
                {i.description ? <span className="block text-sm text-quest-vellum-dim">{i.description}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <h2 className="font-quest-title text-2xl text-quest-gilt">Learning history</h2>
        {h.history.length === 0 ? (
          <p className="font-quest-sans text-quest-vellum-dim">No finished quests yet.</p>
        ) : (
          <ul className="space-y-2 font-quest-sans">
            {h.history.map((e) => (
              <li key={e.campaign_id} className="rounded-md border border-quest-lapis p-2">
                {e.finished_at ? <time dateTime={e.finished_at} className="block text-sm text-quest-vellum-dim">{e.finished_at}</time> : null}
                {e.interests.length > 0 && <>{e.interests.join(', ')} · </>}
                <span>{e.total_xp} XP</span>
                {e.decision ? <span> · {e.decision}</span> : null}
                {typeof e.result_pct === 'number' ? <span> · {e.result_pct.toFixed(1)}%</span> : null}
                <Link to={`/quest/journal/${e.campaign_id}`} className="block text-quest-verdigris-light underline">
                  Journal
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
