import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCreateHero } from '../../api/campaign';
import { ApiError } from '../../api/client';
import type { HeroClass } from '../../api/types';
import { NAME_MAX, validateName, type NameError } from '../lib/heroName';

const nameMessages: Record<NonNullable<NameError>, string> = {
  length: 'Name must be 2–20 characters.',
  characters: 'Use letters, numbers, spaces, hyphens and apostrophes only.',
};

interface ClassCard {
  id: HeroClass;
  name: string;
  tagline: string;
  advantage: string;
}

const classes: readonly ClassCard[] = [
  {
    id: 'guardian',
    name: 'The Guardian',
    tagline: 'Keeps a safety cushion',
    advantage: 'Safety Cushion — start each campaign with 120 HP (€1,200)',
  },
  {
    id: 'analyst',
    name: 'The Analyst',
    tagline: 'Always takes a second look',
    advantage: 'Second Look — reroll one failed dice check per campaign',
  },
  {
    id: 'investigator',
    name: 'The Investigator',
    tagline: 'Has a keen eye for clues',
    advantage: 'Keen Eye — roll one dice check per campaign with advantage',
  },
];

export default function HeroCreate(): React.JSX.Element {
  const navigate = useNavigate();
  const createHero = useCreateHero();
  const [name, setName] = useState('Lena');
  const [heroClass, setHeroClass] = useState<HeroClass | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const nameError = validateName(name);
  const canBegin = nameError === null && heroClass !== null && !createHero.isPending;

  const begin = async (): Promise<void> => {
    if (heroClass === null || nameError !== null) return;
    setFailed(null);
    try {
      await createHero.mutateAsync({ name: name.trim(), class: heroClass });
      void navigate('/quest/interests', { replace: true, state: { newHero: true } });
    } catch (e: unknown) {
      if (e instanceof ApiError && e.kind === 'Conflict') void navigate('/quest', { replace: true });
      else setFailed('Could not create your hero. Please try again.');
    }
  };

  return (
    <form
      className="space-y-5 pb-6 font-quest text-quest-vellum"
      onSubmit={(e) => {
        e.preventDefault();
        void begin();
      }}
    >
      <h1 className="font-quest-title text-4xl text-quest-gilt">Create your hero</h1>
      <div>
        <label htmlFor="hero-name" className="mb-1 block font-quest-sans text-sm text-quest-vellum-dim">
          Name
        </label>
        <input
          id="hero-name"
          type="text"
          value={name}
          maxLength={NAME_MAX}
          autoComplete="off"
          onChange={(e) => setName(e.target.value)}
          aria-invalid={nameError !== null}
          aria-describedby={nameError ? 'hero-name-error' : undefined}
          className="min-h-11 w-full rounded-md border border-quest-gilt bg-quest-lapis-deep px-3 font-quest text-base text-quest-vellum"
        />
        {nameError ? (
          <p id="hero-name-error" role="alert" className="mt-1 font-quest-sans text-sm text-quest-wax-light">
            {nameMessages[nameError]}
          </p>
        ) : null}
      </div>
      <div role="radiogroup" aria-label="Choose your class" className="space-y-3">
        {classes.map((c) => {
          const selected = heroClass === c.id;
          return (
            <button
              key={c.id}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => setHeroClass(c.id)}
              className={`block w-full rounded-lg border-2 p-4 text-left ${
                selected
                  ? 'border-quest-gilt bg-quest-lapis'
                  : 'border-quest-lapis bg-quest-lapis-deep'
              }`}
            >
              <span className="block font-quest-title text-2xl text-quest-gilt">{c.name}</span>
              <span className="block font-quest-sans text-sm italic text-quest-vellum-dim">{c.tagline}</span>
              <span className="mt-1 block">{c.advantage}</span>
            </button>
          );
        })}
      </div>
      {failed ? (
        <p role="alert" className="font-quest-sans text-sm text-quest-wax-light">
          {failed}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={!canBegin}
        className="min-h-11 w-full rounded-md bg-quest-verdigris px-5 font-quest-sans text-lg font-bold text-quest-vellum disabled:opacity-40"
      >
        Begin
      </button>
    </form>
  );
}
