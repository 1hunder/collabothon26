import { useCallback, useEffect, useState } from 'react';
import { fetchLesson } from '../../api/edu';
import type { EduLesson, EduMoment } from '../../api/types';
import { BUDDY_NAME } from './DialogueBox';
import type { EduControls } from './useEdu';

const btn = 'min-h-11 rounded-full px-5 font-quest-sans font-bold';
const primary = `${btn} border border-quest-gilt bg-quest-lapis-deep text-quest-soot`;
const quiet = `${btn} border border-quest-vellum-dim/50 font-medium text-quest-vellum-dim`;

/** Buddy asks whether to look at the waiting learning moments. */
export function EduOffer({ pending, onShow, onNotNow, onLater }: {
  pending: EduMoment[];
  onShow: (m: EduMoment) => void;
  onNotNow: (m: EduMoment) => void;
  onLater: () => void;
}): React.JSX.Element {
  const [only] = pending.length === 1 ? pending : [];
  return (
    <div role="region" aria-label="Learning moments" className="mx-3 rounded-lg bg-quest-lapis/95 p-4 font-quest text-quest-vellum">
      <p className="font-quest-sans text-sm font-bold uppercase tracking-wide text-quest-verdigris-light">{BUDDY_NAME}</p>
      {only ? (
        <>
          <p className="mt-1 text-lg leading-snug">I spotted a learning moment: {only.title}. Want to take a look?</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className={primary} onClick={() => onShow(only)}>Show me</button>
            <button type="button" className={quiet} onClick={() => onNotNow(only)}>Not now</button>
            <button type="button" className={quiet} onClick={onLater}>Later</button>
          </div>
        </>
      ) : (
        <>
          <p className="mt-1 text-lg leading-snug">I spotted {pending.length} learning moments. Which one first?</p>
          <ul className="mt-3 flex flex-col gap-2">
            {pending.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-2 rounded-md bg-quest-soot/50 p-2">
                <span className="min-w-0 flex-1 text-base">{m.title}</span>
                <button type="button" aria-label={`Show me: ${m.title}`} className={primary} onClick={() => onShow(m)}>Show me</button>
                <button type="button" aria-label={`Not now: ${m.title}`} className={quiet} onClick={() => onNotNow(m)}>Not now</button>
              </li>
            ))}
          </ul>
          <button type="button" className={`${quiet} mt-3`} onClick={onLater}>Later</button>
        </>
      )}
    </div>
  );
}

type Load = { s: 'loading' } | { s: 'error' } | { s: 'ready'; lesson: EduLesson };

function Section({ title, children }: { title: string; children: React.ReactNode }): React.JSX.Element {
  return (
    <section className="mt-5">
      <h3 className="font-quest-sans text-sm font-bold uppercase tracking-wide text-quest-verdigris-light">{title}</h3>
      <p className="mt-1 text-lg leading-relaxed">{children}</p>
    </section>
  );
}

/** The learning card: what happened, the idea, an example, the takeaway, then a one-question check. */
export function EduLessonCard({ edu, moment, onDone }: { edu: EduControls; moment: EduMoment; onDone: () => void }): React.JSX.Element {
  const [load, setLoad] = useState<Load>({ s: 'loading' });
  const [picked, setPicked] = useState<number | null>(null);
  const { campaignId, settle } = edu;

  const request = useCallback((): void => {
    fetchLesson(campaignId, moment.id).then(
      (lesson) => {
        setLoad({ s: 'ready', lesson });
        settle(moment.id);
      },
      () => setLoad({ s: 'error' }),
    );
  }, [campaignId, moment.id, settle]);
  useEffect(request, [request]);
  const retry = (): void => {
    setLoad({ s: 'loading' });
    setPicked(null);
    request();
  };

  if (load.s === 'loading') {
    return <p role="status" className="mx-3 rounded-lg bg-quest-lapis/95 p-4 font-quest text-lg text-quest-vellum">CommerzBuddy is preparing your lesson…</p>;
  }
  if (load.s === 'error') {
    return (
      <div role="alert" className="mx-3 rounded-lg bg-quest-lapis/95 p-4 font-quest text-quest-vellum">
        <p>Couldn&apos;t prepare this one.</p>
        <div className="mt-2 flex gap-2">
          <button type="button" className={primary} onClick={retry}>Try again</button>
          <button type="button" className={quiet} onClick={onDone}>Back</button>
        </div>
      </div>
    );
  }
  const { lesson } = load;
  const { check } = lesson;
  return (
    <article aria-label="Learning moment" className="mx-3 max-h-[68dvh] overflow-y-auto rounded-lg bg-quest-lapis/95 p-5 font-quest text-quest-vellum">
      <h2 className="font-quest-title text-2xl leading-tight text-quest-gilt">{lesson.title}</h2>
      <Section title="What happened">{lesson.what_happened}</Section>
      <Section title="The idea">{lesson.idea}</Section>
      <Section title="A quick example">{lesson.example}</Section>
      <section className="mt-5 rounded-md border border-quest-gilt bg-quest-soot/60 p-3">
        <h3 className="font-quest-sans text-sm font-bold uppercase tracking-wide text-quest-gilt">Remember</h3>
        <p className="mt-1 text-lg font-bold leading-snug">{lesson.takeaway}</p>
      </section>
      <section aria-label="Quick check" className="mt-6">
        <h3 className="font-quest-sans text-sm font-bold uppercase tracking-wide text-quest-verdigris-light">Quick check</h3>
        <p className="mt-1 text-lg">{check.question}</p>
        <ul className="mt-2 flex flex-col gap-2">
          {check.options.map((o, i) => {
            const right = picked !== null && i === check.answer_index;
            const wrong = picked === i && i !== check.answer_index;
            return (
              <li key={o}>
                <button
                  type="button"
                  disabled={picked !== null}
                  data-state={right ? 'correct' : wrong ? 'incorrect' : undefined}
                  onClick={() => setPicked(i)}
                  className={`min-h-11 w-full rounded-lg border px-4 py-2 text-left text-base ${right ? 'border-quest-verdigris-light bg-quest-verdigris/40' : wrong ? 'border-quest-wax-light bg-quest-wax/40' : 'border-quest-vellum-dim/50 bg-quest-soot/40'}`}
                >
                  {o}
                </button>
              </li>
            );
          })}
        </ul>
        {picked !== null ? (
          <p role="status" className="mt-2 text-base">
            {picked === check.answer_index ? 'Correct. Nicely spotted.' : `Not quite. The answer is: ${check.options[check.answer_index]}.`}
          </p>
        ) : null}
      </section>
      <button type="button" className={`${primary} mt-5`} onClick={onDone}>Done</button>
    </article>
  );
}
