import type { NewsCard } from '../../api/types';

interface BreakingNewsCardProps {
  card: NewsCard;
  onContinue: () => void;
}

/** A pinned broadsheet notice. Headline and summary are anonymized by the server. */
export default function BreakingNewsCard({ card, onContinue }: BreakingNewsCardProps): React.JSX.Element {
  return (
    <div className="absolute inset-0 z-[26] flex items-center bg-quest-soot/70 px-5">
      <article aria-label="Breaking news" className="w-full rotate-[-1deg] rounded-md bg-quest-vellum p-5 text-quest-soot shadow-[0_20px_60px_rgba(0,0,0,0.6)]">
        <p className="font-quest-sans text-xs font-bold uppercase tracking-widest text-quest-wax">Breaking news</p>
        <h2 className="mt-1 font-quest-title text-3xl leading-tight text-quest-lapis">{card.headline}</h2>
        <p className="mt-2 font-quest text-[17px] leading-snug">{card.summary}</p>
        <button type="button" onClick={onContinue} className="mt-4 min-h-11 rounded-full bg-quest-lapis px-6 font-quest-sans font-bold text-quest-vellum">
          Continue
        </button>
      </article>
    </div>
  );
}
