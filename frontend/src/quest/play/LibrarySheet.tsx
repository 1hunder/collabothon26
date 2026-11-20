import type { CampaignState, KeyFigure } from '../../api/types';
import { formatStoryNumber } from '../lib/storyNumber';
import Sheet from './Sheet';

interface LibrarySheetProps {
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

/** Library: documents published up to story today and the company card (already disguised). */
export default function LibrarySheet({ library, onClose }: LibrarySheetProps): React.JSX.Element {
  const card = library.company_card;
  return (
    <Sheet title="Library" subtitle="Ledgers, proclamations and the company card" onClose={onClose}>
      <section aria-label="Company card" className="mb-4 rounded-md border border-[#c9bb98] bg-[#efe6d1] p-3 font-quest">
        <h3 className="font-quest-title text-2xl text-quest-lapis">{card.name}</h3>
        <p>{card.trade}</p>
        <p>{card.size}</p>
        {card.key_figures.length > 0 ? (
          <ul className="mt-2 space-y-1.5 text-base">
            {card.key_figures.map((f) => (
              <Figure key={f.id ?? f.label} f={f} />
            ))}
          </ul>
        ) : null}
      </section>
      <section aria-label="Documents">
        {library.documents.length === 0 ? <p className="font-quest">No documents yet.</p> : null}
        {library.documents.map((d) => (
          <article key={d.id} className="mb-3 font-quest">
            <h3 className="font-quest-title text-2xl text-quest-lapis">{d.title}</h3>
            {d.entries.map((e) => (
              <p key={e.id} className="text-base leading-snug">
                <b>{e.title}.</b> {e.text}
              </p>
            ))}
          </article>
        ))}
      </section>
    </Sheet>
  );
}
