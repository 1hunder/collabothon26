import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { fetchXp, finishCampaign, queryKeys } from '../../api/campaign';
import type { FinishResult, XpResult } from '../../api/types';
import { finishQuest } from '../questStore';
import { useActiveCampaign } from '../lib/useActiveCampaign';

/** `/quest/xp`: the campaign's rubric categories, then Finish quest. */
export default function Xp(): React.JSX.Element {
  const { id, campaign } = useActiveCampaign();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [fetched, setFetched] = useState<XpResult | null>(null);
  const [result, setResult] = useState<FinishResult | null>(null);
  const [failed, setFailed] = useState(false);
  const xp = campaign?.xp ?? fetched;

  useEffect(() => {
    if (id === null || !campaign || campaign.xp) return;
    let cancelled = false;
    fetchXp(id)
      .then((x) => {
        if (!cancelled) setFetched(x);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id, campaign]);

  if (failed) return <p role="alert">Could not load your XP. Please try again.</p>;
  if (!xp || id === null) return <p role="status">Scoring your reasoning…</p>;

  const finish = async (): Promise<void> => {
    setFailed(false);
    try {
      setResult(await finishCampaign(id));
      finishQuest();
    } catch {
      setFailed(true);
    }
  };

  return (
    <div className="space-y-5 pb-8">
      <h1 className="font-quest-title text-4xl text-quest-gilt">Your XP</h1>
      <ul className="space-y-4">
        {xp.categories.map((c) => (
          <li key={c.name} className="font-quest-sans">
            <div className="flex justify-between">
              <span className="font-bold">{c.name}</span>
              <span>
                {c.score} / {c.max}
              </span>
            </div>
            <p className="text-sm text-quest-vellum-dim">{c.rationale}</p>
            <blockquote className="border-l-2 border-quest-gilt pl-2 text-sm italic">“{c.quote}”</blockquote>
          </li>
        ))}
      </ul>
      <p className="font-quest-title text-3xl text-quest-gilt">Total {xp.total} / 100</p>
      {result ? (
        <div role="status" className="space-y-3 rounded-lg border border-quest-gilt p-3">
          <p>Total XP: {result.total_xp}</p>
          {result.new_item ? <p>New item: {result.new_item.name}</p> : null}
          <button
            type="button"
            onClick={() => {
              void qc.invalidateQueries({ queryKey: queryKeys.hero });
              void navigate('/overview', { replace: true });
            }}
            className="min-h-11 w-full rounded-md bg-quest-verdigris font-quest-sans font-bold"
          >
            Back to the bank
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => void finish()}
          className="min-h-11 w-full rounded-md bg-quest-verdigris px-5 font-quest-sans text-lg font-bold"
        >
          Finish quest
        </button>
      )}
    </div>
  );
}
