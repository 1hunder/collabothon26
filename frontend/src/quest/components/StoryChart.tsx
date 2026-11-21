import { useEffect, useRef } from 'react';
import {
  ColorType,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type LineData,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import { formatStoryDay } from '../lib/storyNumber';
import { LOCALE, formatRealDate, formatRealTick } from './storyChartFormat';

export interface StoryMarker {
  /** story day in story mode, ISO date in real-date mode */
  at: number | string;
  label: string;
}

export type StoryChartProps =
  | { mode: 'story'; points: { story_day: number; price: number }[]; markers?: StoryMarker[] }
  | { mode: 'real'; points: { date: string; price: number }[]; markers?: StoryMarker[] };

const DAY = 86_400;
/** Price scale labels and tooltips are whole numbers, like everything else the player reads. */
const wholePrice = (p: number): string => Math.round(p).toLocaleString('en-US');

export default function StoryChart(props: StoryChartProps): React.JSX.Element {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      height: 240,
      layout: {
        background: { type: ColorType.Solid, color: '#161F3D' },
        textColor: '#E8DCC2',
      },
      grid: { vertLines: { color: '#22305B' }, horzLines: { color: '#22305B' } },
      // Room on the right so the last axis label is not cut off at the edge.
      timeScale:
        props.mode === 'story'
          ? { rightOffset: 3, tickMarkFormatter: (t: Time) => formatStoryDay((t as number) / DAY) }
          : { rightOffset: 3, tickMarkFormatter: formatRealTick },
      localization:
        props.mode === 'story'
          ? { locale: LOCALE, priceFormatter: wholePrice, timeFormatter: (t: Time) => formatStoryDay((t as number) / DAY) }
          : { locale: LOCALE, priceFormatter: wholePrice, timeFormatter: formatRealDate },
    });
    const series = chart.addSeries(LineSeries, {
      color: '#6FB5A8',
      lineWidth: 2,
      priceFormat: { type: 'custom', formatter: wholePrice, minMove: 1 },
    });
    const toTime = (at: number | string): Time =>
      (typeof at === 'number' ? at * DAY : at) as UTCTimestamp | Time;
    const data: LineData[] =
      props.mode === 'story'
        ? props.points.map((p) => ({ time: toTime(p.story_day), value: p.price }))
        : props.points.map((p) => ({ time: p.date as Time, value: p.price }));
    series.setData(data);
    const markers: SeriesMarker<Time>[] = (props.markers ?? []).map((m) => ({
      time: toTime(m.at),
      position: 'aboveBar',
      shape: 'circle',
      color: '#C9A227',
      text: m.label,
    }));
    const handle = createSeriesMarkers(series, markers);
    // Pad both ends so the first and last axis labels are not cut off at the edges.
    if (data.length > 1) chart.timeScale().setVisibleLogicalRange({ from: -6, to: data.length - 1 + 4 });
    else chart.timeScale().fitContent();
    return () => {
      handle.detach();
      chart.remove();
    };
  }, [props]);

  return <div ref={ref} role="img" aria-label="Price chart" className="h-60 w-full" />;
}
