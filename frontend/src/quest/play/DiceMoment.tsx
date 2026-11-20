import { useEffect, useRef, useState } from 'react';
import type { DiceCard, DiceMode, RollResult } from '../../api/types';
import { prefersReducedMotion } from './useTypewriter';

export const TUMBLE_MS = 1000;

export interface DiceApi {
  roll: (mode: DiceMode) => Promise<RollResult>;
  reroll: (rollId: string) => Promise<RollResult>;
  accept: (rollId: string) => Promise<RollResult>;
}

interface DiceMomentProps {
  card: DiceCard;
  api: DiceApi;
  /** The result is final (Continue, Accept, or a Second Look). The narration follows. */
  onResolved: (final: RollResult) => void;
}

type Stage =
  | { name: 'offer' }
  | { name: 'tumbling' }
  | { name: 'result'; roll: RollResult }
  | { name: 'failed' };

const pause = (ms: number): Promise<void> => new Promise((r) => window.setTimeout(r, ms));

/** Full-screen dice check. Every number on it comes from the API. */
export default function DiceMoment({ card, api, onResolved }: DiceMomentProps): React.JSX.Element {
  const [stage, setStage] = useState<Stage>({ name: 'offer' });
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = async (call: () => Promise<RollResult>): Promise<RollResult | null> => {
    setStage({ name: 'tumbling' });
    try {
      const [roll] = await Promise.all([call(), prefersReducedMotion() ? Promise.resolve() : pause(TUMBLE_MS)]);
      if (mounted.current) setStage({ name: 'result', roll });
      return roll;
    } catch {
      if (mounted.current) setStage({ name: 'failed' });
      return null;
    }
  };

  const roll = (mode: DiceMode): void => void run(() => api.roll(mode));
  const keenEye = card.keen_eye_available && card.keen_eye_left > 0;

  const result = stage.name === 'result' ? stage.roll : null;
  const offerReroll = result !== null && !result.final && result.options.includes('reroll');

  return (
    <div role="dialog" aria-modal="true" aria-label="Dice check" className="absolute inset-0 z-[28] flex flex-col items-center justify-center bg-quest-soot/75 px-7 text-center">
      <p className="mb-6 max-w-[30ch] font-quest text-[19px] italic leading-snug text-quest-vellum">{card.title}</p>

      {stage.name === 'offer' || stage.name === 'failed' ? (
        <>
          <p className="font-quest-sans text-quest-vellum-dim">
            Difficulty {card.dc} <span aria-hidden="true">·</span> Bonus +{card.bonus}
          </p>
          {stage.name === 'failed' ? (
            <p role="alert" className="mt-2 font-quest text-quest-wax-light">
              The dice would not roll. Try again.
            </p>
          ) : null}
          <div className="mt-6 flex flex-col items-center gap-3">
            <button type="button" onClick={() => roll('normal')} className="min-h-11 rounded-full border border-quest-gilt bg-quest-gilt px-8 font-quest-sans text-base font-bold text-quest-soot">
              Roll
            </button>
            {keenEye ? (
              <button type="button" onClick={() => roll('advantage')} className="min-h-11 rounded-full border border-quest-vellum/40 px-5 font-quest-sans text-base font-bold text-quest-vellum">
                Keen Eye — roll with advantage ({card.keen_eye_left} left)
              </button>
            ) : null}
          </div>
        </>
      ) : null}

      {stage.name === 'tumbling' ? (
        <div role="status" aria-label="Rolling" className="animate-tumble motion-reduce:animate-none">
          <D20 face="?" />
        </div>
      ) : null}

      {result !== null ? <Result roll={result} offerReroll={offerReroll} onResolved={onResolved} run={run} api={api} /> : null}
    </div>
  );
}

interface ResultProps {
  roll: RollResult;
  offerReroll: boolean;
  onResolved: (final: RollResult) => void;
  run: (call: () => Promise<RollResult>) => Promise<RollResult | null>;
  api: DiceApi;
}

function Result({ roll, offerReroll, onResolved, run, api }: ResultProps): React.JSX.Element {
  const success = roll.result === 'success';
  const natural = roll.used === 20 ? 'Natural 20' : roll.used === 1 ? 'Natural 1' : null;
  return (
    <>
      <D20 face={String(roll.used ?? '')} />
      {roll.dice.length > 1 ? (
        <p className="mt-2 font-quest-sans text-sm text-quest-vellum-dim">
          Two dice: {roll.dice.join(' and ')}. The higher one counts.
        </p>
      ) : null}
      {natural ? <p className="mt-1 font-quest-sans text-sm font-bold text-quest-gilt">{natural}</p> : null}
      <p data-testid="dice-sum" className="mt-5 font-quest text-xl font-bold text-quest-vellum">
        {roll.used} + {roll.bonus} = {roll.total} <span className="font-normal text-quest-vellum-dim">against {roll.dc}</span>
      </p>
      <p data-testid="dice-verdict" className={`mt-2 font-quest-title text-5xl ${success ? 'text-quest-verdigris-light' : 'text-quest-wax-light'}`}>
        {success ? 'Success' : 'Setback'}
      </p>
      <div className="mt-6 flex flex-col items-center gap-3">
        {offerReroll ? (
          <>
            <button
              type="button"
              onClick={() => void run(() => api.reroll(roll.roll_id))}
              className="min-h-11 rounded-full border border-quest-gilt bg-quest-gilt px-6 font-quest-sans font-bold text-quest-soot"
            >
              Second Look — reroll ({roll.rerolls_left} left)
            </button>
            <button
              type="button"
              onClick={() => void api.accept(roll.roll_id).then(onResolved)}
              className="min-h-11 rounded-full border border-quest-vellum/40 px-6 font-quest-sans font-bold text-quest-vellum"
            >
              Accept setback
            </button>
          </>
        ) : (
          <button type="button" onClick={() => onResolved(roll)} className="min-h-11 rounded-full border border-quest-gilt bg-quest-gilt px-8 font-quest-sans font-bold text-quest-soot">
            Continue
          </button>
        )}
      </div>
    </>
  );
}

function D20({ face }: { face: string }): React.JSX.Element {
  return (
    <svg viewBox="0 0 160 160" width={150} height={150} role="img" aria-label={`Twenty-sided die showing ${face}`} className="drop-shadow-[0_12px_24px_rgba(0,0,0,0.6)]">
      <polygon points="80,6 148,44 148,116 80,154 12,116 12,44" fill="#8c6a2a" />
      <polygon points="80,6 148,44 80,62 12,44" fill="#b48a3c" />
      <polygon points="12,44 80,62 46,124 12,116" fill="#6f5222" />
      <polygon points="148,44 148,116 114,124 80,62" fill="#7c5c26" />
      <polygon points="80,62 114,124 46,124" fill="#c9a227" />
      <polygon points="46,124 114,124 80,154" fill="#5e451c" />
      <text x="80" y="110" textAnchor="middle" fontFamily="Alegreya, serif" fontWeight="700" fontSize="34" fill="#15121A">
        {face}
      </text>
    </svg>
  );
}
