import { X } from 'lucide-react';
import { lazy, Suspense, useState } from 'react';
import type { PriceRow } from '../../api/types';
import { formatStoryNumber } from '../lib/storyNumber';
import { useEscapeKey } from './useEscapeKey';

const StoryChart = lazy(() => import('../components/StoryChart'));

interface MarketPanelProps {
  rows: readonly PriceRow[];
  newsDay: number | null;
  onClose: () => void;
}

function PricesTab({ rows, newsDay }: { rows: readonly PriceRow[]; newsDay: number | null }): React.JSX.Element {
  const points = rows.map((r) => ({ story_day: r.day, price: r.close }));
  const markers = newsDay === null ? [] : [{ at: newsDay, label: 'News' }];
  const shown = [...rows].reverse();
  const hasVolume = rows.some((r) => r.volume !== undefined && r.volume !== null);
  return (
    <>
      <div className="mb-3 overflow-hidden rounded-md border border-[#3a2a18]">
        <Suspense fallback={<p role="status" className="p-4 font-quest">Loading chart…</p>}>
          <StoryChart mode="story" points={points} markers={markers} />
        </Suspense>
      </div>
      <div className="max-h-56 overflow-auto">
        <table className="w-full font-quest-sans text-sm">
          <caption className="sr-only">Daily open, high, low and close</caption>
          <thead>
            <tr className="text-left text-[#e8dcc2]/70">
              <th scope="col" className="pr-2">Day</th>
              <th scope="col" className="pr-2">Open</th>
              <th scope="col" className="pr-2">High</th>
              <th scope="col" className="pr-2">Low</th>
              <th scope="col" className="pr-2">Close</th>
              {hasVolume ? <th scope="col">Volume</th> : null}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.day}>
                <th scope="row" className="pr-2 text-left font-medium">{r.day}</th>
                <td className="pr-2">{formatStoryNumber(r.open)}</td>
                <td className="pr-2">{formatStoryNumber(r.high)}</td>
                <td className="pr-2">{formatStoryNumber(r.low)}</td>
                <td className={hasVolume ? 'pr-2' : ''}>{formatStoryNumber(r.close)}</td>
                {hasVolume ? <td>{r.volume == null ? '' : formatStoryNumber(r.volume)}</td> : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

interface MarketTab {
  id: string;
  label: string;
  render: (p: Pick<MarketPanelProps, 'rows' | 'newsDay'>) => React.ReactNode;
}

/**
 * EXTENSION POINT: add further stall sections here (one entry per tab). The tab bar and panel
 * pick them up automatically; the first entry is the one shown on opening.
 */
const marketTabs: readonly MarketTab[] = [
  { id: 'prices', label: 'Price chart', render: ({ rows, newsDay }) => <PricesTab rows={rows} newsDay={newsDay} /> },
];

const canvas: React.CSSProperties = {
  backgroundColor: '#3b2a1a',
  backgroundImage:
    'repeating-linear-gradient(90deg, rgba(0,0,0,0.12) 0 2px, transparent 2px 46px), repeating-linear-gradient(0deg, rgba(255,230,180,0.03) 0 1px, transparent 1px 6px)',
  boxShadow: 'inset 0 0 0 3px #7a5a34, inset 0 0 40px rgba(0,0,0,0.5)',
};

/** Market Square: the stall panel. Section one is the stock price chart up to story today. */
export default function MarketPanel({ rows, newsDay, onClose }: MarketPanelProps): React.JSX.Element {
  const [tabId, setTabId] = useState(marketTabs[0]?.id ?? '');
  const tab = marketTabs.find((t) => t.id === tabId) ?? marketTabs[0];
  useEscapeKey(onClose);
  return (
    <div className="absolute inset-0 z-30 flex items-end bg-quest-soot/60">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Market stall"
        style={canvas}
        className="relative max-h-[88%] w-full overflow-y-auto rounded-t-[20px] px-5 pb-8 pt-5 font-quest text-quest-vellum"
      >
        <button type="button" aria-label="Close Market stall" onClick={onClose} className="absolute right-3 top-3 flex h-11 w-11 items-center justify-center rounded-full text-quest-gilt">
          <X aria-hidden="true" size={22} />
        </button>
        <h2 className="font-quest-title text-3xl text-quest-gilt">Market stall</h2>
        <p className="mb-3 text-base italic text-quest-vellum/80">Daily figures up to today</p>
        <div role="tablist" aria-label="Stall sections" className="mb-3 flex gap-2 border-b border-[#7a5a34]">
          {marketTabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              id={`market-tab-${t.id}`}
              aria-selected={t.id === tab?.id}
              aria-controls={`market-panel-${t.id}`}
              onClick={() => setTabId(t.id)}
              className={`min-h-11 border-b-2 px-3 font-quest-sans text-base ${t.id === tab?.id ? 'border-quest-gilt text-quest-gilt' : 'border-transparent text-quest-vellum/70'}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        {tab ? (
          <div role="tabpanel" id={`market-panel-${tab.id}`} aria-labelledby={`market-tab-${tab.id}`}>
            {tab.render({ rows, newsDay })}
          </div>
        ) : null}
      </div>
    </div>
  );
}
