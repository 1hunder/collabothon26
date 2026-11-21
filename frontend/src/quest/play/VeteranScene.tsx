import { useEffect, useRef, useState } from 'react';
import type { DmStream } from '../../api/useDmStream';
import {
  HABITS_TOPIC,
  questLine,
  type VeteranDone,
  type VeteranMood,
  type VeteranOverview,
} from '../../api/veteran';
import DialogueBox, { VETERAN_NAME, type VoiceKind } from './DialogueBox';
import { VETERAN_DRAFT_KEY, useSessionDraft } from './useSessionDraft';
import VeteranPortrait, { VeteranToken } from './VeteranPortrait';

interface VeteranSceneProps {
  stream: DmStream;
  /** GET /hero/veteran; undefined while loading. */
  overview: VeteranOverview | undefined;
  onClose: () => void;
  /** Open the decision timeline card of a remembered quest. */
  onTimeline: (campaignId: string) => void;
  /** VOICE HOOK, same contract as DialogueBox.onPageShown. */
  onPageShown?: (text: string, voice: VoiceKind, audioTextId?: number | string | null) => void;
  /** Called before every request (stops the voice). */
  onAsked?: () => void;
}

const choiceBase =
  'min-h-11 w-full rounded-[4px_12px_12px_4px] border border-l-[3px] border-quest-wax-light/40 border-l-quest-wax-light bg-quest-lapis/90 px-3.5 py-2.5 text-left font-quest text-[17px] leading-snug text-quest-vellum disabled:opacity-50';

/**
 * A conversation with Brannoc by the Tavern fire. It runs beside the campaign, never in it: the
 * requests go to /hero/veteran, so no turn, focus or story day is spent.
 */
export default function VeteranScene({ stream, overview, onClose, onTimeline, onPageShown, onAsked }: VeteranSceneProps): React.JSX.Element {
  const { state, send } = stream;
  const [topic, setTopic] = useState<string | null>(null);
  const [advancedKey, setAdvancedKey] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [writing, setWriting] = useState(false);

  // Walking up to him starts the conversation: he greets (or, for a new hero, tells his story).
  const greeted = useRef(false);
  useEffect(() => {
    if (greeted.current || state.phase !== 'idle') return;
    greeted.current = true;
    send({ text: '', topic: null });
  }, [state.phase, send]);

  const done = state.phase === 'done' ? (state.extras as unknown as VeteranDone) : null;
  const busy = state.phase === 'sending' || state.phase === 'streaming';
  const mood: VeteranMood = busy ? 'pondering' : (done?.mood ?? 'listening');
  const key = state.phase === 'idle' ? 'idle' : state.clientMsgId;
  const inChoices = done !== null && advancedKey === key;

  const say = (text: string, nextTopic: string | null = topic): void => {
    if (busy) return;
    onAsked?.();
    setTopic(nextTopic);
    setPicking(false);
    setWriting(false);
    setAdvancedKey(null);
    send({ text, topic: nextTopic });
  };

  const quests = overview?.quests ?? [];
  const questTopic = topic !== null && topic !== HABITS_TOPIC ? topic : null;
  const showPicker = overview?.has_memory === true && (picking || topic === null);

  const body = ((): React.ReactNode => {
    if (state.phase === 'lost') {
      return (
        <div role="alert" className="mx-3 rounded-lg bg-quest-lapis/95 p-4 font-quest text-quest-vellum">
          <p>Brannoc stares into the fire, lost in an old memory.</p>
          <button type="button" onClick={stream.retry} className="mt-2 min-h-11 rounded-full border border-quest-gilt bg-quest-lapis-deep px-5 font-quest-sans font-bold text-quest-soot">
            Try again
          </button>
        </div>
      );
    }
    if (writing) {
      return <OwnWords busy={busy} onSend={(t) => say(t)} onCancel={() => setWriting(false)} />;
    }
    if (inChoices && done) {
      return (
        <section aria-label="Your reply to Brannoc" className="mx-3 flex flex-col gap-2">
          <p className="mx-1.5 mb-1 font-quest text-lg italic text-quest-vellum [text-shadow:0_1px_8px_rgba(0,0,0,0.8)]">
            {showPicker ? 'Which road shall we walk back down?' : 'What do you say?'}
          </p>
          {showPicker ? (
            <>
              {quests.slice(0, 3).map((q) => (
                <button key={q.campaign_id} type="button" disabled={busy} onClick={() => say('', q.campaign_id)} className={choiceBase}>
                  <span className="block">{q.title}</span>
                  <span className="block font-quest-sans text-[13px] text-quest-vellum-dim">
                    {questLine(q)}
                    {q.real_name ? ` · ${q.real_name}` : ''}
                  </span>
                </button>
              ))}
              <button type="button" disabled={busy} onClick={() => say('', HABITS_TOPIC)} className={choiceBase}>
                My habits across all quests
              </button>
            </>
          ) : (
            done.suggestions.map((s) => (
              <button key={s} type="button" disabled={busy} onClick={() => say(s)} className={choiceBase}>
                {s}
              </button>
            ))
          )}
          <button type="button" disabled={busy} onClick={() => setWriting(true)} className={`${choiceBase} border-dashed italic text-quest-vellum-dim`}>
            Write your own…
          </button>
          <div className="flex flex-wrap gap-2 pt-1">
            {questTopic !== null ? (
              <button
                type="button"
                onClick={() => onTimeline(questTopic)}
                className={`min-h-11 flex-1 rounded-full border px-3 font-quest-sans text-sm ${
                  done.show_timeline ? 'border-quest-gilt bg-quest-gilt/15 text-quest-gilt' : 'border-quest-gilt/50 text-quest-gilt'
                }`}
              >
                Decision timeline
              </button>
            ) : null}
            {overview?.has_memory && !showPicker ? (
              <button type="button" onClick={() => setPicking(true)} className="min-h-11 flex-1 rounded-full border border-quest-gilt/50 px-3 font-quest-sans text-sm text-quest-gilt">
                Another road
              </button>
            ) : null}
            <button type="button" onClick={onClose} className="min-h-11 flex-1 rounded-full border border-quest-vellum-dim/50 px-3 font-quest-sans text-sm text-quest-vellum-dim">
              Leave the fire
            </button>
          </div>
        </section>
      );
    }
    return (
      <DialogueBox
        key={key}
        speaker={VETERAN_NAME}
        text={state.phase === 'streaming' || state.phase === 'done' ? state.text : ''}
        final={!busy}
        writing={busy || state.phase === 'idle'}
        writingLabel="Brannoc puffs on his pipe…"
        onAdvance={() => setAdvancedKey(key)}
        onPageShown={onPageShown}
        audioTextId={done?.audio_text_id ?? null}
      />
    );
  })();

  return (
    <section aria-label="Brannoc, the Veteran" className="relative">
      <div data-testid="veteran-figure" className="pointer-events-none absolute bottom-full left-0 mb-1 w-[50%] max-w-[210px] animate-summon motion-reduce:animate-none">
        <VeteranPortrait bare glowing mood={mood} className="block h-auto w-full" />
      </div>
      {body}
    </section>
  );
}

function OwnWords({ busy, onSend, onCancel }: { busy: boolean; onSend: (text: string) => void; onCancel: () => void }): React.JSX.Element {
  const [text, setText] = useSessionDraft(VETERAN_DRAFT_KEY);
  const empty = text.trim() === '';
  const submit = (): void => {
    if (empty || busy) return;
    const out = text.trim();
    setText('');
    onSend(out);
  };
  return (
    <form
      aria-label="Your own words to Brannoc"
      className="mx-3 flex flex-col gap-2 rounded-lg bg-quest-lapis/95 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label htmlFor="veteran-words" className="font-quest text-lg italic text-quest-vellum">
        What do you tell Brannoc?
      </label>
      <textarea
        id="veteran-words"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        rows={3}
        maxLength={400}
        className="w-full resize-none rounded-md border border-quest-wax-light/50 bg-quest-soot/60 p-3 font-quest text-base text-quest-vellum"
      />
      <div className="flex gap-2">
        <button type="button" onClick={onCancel} className="min-h-11 rounded-full border border-quest-vellum-dim/50 px-4 font-quest-sans text-quest-vellum-dim">
          Back
        </button>
        <button type="submit" disabled={empty || busy} className="min-h-11 flex-1 rounded-full border border-quest-gilt bg-quest-lapis-deep px-4 font-quest-sans font-bold text-quest-soot disabled:opacity-40">
          Say it
        </button>
      </div>
    </form>
  );
}

/** The chip in the Tavern's top row. */
export function VeteranChip({ onClick }: { onClick: () => void }): React.JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex min-h-11 items-center gap-2 rounded-full border border-quest-gilt/60 bg-quest-soot/50 py-1 pl-1.5 pr-4 font-quest-sans text-sm text-quest-gilt"
    >
      <VeteranToken size={30} />
      Talk to Brannoc
    </button>
  );
}
