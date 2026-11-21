import { useEffect, useRef, useState } from 'react';
import type { DiceCard, DiceMode, RollResult } from '../../api/types';
import Die3D from './Die3D';
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
  /**
   * Coming back to a setback that was never resolved (the state only says "rolling"): show the
   * same Setback card without a new roll. The server's pending roll is the only source.
   */
  resumeSetback?: { rerollsLeft: number };
}

type Stage =
  | { name: 'resumed' }
  | { name: 'offer' }
  | { name: 'tumbling' }
  | { name: 'result'; roll: RollResult }
  | { name: 'failed' };

const pause = (ms: number): Promise<void> => new Promise((r) => window.setTimeout(r, ms));

/** Full-screen dice check. Every number on it comes from the API. */
export default function DiceMoment({ card, api, onResolved, resumeSetback }: DiceMomentProps): React.JSX.Element {
  const [stage, setStage] = useState<Stage>(resumeSetback ? { name: 'resumed' } : { name: 'offer' });
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

      {stage.name === 'resumed' && resumeSetback ? (
        <>
          <p className="font-quest-sans text-quest-vellum-dim">Difficulty {card.dc}</p>
          <p data-testid="dice-verdict" className="mt-2 font-quest-title text-5xl text-quest-wax-light">
            Setback
          </p>
          <div className="mt-6 flex flex-col items-center gap-3">
            {resumeSetback.rerollsLeft > 0 ? (
              <button
                type="button"
                onClick={() => void run(() => api.reroll(card.roll_id))}
                className="min-h-11 rounded-full border border-quest-gilt bg-quest-gilt px-6 font-quest-sans font-bold text-quest-soot"
              >
                Second Look — reroll ({resumeSetback.rerollsLeft} left)
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => void api.accept(card.roll_id).then(onResolved)}
              className="min-h-11 rounded-full border border-quest-vellum/40 px-6 font-quest-sans font-bold text-quest-vellum"
            >
              {resumeSetback.rerollsLeft > 0 ? 'Accept setback' : 'Continue'}
            </button>
          </div>
        </>
      ) : null}

      {/* One die from the throw to the result, so it can settle onto the rolled face. */}
      {stage.name === 'tumbling' || result !== null ? (
        <div
          role={stage.name === 'tumbling' ? 'status' : undefined}
          aria-label={stage.name === 'tumbling' ? 'Rolling' : undefined}
          className={stage.name === 'tumbling' ? 'animate-tumble motion-reduce:animate-none' : critClass(result)}
        >
          <Die3D value={result?.used ?? null} />
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
    // fades in once the die has settled (SETTLE_MS)
    <div className="flex animate-dice-reveal flex-col items-center motion-reduce:animate-none">
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
    </div>
  );
}

/** A natural 20 glows gold and a natural 1 shudders, once the die has settled. */
function critClass(roll: RollResult | null): string | undefined {
  if (roll?.used === 20) return 'animate-crit-glow motion-reduce:animate-none';
  if (roll?.used === 1) return 'animate-crit-shake motion-reduce:animate-none';
  return undefined;
}
