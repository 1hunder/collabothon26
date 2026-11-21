import { useLayoutEffect, useRef, useState } from 'react';
import { coverRect, sceneHotspots, type HotspotTarget, type Size } from './sceneHotspots';

interface HotspotLayerProps {
  /** PlayLocation.key of the current location. */
  locationKey: string | undefined;
  /** False while a sheet, the dice, a card or the Buddy is open: no hotspot is offered. */
  active: boolean;
  onOpen: (target: HotspotTarget) => void;
}

/** Locations whose hotspot has already pulsed once this session. */
const pulsedLocations = new Set<string>();

/** Transparent buttons laid over the glowing object painted into the background. */
export default function HotspotLayer({ locationKey, active, onOpen }: HotspotLayerProps): React.JSX.Element | null {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<Size | null>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = (): void => {
      const r = el.getBoundingClientRect();
      setSize(r.width > 0 && r.height > 0 ? { width: r.width, height: r.height } : null);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const config = locationKey === undefined ? undefined : sceneHotspots[locationKey];
  const pulse = locationKey !== undefined && !pulsedLocations.has(locationKey);
  useLayoutEffect(() => {
    if (locationKey !== undefined && active) pulsedLocations.add(locationKey);
  }, [locationKey, active]);

  return (
    <div ref={ref} data-testid="scene-hotspots" className="pointer-events-none absolute inset-0 z-[4]">
      {active && config
        ? config.hotspots.map((h) => {
            // Without a measured box (first paint, tests) the rect is read as plain container percent.
            const style: React.CSSProperties = size
              ? (() => {
                  const r = coverRect(size, config.natural, h.rect);
                  return { left: r.left, top: r.top, width: r.width, height: r.height };
                })()
              : { left: `${h.rect.x}%`, top: `${h.rect.y}%`, width: `${h.rect.w}%`, height: `${h.rect.h}%` };
            return (
              <button
                key={h.target}
                type="button"
                aria-label={h.label}
                data-hotspot={h.target}
                onClick={() => onOpen(h.target)}
                style={style}
                className={`pointer-events-auto absolute rounded-2xl border-2 border-transparent bg-transparent outline-offset-2 focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-quest-gilt ${
                  pulse ? 'animate-hotspot-pulse motion-reduce:animate-none' : ''
                }`}
              />
            );
          })
        : null}
    </div>
  );
}
