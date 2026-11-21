import { useState } from 'react';
import { useAddLesson, useVeteranTimeline, type Judgement, type Luck, type TimelineDecision } from '../../api/veteran';
import Sheet from './Sheet';

interface VeteranTimelineProps {
  campaignId: string;
  onClose: () => void;
}

const JUDGEMENT: Record<Judgement, { label: string; cls: string }> = {
  sound: { label: 'Sound', cls: 'bg-quest-verdigris/20 text-[#24584F]' },
  hasty: { label: 'Hasty', cls: 'bg-quest-wax/15 text-[#8A2420]' },
  thin: { label: 'No reason', cls: 'bg-[#7A6548]/15 text-[#6E5C43]' },
};
const LUCK: Record<Luck, { label: string; cls: string }> = {
  kind: { label: 'Kind', cls: 'bg-quest-verdigris/20 text-[#24584F]' },
  cruel: { label: 'Cruel', cls: 'bg-quest-wax/15 text-[#8A2420]' },
  neutral: { label: '—', cls: 'bg-[#7A6548]/10 text-[#6E5C43]' },
};
const ACTION: Record<TimelineDecision['action'], string> = { buy: 'Bought', sell: 'Sold', hold: 'Held' };
const BAND: Record<string, string> = {
  well_matched: 'Your confidence matched the result',
  overconfident: 'Surer than the evidence allowed',
  underconfident: 'Right, but with little trust in yourself',
  missed: 'Read one way, went the other',
  hedged: 'Kept near even odds',
};

function Pill({ label, cls }: { label: string; cls: string }): React.JSX.Element {
  return <span className={`inline-block rounded-full px-2 py-0.5 font-quest-sans text-[12px] font-bold ${cls}`}>{label}</span>;
}

/**
 * Brannoc's ledger of one finished quest: each decision in order with the hero's own words, and
 * two separate columns, judgement (yours) and luck (the die's). Ends with "keep a lesson".
 */
export default function VeteranTimeline({ campaignId, onClose }: VeteranTimelineProps): React.JSX.Element {
  const tl = useVeteranTimeline(campaignId);
  const addLesson = useAddLesson();
  const [lesson, setLesson] = useState('');
  const kept = addLesson.isSuccess;
  const t = tl.data;

  return (
    <Sheet title={t ? t.title : 'Decision timeline'} subtitle={t ? `From Brannoc's ledger · quest ${t.number}${t.real_name ? ` · ${t.real_name}` : ''}` : undefined} onClose={onClose}>
      {tl.isPending ? <p role="status" className="font-quest">Brannoc leafs through his ledger…</p> : null}
      {tl.isError ? <p role="alert" className="font-quest">This page of the ledger is sealed for now.</p> : null}
      {t ? (
        <div className="flex flex-col gap-4 font-quest">
          <table className="w-full border-collapse text-left text-[15px]">
            <thead>
              <tr className="border-b border-[#5a3c1e]/30 font-quest-sans text-[11px] uppercase tracking-[0.1em] text-[#7A6548]">
                <th className="py-1 font-normal">Your decision</th>
                <th className="w-[74px] py-1 text-center font-normal">Judgement</th>
                <th className="w-[58px] py-1 text-center font-normal">Luck</th>
              </tr>
            </thead>
            <tbody>
              {t.decisions.map((d) => (
                <tr key={d.seq} data-testid="timeline-row" className="border-b border-dashed border-[#5a3c1e]/25 align-top">
                  <td className="py-2 pr-2">
                    <span className="block font-quest-sans text-[11px] font-bold uppercase tracking-[0.08em] text-[#7A6548]">
                      {d.when} · {d.day}
                    </span>
                    {ACTION[d.action]}
                    {d.action !== 'hold' && d.amount_eur > 0 ? ` ${d.amount_eur} coins` : ''}.{' '}
                    <q className="italic text-[#3E2D1A]">{d.text}</q>
                    {d.reasoning ? (
                      <span className="mt-0.5 block text-[13px] text-[#6E5C43]">
                        You said: <q className="italic">{d.reasoning}</q>
                      </span>
                    ) : null}
                  </td>
                  <td className="py-2 text-center"><Pill {...JUDGEMENT[d.judgement]} /></td>
                  <td className="py-2 text-center"><Pill {...LUCK[d.luck]} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <dl className="grid grid-cols-2 gap-2 text-[14px]">
            <div className="rounded-lg bg-white/40 p-2">
              <dt className="font-quest-sans text-[11px] uppercase tracking-[0.1em] text-[#7A6548]">Forecast</dt>
              <dd>
                {t.forecast.pct !== null ? `${t.forecast.pct}% likely higher, ${t.forecast.confidence ?? ''} confidence` : 'Left open'}
              </dd>
            </div>
            <div className="rounded-lg bg-white/40 p-2">
              <dt className="font-quest-sans text-[11px] uppercase tracking-[0.1em] text-[#7A6548]">What happened</dt>
              <dd>
                Ended {t.forecast.market === 'up' ? 'higher' : 'lower'}. {BAND[t.forecast.band] ?? ''}
              </dd>
            </div>
            <div className="rounded-lg bg-white/40 p-2">
              <dt className="font-quest-sans text-[11px] uppercase tracking-[0.1em] text-[#7A6548]">Clues missed</dt>
              <dd>{t.missed.length ? t.missed.join(', ') : 'None: every key clue found'}</dd>
            </div>
            <div className="rounded-lg bg-white/40 p-2">
              <dt className="font-quest-sans text-[11px] uppercase tracking-[0.1em] text-[#7A6548]">Result</dt>
              <dd>
                {t.result.pnl_pct !== null ? `${t.result.pnl_pct > 0 ? '+' : ''}${t.result.pnl_pct}%` : '—'} · +{t.xp} XP
              </dd>
            </div>
          </dl>
          <form
            aria-label="Keep a lesson"
            className="flex flex-col gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (lesson.trim().length < 3 || addLesson.isPending || kept) return;
              addLesson.mutate({ text: lesson.trim(), campaign_id: t.campaign_id });
            }}
          >
            <label htmlFor="veteran-lesson" className="font-quest-sans text-[12px] uppercase tracking-[0.1em] text-[#7A6548]">
              Lesson learned
            </label>
            <textarea
              id="veteran-lesson"
              value={lesson}
              onChange={(e) => setLesson(e.target.value)}
              disabled={kept}
              rows={2}
              maxLength={280}
              placeholder="In your own words: what will you do differently?"
              className="w-full resize-none rounded-md border border-[#5a3c1e]/35 bg-white/60 p-2 text-base text-quest-soot"
            />
            {addLesson.isError ? <p role="alert" className="text-sm text-[#8A2420]">Could not keep the lesson. Try again.</p> : null}
            <button
              type="submit"
              disabled={kept || addLesson.isPending || lesson.trim().length < 3}
              className={`min-h-11 rounded-full px-4 font-quest-title text-lg text-[#F4E9D2] disabled:opacity-60 ${kept ? 'bg-quest-verdigris' : 'bg-quest-wax'}`}
            >
              {kept ? 'Kept in your journal' : 'Keep in journal'}
            </button>
          </form>
        </div>
      ) : null}
    </Sheet>
  );
}
