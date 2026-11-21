import type { PlayLocation } from '../../api/types';
import Sheet from './Sheet';

interface MapSheetProps {
  locations: readonly PlayLocation[];
  currentId: string | null;
  /** True while a dice check is open: moving is not allowed. */
  disabled: boolean;
  onMove: (location: PlayLocation) => void;
  onClose: () => void;
}

export default function MapSheet({ locations, currentId, disabled, onMove, onClose }: MapSheetProps): React.JSX.Element {
  return (
    <Sheet title="The map" subtitle="Where would you go?" onClose={onClose}>
      <ul className="space-y-2">
        {locations.map((l) => {
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
                  {here ? 'you are here' : l.fixed ? '' : 'this tale only'}
                  {here && !l.fixed ? ' · this tale only' : ''}
                </small>
              </button>
            </li>
          );
        })}
      </ul>
    </Sheet>
  );
}
