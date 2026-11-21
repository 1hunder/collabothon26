import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { useRef, useState } from 'react';
import type { CampaignState, KeyFigure } from '../../api/types';
import { formatStoryNumber } from '../lib/storyNumber';
import { useEscapeKey } from './useEscapeKey';

interface LibraryScrollProps {
  library: CampaignState['library'];
  onClose: () => void;
}

const show = (v: number | string): string => {
  const n = typeof v === 'string' && v.trim() !== '' ? Number(v) : v;
  return typeof n === 'number' && Number.isFinite(n) ? formatStoryNumber(n) : String(v);
};

function Figure({ f }: { f: KeyFigure }): React.JSX.Element {
  return (
    <li>
      <span className="font-medium">{f.label}</span>: {show(f.value)}
      {f.period ? <span className="text-[#6d6350]"> ({f.period})</span> : null}
      {f.explain ? <p className="text-sm italic text-[#5b5242]">{f.explain}</p> : null}
    </li>
  );
}

const parchment: React.CSSProperties = {
  backgroundColor: '#e8dcc2',
  backgroundImage: [
    'radial-gradient(ellipse at 50% 0%, rgba(255,250,235,0.7), transparent 60%)',
    'radial-gradient(ellipse at 0% 100%, rgba(120,88,40,0.28), transparent 55%)',
    'radial-gradient(ellipse at 100% 100%, rgba(120,88,40,0.28), transparent 55%)',
    'repeating-linear-gradient(8deg, rgba(110,84,44,0.05) 0 2px, transparent 2px 7px)',
  ].join(','),
  boxShadow: 'inset 0 0 0 3px #c9a227, inset 0 0 0 6px #e8dcc2, inset 0 0 0 7px #c9a227, inset 0 0 60px rgba(110,70,20,0.35)',
};

const SWIPE_PX = 50;

/** Library: a full-screen parchment. One page for the company card, then one per document. */
export default function LibraryScroll({ library, onClose }: LibraryScrollProps): React.JSX.Element {
  const card = library.company_card;
  const pages: { key: string; node: React.ReactNode }[] = [
    {
      key: 'card',
      node: (
        <section aria-label="Company card">
          <h3 className="font-quest-title text-3xl text-quest-lapis">{card.name}</h3>
          <p>{card.trade}</p>
          <p>{card.size}</p>
          {card.key_figures.length > 0 ? (
            <ul className="mt-3 space-y-1.5 text-base">
              {card.key_figures.map((f) => (
                <Figure key={f.id ?? f.label} f={f} />
              ))}
            </ul>
          ) : null}
        </section>
      ),
    },
    ...library.documents.map((d) => ({
      key: d.id,
      node: (
        <article aria-label={d.title}>
          <h3 className="font-quest-title text-3xl text-quest-lapis">{d.title}</h3>
          {d.entries.map((e) => (
            <p key={e.id} className="mt-2 text-base leading-snug">
              <b>{e.title}.</b> {e.text}
            </p>
          ))}
        </article>
      ),
    })),
  ];
  const [index, setIndex] = useState(0);
  const touchX = useRef<number | null>(null);
  const last = pages.length - 1;
  const go = (d: number): void => setIndex((i) => Math.min(last, Math.max(0, i + d)));
  useEscapeKey(onClose);

  return (
    <div className="absolute inset-0 z-30 bg-quest-soot/70">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Library"
        tabIndex={-1}
        data-testid="parchment"
        style={parchment}
        onKeyDown={(e) => {
          if (e.key === 'ArrowRight') go(1);
          if (e.key === 'ArrowLeft') go(-1);
        }}
        onTouchStart={(e) => {
          touchX.current = e.touches[0]?.clientX ?? null;
        }}
        onTouchEnd={(e) => {
          const start = touchX.current;
          const end = e.changedTouches[0]?.clientX;
          touchX.current = null;
          if (start === null || end === undefined) return;
          if (start - end > SWIPE_PX) go(1);
          else if (end - start > SWIPE_PX) go(-1);
        }}
        className="absolute inset-2 flex flex-col rounded-lg font-quest text-quest-soot"
      >
        {/* Close sits top-left: the quest layout's own "Close quest" button owns the top-right corner. */}
        <header className="flex items-start gap-1 px-3 pt-4">
          <button type="button" aria-label="Close Library" onClick={onClose} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-quest-lapis-deep">
            <X aria-hidden="true" size={22} />
          </button>
          <div className="pr-12">
            <h2 className="font-quest-title text-2xl text-quest-wax">Library</h2>
            <p className="text-base italic text-[#5b5242]">The guild&apos;s records, as far as they reach today</p>
          </div>
        </header>
        <div key={pages[index]?.key} data-testid="parchment-page" className="min-h-0 flex-1 overflow-y-auto px-7 pb-4 pt-3">
          {pages[index]?.node}
          {library.documents.length === 0 ? <p className="mt-3">No documents yet.</p> : null}
        </div>
        <footer className="flex items-center justify-between px-4 pb-4">
          <button type="button" aria-label="Previous page" disabled={index === 0} onClick={() => go(-1)} className="flex h-11 w-11 items-center justify-center rounded-full bg-quest-lapis-deep disabled:opacity-30">
            <ChevronLeft aria-hidden="true" size={26} />
          </button>
          <p aria-live="polite" className="font-quest-sans text-sm text-[#5b5242]">
            Page {index + 1} of {pages.length}
          </p>
          <button type="button" aria-label="Next page" disabled={index === last} onClick={() => go(1)} className="flex h-11 w-11 items-center justify-center rounded-full bg-quest-lapis-deep disabled:opacity-30">
            <ChevronRight aria-hidden="true" size={26} />
          </button>
        </footer>
      </div>
    </div>
  );
}
