import { lazy, Suspense } from 'react';
import type { PriceRow } from '../../api/types';
import { formatStoryNumber } from '../lib/storyNumber';
import Sheet from './Sheet';

const StoryChart = lazy(() => import('../components/StoryChart'));

interface PriceBoardProps {
  rows: readonly PriceRow[];
  newsDay: number | null;
  onClose: () => void;
}

/** Market Square: the chart and the daily figures, exactly up to story today. */
export default function PriceBoard({ rows, newsDay, onClose }: PriceBoardProps): React.JSX.Element {
  const points = rows.map((r) => ({ story_day: r.day, price: r.close }));
  const markers = newsDay === null ? [] : [{ at: newsDay, label: 'News' }];
  const shown = [...rows].reverse();
  return (
    <Sheet title="Price board" subtitle="Daily figures up to today" onClose={onClose}>
      <div className="mb-3 overflow-hidden rounded-md">
        <Suspense fallback={<p role="status" className="p-4 font-quest">Loading chart…</p>}>
          <StoryChart mode="story" points={points} markers={markers} />
        </Suspense>
      </div>
      <div className="max-h-56 overflow-auto">
        <table className="w-full font-quest-sans text-sm">
          <caption className="sr-only">Daily open, high, low, close and volume</caption>
          <thead>
            <tr className="text-left text-[#5b5242]">
              <th scope="col" className="pr-2">Day</th>
              <th scope="col" className="pr-2">Open</th>
              <th scope="col" className="pr-2">High</th>
              <th scope="col" className="pr-2">Low</th>
              <th scope="col" className="pr-2">Close</th>
              <th scope="col">Volume</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.day}>
                <th scope="row" className="pr-2 text-left font-medium">{r.day}</th>
                <td className="pr-2">{formatStoryNumber(r.open)}</td>
                <td className="pr-2">{formatStoryNumber(r.high)}</td>
                <td className="pr-2">{formatStoryNumber(r.low)}</td>
                <td className="pr-2">{formatStoryNumber(r.close)}</td>
                <td>{r.volume === undefined ? '' : formatStoryNumber(r.volume)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Sheet>
  );
}
