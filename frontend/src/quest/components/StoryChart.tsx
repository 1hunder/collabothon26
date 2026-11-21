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

export interface StoryMarker {
  /** story day in story mode, ISO date in real-date mode */
  at: number | string;
  label: string;
}

export type StoryChartProps =
  | { mode: 'story'; points: { story_day: number; price: number }[]; markers?: StoryMarker[] }
  | { mode: 'real'; points: { date: string; price: number }[]; markers?: StoryMarker[] };

const DAY = 86_400;

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
      timeScale:
        props.mode === 'story'
          ? { tickMarkFormatter: (t: Time) => formatStoryDay((t as number) / DAY) }
          : {},
      localization:
        props.mode === 'story'
          ? { timeFormatter: (t: Time) => formatStoryDay((t as number) / DAY) }
          : {},
    });
    const series = chart.addSeries(LineSeries, { color: '#6FB5A8', lineWidth: 2 });
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
    chart.timeScale().fitContent();
    return () => {
      handle.detach();
      chart.remove();
    };
  }, [props]);

  return <div ref={ref} role="img" aria-label="Price chart" className="h-60 w-full" />;
}
