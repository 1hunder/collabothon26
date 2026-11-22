import { useState } from 'react';
import type { BoardSuggestion } from '../../api/types';
import ParchmentSheet from './ParchmentSheet';

interface CommissionSheetProps {
  suggestion: BoardSuggestion;
  busy: boolean;
  failed: boolean;
  /** `theme` is undefined when the player accepts the suggestion. */
  onCommission: (theme?: string) => void;
  onClose: () => void;
}

/** Ask the scribe for a new quest: take the suggestion from the player's spending, or name a theme. */
export default function CommissionSheet({ suggestion, busy, failed, onCommission, onClose }: CommissionSheetProps): React.JSX.Element {
  const [theme, setTheme] = useState('');
  const typed = theme.trim();
  return (
    <ParchmentSheet title="Commission a new quest" onClose={onClose}>
      <h3 className="qb-h">Based on your spending</h3>
      <p className="text-xl font-bold">{suggestion.category_label}</p>
      <p className="text-lg leading-snug">{suggestion.why}</p>
      <div className="mt-3">
        <button type="button" data-autofocus className="qb-btn" disabled={busy} onClick={() => onCommission()}>
          Use this
        </button>
      </div>

      <form
        className="mt-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (typed) onCommission(typed);
        }}
      >
        <label htmlFor="qb-theme" className="qb-h block" style={{ marginTop: 0 }}>
          Or tell me what you&apos;d like
        </label>
        <input
          id="qb-theme"
          className="qb-input"
          value={theme}
          maxLength={60}
          placeholder="e.g. electric cars, music…"
          onChange={(e) => setTheme(e.target.value)}
        />
        <div className="mt-3">
          <button type="submit" className="qb-btn quiet" disabled={busy || typed === ''}>Commission</button>
        </div>
      </form>
      {failed ? <p role="alert" className="mt-3 text-lg font-bold">The scribe could not take your order. Try again.</p> : null}
    </ParchmentSheet>
  );
}
