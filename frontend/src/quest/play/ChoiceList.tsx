import type { Purse } from '../../api/types';
import { PurseLine } from './DecisionCards';
import { ACTION_DRAFT_KEY, useSessionDraft } from './useSessionDraft';

export interface ChoiceListProps {
  /** The question above the input; a decision scene asks about the coins. */
  prompt?: string;
  /** Shown under the question while a decision scene is open. */
  purse?: Purse;
  /** Show "I'm ready to decide". */
  canDecide: boolean;
  /** Freeze every button while a request is in flight. */
  busy?: boolean;
  onSend: (text: string) => void;
  onDecide: () => void;
}

/** After the Campaign Master's last page: the player writes what they do (no preset options). */
export default function ChoiceList({
  prompt = 'What would you do?',
  purse,
  canDecide,
  busy = false,
  onSend,
  onDecide,
}: ChoiceListProps): React.JSX.Element {
  return (
    <section aria-label="Choices" className="mx-3 flex flex-col gap-2">
      <ActionInput label={prompt} busy={busy} onSend={onSend}>
        {purse ? <PurseLine purse={purse} className="text-quest-vellum" /> : null}
      </ActionInput>
      {canDecide ? (
        <button
          type="button"
          disabled={busy}
          onClick={onDecide}
          className="min-h-11 w-full rounded-[4px_12px_12px_4px] border border-l-[3px] border-quest-gilt/60 border-l-quest-gilt bg-quest-lapis/90 px-3.5 py-3 text-left font-quest text-[17px] leading-snug text-[#f3e6c4] disabled:opacity-50"
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
  /** Shown as a "Back" button when given. */
  onCancel?: () => void;
  label?: string;
  /** Extra lines under the label (the purse in a decision scene). */
  children?: React.ReactNode;
}

export function ActionInput({ busy, onSend, onCancel, label = 'What would you do?', children }: ActionInputProps): React.JSX.Element {
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
      aria-label="Your own action"
      className="mx-3 flex flex-col gap-2 rounded-lg bg-quest-lapis/95 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label htmlFor="own-action" className="font-quest text-lg italic text-quest-vellum">
        {label}
      </label>
      {children}
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
        rows={3}
        maxLength={400}
        // 16px or more keeps iOS from zooming the page on focus
        className="w-full resize-none rounded-md border border-quest-verdigris-light/50 bg-quest-soot/60 p-3 font-quest text-base text-quest-vellum"
      />
      <div className="flex gap-2">
        {onCancel ? (
          <button type="button" onClick={onCancel} className="min-h-11 rounded-full border border-quest-vellum-dim/50 px-4 font-quest-sans text-quest-vellum-dim">
            Back
          </button>
        ) : null}
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
