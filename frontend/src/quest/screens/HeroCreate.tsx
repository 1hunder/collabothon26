import { useRef, useState } from 'react';
import { Dices, MoveHorizontal } from 'lucide-react';
import shieldArt from '../../assets/01_shield_original.png';
import mapArt from '../../assets/02_map_original.png';
import booksArt from '../../assets/03_books_dice_original.png';
import './HeroCreate.css';
import { useLocation, useNavigate } from 'react-router-dom';
import { useChooseHeroClass, useCreateHero, useHero } from '../../api/campaign';
import { ApiError } from '../../api/client';
import type { HeroClass } from '../../api/types';
import { unlockVoice } from '../../voice';
import { NAME_MAX, validateName, type NameError } from '../lib/heroName';
import type { QuestEntryState } from '../setupNavigation';

const nameMessages: Record<NonNullable<NameError>, string> = {
  length: 'Name must be 2–20 characters.',
  characters: 'Use letters, numbers, spaces, hyphens and apostrophes only.',
};

interface ClassCard {
  id: HeroClass;
  name: string;
  art: string;
  tagline: string;
  advantage: string;
}

const classes: readonly ClassCard[] = [
  {
    id: 'analyst',
    art: booksArt,
    name: 'The Analyst',
    tagline: 'Always takes a second look',
    advantage: 'Second Look — reroll one failed dice check per campaign',
  },
  {
    id: 'guardian',
    art: shieldArt,
    name: 'The Guardian',
    tagline: 'Keeps a safety cushion',
    advantage: 'Safety Cushion — start each campaign with 120 HP (1,200 gp)',
  },
  {
    id: 'investigator',
    art: mapArt,
    name: 'The Investigator',
    tagline: 'Has a keen eye for clues',
    advantage: 'Keen Eye — roll one dice check per campaign with advantage',
  },
];

function ClassCarousel({ selected, disabled, onSelect }: {
  selected: HeroClass | undefined;
  disabled: boolean;
  onSelect: (id: HeroClass) => void;
}) {
  const current = classes.findIndex(card => card.id === (selected ?? 'guardian'));
  const group = useRef<HTMLDivElement>(null);
  const touch = useRef<{ x: number; y: number } | null>(null);
  const skipClick = useRef(false);
  const adjacent = (step: number) => (current + step + classes.length) % classes.length;

  return (
    <div className="class-carousel">
      <div
        ref={group}
        role="radiogroup"
        aria-label="Choose your class"
        className="class-stage"
        onPointerDown={event => {
          skipClick.current = false;
          touch.current = event.isPrimary ? { x: event.clientX, y: event.clientY } : null;
        }}
        onPointerCancel={() => { touch.current = null; }}
        onPointerUp={event => {
          const start = touch.current;
          touch.current = null;
          if (!start || disabled) return;
          const dx = event.clientX - start.x;
          if (Math.abs(dx) < 35 || Math.abs(dx) <= Math.abs(event.clientY - start.y)) return;
          skipClick.current = true;
          onSelect(classes[adjacent(dx < 0 ? 1 : -1)]!.id);
        }}
        onClickCapture={event => {
          if (skipClick.current && event.detail > 0) event.stopPropagation();
          skipClick.current = false;
        }}
        onKeyDown={event => {
          if (disabled || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
          event.preventDefault();
          const index = adjacent(event.key === 'ArrowRight' ? 1 : -1);
          onSelect(classes[index]!.id);
          group.current?.querySelectorAll('button')[index]?.focus({ preventScroll: true });
        }}
      >
        {classes.map((card, index) => (
          <button key={card.id} type="button" role="radio" aria-checked={selected === card.id}
            className="class-card" data-position={index === current ? 'center' : index === adjacent(1) ? 'right' : 'left'}
            tabIndex={index === current ? 0 : -1} disabled={disabled} onClick={() => onSelect(card.id)}>
            <img src={card.art} alt="" draggable={false} className="class-art" />
            <span className="class-title">{card.name}</span>
            <span aria-hidden="true" className="class-rule">✦</span>
            <span className="class-tagline">{card.tagline}</span>
            <span className="class-advantage">{card.advantage}</span>
          </button>
        ))}
      </div>
      <div className="flex justify-center">
        {classes.map((card, index) => (
          <button key={card.id} type="button" disabled={disabled} aria-label={`Show ${card.name}`}
            aria-current={index === current} className="class-dot" onClick={() => onSelect(card.id)} />
        ))}
      </div>
      {!disabled && <p className="text-center text-sm italic"><MoveHorizontal aria-hidden="true" className="mx-auto h-4 text-quest-gilt" />
        {selected ? 'Swipe to explore classes' : 'Swipe or tap a card to choose'}</p>}
    </div>
  );
}

export default function HeroCreate({ chooseClass = false }: { chooseClass?: boolean }): React.JSX.Element {
  const navigate = useNavigate();
  const entry = useLocation().state as QuestEntryState | null;
  const hero = useHero();
  const createHero = useCreateHero();
  const updateClass = useChooseHeroClass();
  const savedHero = chooseClass || entry?.newHero ? hero.data : null;
  const reviewOnly = Boolean(savedHero) && !chooseClass;
  const continueToDisclosure = (): void => {
    void navigate('/quest/board', { replace: true, state: { ...entry, newHero: !chooseClass, chooseClass } });
  };
  const [name, setName] = useState('Lena');
  const [heroClass, setHeroClass] = useState<HeroClass | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const nameError = validateName(name);
  const selectedClass = heroClass ?? savedHero?.class;
  const pending = createHero.isPending || updateClass.isPending;
  const canBegin = Boolean(selectedClass) && (savedHero ? !pending : nameError === null && !pending);

  const begin = async (): Promise<void> => {
    unlockVoice();
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
      <h1 className="text-center font-quest-title text-[2.65rem] leading-tight text-quest-gilt">{chooseClass ? 'Choose your class' : 'Create your hero'}</h1>
      <div className="class-heading-rule" aria-hidden="true"><Dices size={20} /></div>
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
      <ClassCarousel selected={selectedClass} disabled={reviewOnly || pending} onSelect={setHeroClass} />
      {failed ? (
        <p role="alert" className="font-quest-sans text-sm text-quest-wax-light">
          {failed}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={!canBegin}
        className="class-continue disabled:opacity-40"
      >
        {savedHero ? 'Continue' : 'Begin'}
      </button>
    </form>
  );
}
