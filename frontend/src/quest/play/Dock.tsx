import { BookOpen, Map, Sparkles, Volume2, VolumeX } from 'lucide-react';

interface DockProps {
  /** The map cannot be used while a dice check is open. */
  mapDisabled: boolean;
  voiceOn: boolean;
  onMap: () => void;
  onJournal: () => void;
  onToggleVoice: () => void;
  /** Learning moments waiting: shows a Buddy button with a badge that opens the Buddy panel. */
  eduWaiting?: number;
  onBuddy?: () => void;
}

const item =
  'flex min-h-11 w-16 flex-col items-center gap-0.5 rounded-lg bg-quest-soot/70 text-sm disabled:opacity-40';

export default function Dock({ mapDisabled, voiceOn, onMap, onJournal, onToggleVoice, eduWaiting = 0, onBuddy }: DockProps): React.JSX.Element {
  return (
    <nav aria-label="Quest dock" className="flex items-center justify-between px-5 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-2">
      <button type="button" className={item} disabled={mapDisabled} onClick={onMap}>
        <Map aria-hidden="true" size={26} />
        Map
      </button>
      <button type="button" className={item} onClick={onJournal}>
        <BookOpen aria-hidden="true" size={26} />
        Journal
      </button>
      {eduWaiting > 0 && onBuddy ? (
        <button type="button" className={`${item} relative text-quest-gilt`} aria-label={`CommerzBuddy, ${eduWaiting} learning ${eduWaiting === 1 ? 'moment' : 'moments'} waiting`} data-awake="true" onClick={onBuddy}>
          <Sparkles aria-hidden="true" size={26} />
          Buddy
          <span aria-hidden="true" className="absolute -right-1 -top-1 grid size-5 place-items-center rounded-full bg-quest-wax-light text-xs font-bold text-quest-vellum">{eduWaiting}</span>
        </button>
      ) : null}
      <button type="button" className={item} aria-pressed={voiceOn} onClick={onToggleVoice}>
        {voiceOn ? <Volume2 aria-hidden="true" size={26} /> : <VolumeX aria-hidden="true" size={26} />}
        Voice
      </button>
    </nav>
  );
}
