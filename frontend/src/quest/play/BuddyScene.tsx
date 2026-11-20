import type { DmStream } from '../../api/useDmStream';
import BuddyToken from './BuddyToken';
import DialogueBox, { BUDDY_NAME, type VoiceKind } from './DialogueBox';
import { BUDDY_DRAFT_KEY, useSessionDraft } from './useSessionDraft';

export const BUDDY_GREETING =
  'Ask me anything about what you see. I can explain words and numbers, but the decision is yours.';

interface BuddySceneProps {
  stream: DmStream;
  onClose: () => void;
  /** VOICE HOOK, same contract as DialogueBox.onPageShown. */
  onPageShown?: (text: string, voice: VoiceKind) => void;
  onAsked?: () => void;
}

/**
 * CommerzBuddy on call: the token sits beside the dialogue box, Buddy speaks under the verdigris
 * name tab, and a question box is open. Closing keeps the typed draft (sessionStorage).
 */
export default function BuddyScene({ stream, onClose, onPageShown, onAsked }: BuddySceneProps): React.JSX.Element {
  const [draft, setDraft] = useSessionDraft(BUDDY_DRAFT_KEY);
  const { state } = stream;
  const empty = draft.trim() === '';
  const busy = state.phase === 'sending' || state.phase === 'streaming';

  const ask = (): void => {
    if (empty || busy) return;
    const text = draft.trim();
    setDraft('');
    onAsked?.();
    stream.send({ text });
  };

  const live = state.phase === 'streaming' || state.phase === 'done';
  const text = live ? state.text : state.phase === 'idle' ? BUDDY_GREETING : '';

  return (
    <section aria-label="CommerzBuddy" className="relative">
      <BuddyToken size={64} className="absolute -top-[72px] right-6 animate-summon motion-reduce:animate-none" />
      {state.phase === 'lost' ? (
        <div role="alert" className="mx-3 rounded-lg bg-quest-lapis/95 p-4 font-quest text-quest-vellum">
          <p>CommerzBuddy lost the thread.</p>
          <button type="button" onClick={stream.retry} className="mt-2 min-h-11 rounded-full bg-quest-gilt px-5 font-quest-sans font-bold text-quest-soot">
            Try again
          </button>
        </div>
      ) : (
        <DialogueBox
          key={state.phase === 'idle' ? 'greeting' : state.clientMsgId}
          speaker={BUDDY_NAME}
          text={text}
          final={state.phase !== 'streaming' && state.phase !== 'sending'}
          writing={busy}
          writingLabel="CommerzBuddy is thinking…"
          onAdvance={() => undefined}
          onPageShown={onPageShown}
        />
      )}
      <form
        aria-label="Ask CommerzBuddy"
        className="mx-3 mt-2 flex flex-col gap-2 rounded-lg bg-quest-lapis/95 p-3"
        onSubmit={(e) => {
          e.preventDefault();
          ask();
        }}
      >
        <label htmlFor="buddy-question" className="sr-only">
          Your question for CommerzBuddy
        </label>
        <textarea
          id="buddy-question"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={2}
          maxLength={400}
          placeholder="What would you like to understand?"
          className="w-full resize-none rounded-md border border-quest-verdigris-light/50 bg-quest-soot/60 p-3 font-quest text-base text-quest-vellum"
        />
        <div className="flex gap-2">
          <button type="button" onClick={onClose} className="min-h-11 rounded-full border border-quest-vellum-dim/50 px-4 font-quest-sans text-quest-vellum-dim">
            Close Buddy
          </button>
          <button
            type="submit"
            disabled={empty || busy}
            className="min-h-11 flex-1 rounded-full bg-quest-verdigris-light px-4 font-quest-sans font-bold text-quest-soot disabled:opacity-40"
          >
            Ask
          </button>
        </div>
      </form>
    </section>
  );
}
