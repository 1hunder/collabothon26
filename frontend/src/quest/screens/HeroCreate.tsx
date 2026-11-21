import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useChooseHeroClass, useCreateHero, useHero } from '../../api/campaign';
import { ApiError } from '../../api/client';
import type { HeroClass } from '../../api/types';
import { NAME_MAX, validateName, type NameError } from '../lib/heroName';
import type { QuestEntryState } from '../setupNavigation';

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

export default function HeroCreate({ chooseClass = false }: { chooseClass?: boolean }): React.JSX.Element {
  const navigate = useNavigate();
  const entry = useLocation().state as QuestEntryState | null;
  const hero = useHero();
  const createHero = useCreateHero();
  const updateClass = useChooseHeroClass();
  const savedHero = chooseClass || entry?.newHero ? hero.data : null;
  const reviewOnly = Boolean(savedHero) && !chooseClass;
  const continueToDisclosure = (): void => {
    void navigate('/quest/disclosure', { replace: true, state: { ...entry, newHero: !chooseClass, chooseClass } });
  };
  const [name, setName] = useState('Lena');
  const [heroClass, setHeroClass] = useState<HeroClass | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const nameError = validateName(name);
  const selectedClass = heroClass ?? savedHero?.class;
  const pending = createHero.isPending || updateClass.isPending;
  const canBegin = Boolean(selectedClass) && (savedHero ? !pending : nameError === null && !pending);

  const begin = async (): Promise<void> => {
    if (reviewOnly) {
      continueToDisclosure();
      return;
    }
    if (!selectedClass || !canBegin) return;
    setFailed(null);
    try {
      if (chooseClass) {
        if (selectedClass !== savedHero?.class) await updateClass.mutateAsync(selectedClass);
      } else {
        await createHero.mutateAsync({ name: name.trim(), class: selectedClass });
      }
      continueToDisclosure();
    } catch (e: unknown) {
      if (e instanceof ApiError && e.kind === 'Conflict') void navigate('/quest', { replace: true });
      else setFailed(chooseClass ? 'Could not save your class. Please try again.' : 'Could not create your hero. Please try again.');
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
      <h1 className="font-quest-title text-4xl text-quest-gilt">{chooseClass ? 'Choose your class' : 'Create your hero'}</h1>
      <div>
        <label htmlFor="hero-name" className="mb-1 block font-quest-sans text-sm text-quest-vellum-dim">
          Name
        </label>
        <input
          id="hero-name"
          type="text"
          value={savedHero?.name ?? name}
          readOnly={Boolean(savedHero)}
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
          const selected = selectedClass === c.id;
          return (
            <button
              key={c.id}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={reviewOnly || pending}
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
        className="min-h-11 w-full rounded-md border border-quest-gilt/70 bg-quest-lapis-deep px-5 font-quest-sans text-lg font-bold text-quest-vellum disabled:opacity-40"
      >
        {savedHero ? 'Continue' : 'Begin'}
      </button>
    </form>
  );
}
