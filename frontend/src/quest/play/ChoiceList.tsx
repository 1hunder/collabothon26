import type { Purse } from '../../api/types';
import { PurseLine } from './DecisionCards';
import { ACTION_DRAFT_KEY, useSessionDraft } from './useSessionDraft';

export interface ChoiceListProps {
  /** The question above the input; a decision scene asks about the coins. */
  prompt?: string;
  mascot?: React.ReactNode;
  /** Shown under the question while a decision scene is open. */
  purse?: Purse;
  /** Show "I'm ready to decide". */
  canDecide: boolean;
  /** The curious trader asked why: the next message is the player's reasoning. */
  awaitingReasoning?: boolean;
  /** Freeze every button while a request is in flight. */
  busy?: boolean;
  onSend: (text: string) => void;
  onDecide: () => void;
  /** Shown in a decision scene: leave it without trading (it comes back when the player decides). */
  onLeave?: () => void;
  /** Bring back the reply just read, to read it again (a tap went past it too fast). */
  onReread?: () => void;
}

const buttonBase =
  'min-h-11 w-full rounded-[4px_12px_12px_4px] border border-l-[3px] border-quest-verdigris-light/50 border-l-quest-verdigris bg-quest-lapis/90 px-3.5 py-3 text-left font-quest text-[17px] leading-snug text-quest-vellum disabled:opacity-50';

/** The player's turn: a text input is the only way to answer. */
export default function ChoiceList({
  prompt = 'What would you do?',
  mascot,
  purse,
  canDecide,
  awaitingReasoning = false,
  busy = false,
  onSend,
  onReread,
  onDecide,
  onLeave,
}: ChoiceListProps): React.JSX.Element {
  return (
    <section aria-label="Your turn" className="mx-3 flex flex-col gap-2">
      {onReread ? (
        <button
          type="button"
          onClick={onReread}
          className="mx-1.5 flex min-h-9 items-center gap-1.5 self-start rounded-full bg-quest-soot/60 px-3 font-quest-sans text-sm text-quest-vellum hover:bg-quest-soot/80"
        >
          <span aria-hidden="true" className="text-quest-gilt">◀</span> Read again
        </button>
      ) : null}
      <div className="relative">
        <ActionInput
          prompt={awaitingReasoning ? 'Why did you choose that?' : prompt}
          placeholder={awaitingReasoning ? 'Your reasoning, in your own words…' : undefined}
          busy={busy}
          onSend={onSend}
        />
        {mascot}
      </div>
      {onLeave ? (
        <button
          type="button"
          disabled={busy}
          onClick={onLeave}
          className="mx-1.5 flex min-h-11 items-center gap-1.5 self-start rounded-full border border-quest-gilt/50 bg-quest-soot/60 px-4 font-quest-sans text-sm text-quest-vellum hover:bg-quest-soot/80 disabled:opacity-50"
        >
          <span aria-hidden="true" className="text-quest-gilt">✕</span> Leave without trading
        </button>
      ) : null}
      {purse ? <PurseLine purse={purse} className="mx-1.5 mb-1 text-quest-vellum [text-shadow:0_1px_8px_rgba(0,0,0,0.8)]" /> : null}
      {canDecide ? (
        <button
          type="button"
          disabled={busy}
          onClick={onDecide}
          className={`${buttonBase} !border-quest-gilt/60 !border-l-quest-gilt text-[#f3e6c4]`}
        >
          I&apos;m ready to decide
        </button>
      ) : null}
    </section>
  );
}

interface ActionInputProps {
  busy: boolean;
  onSend: (text: string) => void;
  prompt: string;
  placeholder?: string;
}

export function ActionInput({ busy, onSend, prompt, placeholder = 'What do you do?' }: ActionInputProps): React.JSX.Element {
  const [text, setText] = useSessionDraft(ACTION_DRAFT_KEY);
  const empty = text.trim() === '';
  const submit = (): void => {
    if (empty || busy) return;
    const out = text.trim();
    setText('');
    onSend(out);
  };
  return (
    <form
      aria-label="Your action"
      className="mx-3 flex flex-col gap-2 rounded-lg bg-quest-lapis/95 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label htmlFor="own-action" className="font-quest text-lg italic text-quest-vellum">
        {prompt}
      </label>
      <textarea
        id="own-action"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        rows={2}
        placeholder={placeholder}
        maxLength={400}
        // 16px or more keeps iOS from zooming the page on focus
        className="w-full resize-none rounded-md border border-quest-verdigris-light/50 bg-quest-soot/60 p-3 font-quest text-base text-quest-vellum"
      />
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={empty || busy}
          className="min-h-11 flex-1 rounded-full border border-quest-gilt bg-quest-lapis-deep px-4 font-quest-sans font-bold text-quest-soot disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </form>
  );
}
