import VeteranPortrait from './VeteranPortrait';

interface TavernVeteranProps {
  /** False while a sheet, card, the dice or a conversation is open: he stays, but cannot be tapped. */
  active: boolean;
  /** Hidden while his conversation is open (the scene shows him larger). */
  hidden: boolean;
  onOpen: () => void;
}

/**
 * Brannoc sitting by the Tavern fireplace, drawn over the art like any other character. The figure
 * itself is the hotspot: tap him to talk.
 */
export default function TavernVeteran({ active, hidden, onOpen }: TavernVeteranProps): React.JSX.Element | null {
  if (hidden) return null;
  return (
    <button
      type="button"
      aria-label="Talk to Brannoc, the Veteran by the fire"
      data-hotspot="veteran"
      disabled={!active}
      onClick={onOpen}
      className="absolute left-[1%] top-[29%] z-[4] w-[34%] max-w-[160px] rounded-[40%_40%_14px_14px] outline-offset-2 transition-[filter] focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-quest-gilt enabled:hover:drop-shadow-[0_0_14px_rgba(201,162,39,0.55)] disabled:cursor-default"
    >
      <VeteranPortrait bare className="block h-auto w-full drop-shadow-[0_6px_14px_rgba(0,0,0,0.6)]" />
    </button>
  );
}
