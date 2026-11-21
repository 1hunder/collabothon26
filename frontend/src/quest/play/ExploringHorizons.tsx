interface ExploringHorizonsProps {
  name: string;
}

/** Full-scene loading state while a new location's art is painted. Sits under the dialogue. */
export default function ExploringHorizons({ name }: ExploringHorizonsProps): React.JSX.Element {
  return (
    <div
      data-testid="exploring-horizons"
      role="status"
      className="absolute inset-0 flex flex-col items-center justify-center gap-3 overflow-hidden bg-gradient-to-b from-[#2a2440] via-[#1d2547] to-[#120f1a] px-8 text-center"
    >
      <div
        aria-hidden="true"
        className="absolute inset-[-10%] bg-[radial-gradient(circle_at_30%_30%,rgba(201,162,39,0.18),transparent_45%),repeating-linear-gradient(35deg,rgba(232,220,194,0.05)_0_2px,transparent_2px_26px)] motion-safe:animate-map-drift"
      />
      <svg
        aria-hidden="true"
        viewBox="0 0 100 100"
        className="relative h-28 w-28 text-quest-gilt motion-safe:animate-compass-drift"
      >
        <circle cx="50" cy="50" r="44" fill="none" stroke="currentColor" strokeWidth="2" />
        <circle cx="50" cy="50" r="38" fill="none" stroke="currentColor" strokeOpacity="0.4" strokeWidth="1" />
        <path d="M50 10 L58 50 L50 90 L42 50 Z" fill="currentColor" fillOpacity="0.25" stroke="currentColor" strokeWidth="1.5" />
        <path d="M50 10 L58 50 L42 50 Z" fill="#E2807A" />
        <path d="M10 50 L50 42 L90 50 L50 58 Z" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="50" cy="50" r="3" fill="currentColor" />
      </svg>
      <p className="relative font-quest-title text-4xl text-quest-gilt">Exploring new horizons</p>
      <p className="relative font-quest text-xl italic text-quest-vellum">{name}</p>
    </div>
  );
}
