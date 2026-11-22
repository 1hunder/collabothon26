import { Suspense } from 'react';
import '@fontsource/alegreya/400.css';
import '@fontsource/alegreya-sans/400.css';
import '@fontsource/pirata-one/400.css';
import type { RevealData } from '../../api/types';
import { formatStoryNumber } from '../lib/storyNumber';

import { formatRealDate } from '../components/storyChartFormat';
// Bundled, not lazy: a lazy chunk from a build replaced by a later deploy failed mid-game.
import StoryChart from '../components/StoryChart';

interface RevealProps {
  data: RevealData;
}

export default function Reveal({ data }: RevealProps): React.JSX.Element {
  return (
    <article className="min-h-dvh space-y-6 bg-quest-soot p-4 font-quest text-quest-vellum">
      <header>
        <h1 className="font-quest-title text-4xl text-quest-gilt">{data.real_name}</h1>
        <p className="font-quest-sans text-quest-vellum-dim">
          {data.ticker} · {data.start_date} to {data.end_date}
        </p>
      </header>

      {data.n_guessers > 0 && (
        <p>
          Before you played, {data.n_guessers} AI testers tried to guess this company. None of them
          got it.
        </p>
      )}

      <Suspense fallback={<div className="h-60" aria-busy="true" />}>
        <StoryChart
          mode="real"
          points={data.series}
          markers={data.news_points.map((n) => ({ at: n.real_date, label: formatRealDate(n.real_date) }))}
        />
      </Suspense>

      <table className="w-full text-left font-quest-sans text-sm">
        <caption className="mb-2 text-left font-quest-title text-2xl text-quest-gilt">
          What happened
        </caption>
        <thead className="text-quest-vellum-dim">
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Price</th>
            <th scope="col">News</th>
          </tr>
        </thead>
        <tbody>
          {data.news_points.map((n) => (
            <tr key={`${n.story_day}-${n.real_date}`} className="border-t border-quest-lapis">
              <td>{n.real_date}</td>
              <td>{formatStoryNumber(n.real_price)}</td>
              <td>{n.headline}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <section>
        <h2 className="mb-2 font-quest-title text-2xl text-quest-gilt">What we changed</h2>
        <ul className="list-disc space-y-1 pl-5">
          {data.what_changed.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </section>
    </article>
  );
}
