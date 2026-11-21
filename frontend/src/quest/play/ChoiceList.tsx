import { useState } from 'react';
import type { Purse } from '../../api/types';
import { PurseLine } from './DecisionCards';
import { ACTION_DRAFT_KEY, useSessionDraft } from './useSessionDraft';

export interface ChoiceListProps {
  suggestions: readonly string[];
  /** The question above the choices; a decision scene asks about the coins. */
  prompt?: string;
  /** Shown under the question while a decision scene is open. */
  purse?: Purse;
  /** Show "I'm ready to decide". */
  canDecide: boolean;
  focusLeft: number;
  bonusLeadAvailable: boolean;
  /** Freeze every button while a request is in flight. */
  busy?: boolean;
  onSend: (text: string) => void;
  onDecide: () => void;
  onHint: () => void;
  onBonusLead: () => void;
}

const choiceBase =
  'min-h-11 w-full rounded-[4px_12px_12px_4px] border border-l-[3px] border-quest-verdigris-light/50 border-l-quest-verdigris bg-quest-lapis/90 px-3.5 py-3 text-left font-quest text-[17px] leading-snug text-quest-vellum disabled:opacity-50';

export default function ChoiceList({
  suggestions,
  prompt = 'What would you do?',
  purse,
  canDecide,
  focusLeft,
  bonusLeadAvailable,
  busy = false,
  onSend,
  onDecide,
  onHint,
  onBonusLead,
}: ChoiceListProps): React.JSX.Element {
  const [writing, setWriting] = useState(false);

  if (writing) {
    return <ActionInput busy={busy} onSend={onSend} onCancel={() => setWriting(false)} />;
  }

  return (
    <section aria-label="Choices" className="mx-3 flex flex-col gap-2">
      <p className="mx-1.5 mb-1 font-quest text-lg italic text-quest-vellum [text-shadow:0_1px_8px_rgba(0,0,0,0.8)]">
        {prompt}
      </p>
      {purse ? <PurseLine purse={purse} className="mx-1.5 mb-1 text-quest-vellum [text-shadow:0_1px_8px_rgba(0,0,0,0.8)]" /> : null}
      {suggestions.map((s) => (
        <button key={s} type="button" disabled={busy} onClick={() => onSend(s)} className={choiceBase}>
          {s}
        </button>
      ))}
      <button
        type="button"
        disabled={busy}
        onClick={() => setWriting(true)}
        className={`${choiceBase} border-dashed italic text-quest-vellum-dim`}
      >
        Write your own action…
      </button>
      {canDecide ? (
        <button
          type="button"
          disabled={busy}
          onClick={onDecide}
          className={`${choiceBase} !border-quest-gilt/60 !border-l-quest-gilt text-[#f3e6c4]`}
        >
          I&apos;m ready to decide
        </button>
      ) : null}
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          disabled={busy || focusLeft <= 0}
          onClick={onHint}
          className="min-h-11 flex-1 rounded-full border border-quest-gilt/50 px-3 font-quest-sans text-sm text-quest-gilt disabled:opacity-40"
        >
          Ask for a hint
        </button>
        <button
          type="button"
          disabled={busy || focusLeft <= 0 || !bonusLeadAvailable}
          onClick={onBonusLead}
          className="min-h-11 flex-1 rounded-full border border-quest-gilt/50 px-3 font-quest-sans text-sm text-quest-gilt disabled:opacity-40"
        >
          Chase a bonus lead
        </button>
      </div>
    </section>
  );
}

interface ActionInputProps {
  busy: boolean;
  onSend: (text: string) => void;
  onCancel: () => void;
}

export function ActionInput({ busy, onSend, onCancel }: ActionInputProps): React.JSX.Element {
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
        What would you do?
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
        rows={3}
        maxLength={400}
        // 16px or more keeps iOS from zooming the page on focus
        className="w-full resize-none rounded-md border border-quest-verdigris-light/50 bg-quest-soot/60 p-3 font-quest text-base text-quest-vellum"
      />
      <div className="flex gap-2">
        <button type="button" onClick={onCancel} className="min-h-11 rounded-full border border-quest-vellum-dim/50 px-4 font-quest-sans text-quest-vellum-dim">
          Back
        </button>
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
