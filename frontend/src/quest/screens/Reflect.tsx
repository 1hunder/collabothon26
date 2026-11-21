import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { patchCampaignCache, submitReflection } from '../../api/campaign';
import { REFLECTION_MIN } from '../lib/commit';
import { useActiveCampaign } from '../lib/useActiveCampaign';

/** `/quest/reflect`: the answer unlocks the company reveal (spec 002). */
export default function Reflect(): React.JSX.Element {
  const { id, campaign } = useActiveCampaign();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const valid = text.trim().length >= REFLECTION_MIN;
  const question = campaign?.debrief?.reflection_question ?? 'What would you check first next time?';

  const submit = async (): Promise<void> => {
    if (!valid || id === null) return;
    setBusy(true);
    setFailed(false);
    try {
      await submitReflection(id, text.trim());
      patchCampaignCache(qc, id, { phase: 'company' });
      void navigate('/quest/reveal', { replace: true });
    } catch {
      setFailed(true);
      setBusy(false);
    }
  };

  return (
    <form
      className="space-y-4 pb-8"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <h1 className="font-quest-title text-4xl text-quest-gilt">Reflection</h1>
      <label htmlFor="reflection" className="block text-lg">
        {question}
      </label>
      <textarea
        id="reflection"
        rows={5}
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="w-full rounded-md border border-quest-gilt bg-quest-lapis-deep p-3 text-base"
      />
      {failed ? (
        <p role="alert" className="font-quest-sans text-sm text-quest-wax-light">
          Could not submit your reflection. Please try again.
        </p>
      ) : null}
      <button
        type="submit"
        disabled={!valid || busy}
        className="min-h-11 w-full rounded-md bg-quest-verdigris px-5 font-quest-sans text-lg font-bold disabled:opacity-40"
      >
        Submit reflection
      </button>
    </form>
  );
}
