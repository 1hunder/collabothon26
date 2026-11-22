import { X } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { PlayLocation } from '../../api/types';
import villageMap from '../../assets/village-map.webp';

interface MapSheetProps {
  locations: readonly PlayLocation[];
  currentId: string | null;
  /** True while a dice check is open: moving is not allowed. */
  disabled: boolean;
  onMove: (location: PlayLocation) => void;
  onClose: () => void;
}

interface Area {
  /** Percent of the map image: left, top, width, height. */
  box: readonly [number, number, number, number];
}

const MAP_W = 941;
const MAP_H = 1672;

/** Where each fixed building sits on the village map (percent of the image). */
const FIXED_AREAS: Readonly<Record<string, Area>> = {
  library: { box: [11, 6, 37, 20] },
  market_square: { box: [27, 41, 44, 19] },
  tavern: { box: [62, 65, 36, 24] },
};

/** The far hills: the gateway to this tale's own places. */
const OTHER_AREA: Area = { box: [52, 3, 47, 14] };

const place = ({ box: [left, top, width, height] }: Area): React.CSSProperties => ({
  left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%`,
});

/**
 * The image covers the whole map area (like object-fit: cover) while staying one box with the
 * hotspots, so they keep sitting on their buildings: width is the larger of the area's width and
 * the width that fills its height; a tall overflow scrolls, a wide one is cropped evenly.
 */
const COVER: React.CSSProperties = {
  width: `max(100cqw, 100cqh * ${MAP_W} / ${MAP_H})`,
  aspectRatio: `${MAP_W} / ${MAP_H}`,
  marginLeft: '50%',
  transform: 'translateX(-50%)',
};

const PLAQUE = 'pointer-events-none rounded-md border border-[#c9bb98] bg-quest-vellum/90 px-2 py-0.5 font-quest text-sm font-semibold leading-tight text-quest-soot shadow';

/** Full-screen village map. It stops above the quest dock (--dock-h, set by VnStage) so Map, Journal and Voice stay usable. */
export default function MapSheet({ locations, currentId, disabled, onMove, onClose }: MapSheetProps): React.JSX.Element {
  const onMap = locations.filter((l) => l.key in FIXED_AREAS);
  const others = locations.filter((l) => !(l.key in FIXED_AREAS));
  const hereIsOther = others.some((l) => l.id === currentId);
  const unseen = others.filter((l) => l.generated && !l.visited && l.id !== currentId).length;
  const [othersOpen, setOthersOpen] = useState(hereIsOther);

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="The map"
      style={{ bottom: 'calc(var(--dock-h, 0px) + 0.25rem)' }}
      className="absolute inset-x-0 top-0 z-30 overflow-hidden bg-quest-vellum text-quest-soot"
    >
      <div className="h-full w-full overflow-y-auto overflow-x-hidden [container-type:size]">
        <div className="relative" style={COVER}>
          <img src={villageMap} alt="" width={MAP_W} height={MAP_H} className="absolute inset-0 h-full w-full select-none" draggable={false} />

          {onMap.map((l) => {
            const here = l.id === currentId;
            return (
              <button
                key={l.id}
                type="button"
                disabled={disabled || here}
                aria-current={here ? 'location' : undefined}
                aria-label={here ? `${l.name}, you are here` : l.name}
                onClick={() => onMove(l)}
                style={place(FIXED_AREAS[l.key])}
                className={`absolute flex flex-col items-center justify-end gap-0.5 rounded-xl pb-1 transition-colors enabled:hover:bg-quest-vellum/20 enabled:active:bg-quest-vellum/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-quest-lapis disabled:cursor-default ${
                  here ? 'ring-2 ring-quest-lapis/80' : ''
                }`}
              >
                {here ? (
                  <span className="pointer-events-none rounded-full bg-quest-lapis px-2 py-0.5 font-quest-sans text-[11px] font-bold uppercase tracking-wide text-quest-vellum shadow">
                    you are here
                  </span>
                ) : null}
                <span className={PLAQUE}>{l.name}</span>
              </button>
            );
          })}

          <button
            type="button"
            aria-expanded={othersOpen}
            aria-controls="map-other-locations"
            onClick={() => setOthersOpen((o) => !o)}
            style={place(OTHER_AREA)}
            className="absolute flex items-end justify-center rounded-xl pb-1 transition-colors hover:bg-quest-vellum/20 active:bg-quest-vellum/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-quest-lapis"
          >
            <span className={`${PLAQUE} flex items-center gap-1`}>
              Other locations
              {unseen > 0 ? (
                <span className="rounded-full bg-quest-verdigris px-1.5 font-quest-sans text-[11px] font-bold text-quest-vellum">{unseen}</span>
              ) : null}
            </span>
          </button>
        </div>
      </div>

      <button
        type="button"
        aria-label="Close The map"
        onClick={onClose}
        className="absolute right-3 top-[calc(0.75rem+env(safe-area-inset-top))] flex h-11 w-11 items-center justify-center rounded-full bg-quest-lapis-deep text-quest-soot shadow"
      >
        <X aria-hidden="true" size={22} />
      </button>

      {othersOpen ? (
        <section
          id="map-other-locations"
          aria-label="Other locations"
          className="absolute inset-x-0 bottom-0 max-h-[45%] overflow-y-auto rounded-t-[20px] border-t border-[#c9bb98] bg-quest-vellum px-5 pb-4 pt-4 shadow-[0_-6px_20px_rgba(0,0,0,0.25)]"
        >
          <h3 className="mb-2 font-quest text-lg font-semibold text-quest-lapis">Other locations</h3>
          {others.length === 0 ? (
            <p className="font-quest text-base italic text-[#5b5242]">No other roads are open in this tale yet.</p>
          ) : (
            <ul className="space-y-2">
              {others.map((l) => {
                const here = l.id === currentId;
                return (
                  <li key={l.id}>
                    <button
                      type="button"
                      disabled={disabled || here}
                      aria-current={here ? 'location' : undefined}
                      onClick={() => onMove(l)}
                      className={`flex min-h-11 w-full items-center justify-between rounded-lg border bg-quest-lapis-deep px-3 py-2.5 text-left font-quest text-[17px] font-medium text-quest-soot disabled:opacity-70 ${
                        here ? 'border-quest-lapis shadow-[inset_3px_0_0_#22305B]' : 'border-[#c9bb98]'
                      }`}
                    >
                      <span>
                        {l.name}
                        {l.generated && !l.visited && !here ? (
                          <span className="ml-2 rounded-full bg-quest-verdigris px-2 py-0.5 align-middle font-quest-sans text-xs font-bold uppercase text-quest-vellum">new</span>
                        ) : null}
                      </span>
                      <small className="font-quest-sans text-sm text-quest-vellum-dim">
                        {[here ? 'you are here' : '', l.fixed ? '' : 'this tale only'].filter(Boolean).join(' · ')}
                      </small>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      ) : null}
    </div>
  );
}
