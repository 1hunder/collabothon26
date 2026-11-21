import { useEffect, useRef } from 'react';

export const TITLE_CARD_MS = 1500;

interface TitleCardProps {
  title: string;
  /** Smaller line under the title. */
  subtitle?: string;
  onDone: () => void;
}

/** Blackletter title over the art for about 1.5 s; any tap skips it. */
export default function TitleCard({ title, subtitle, onDone }: TitleCardProps): React.JSX.Element {
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  });
  useEffect(() => {
    const id = window.setTimeout(() => done.current(), TITLE_CARD_MS);
    return () => window.clearTimeout(id);
  }, []);

  return (
    <button
      type="button"
      data-testid="title-card"
      aria-label={`${title}. Tap to skip`}
      onClick={onDone}
      className="absolute inset-0 z-[25] grid place-items-center bg-quest-soot/50 text-center"
    >
      <span>
        <span className="block font-quest-title text-6xl leading-none text-quest-gilt [text-shadow:0_2px_20px_rgba(0,0,0,0.8)]">{title}</span>
        {subtitle ? <span className="mt-2.5 block text-lg">{subtitle}</span> : null}
        <span className="mx-auto mt-4 block h-px w-[120px] bg-gradient-to-r from-transparent via-quest-gilt to-transparent" />
      </span>
    </button>
  );
}
