import { X } from 'lucide-react';
import { useEffect } from 'react';

interface SheetProps {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
}

/** Vellum bottom sheet shared by the map, journal, backlog, price board and library. */
export default function Sheet({ title, subtitle, onClose, children }: SheetProps): React.JSX.Element {
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="absolute inset-0 z-30 flex items-end bg-quest-soot/60">
      <div role="dialog" aria-modal="true" aria-label={title} className="relative max-h-[85%] w-full overflow-y-auto rounded-t-[20px] bg-quest-vellum px-5 pb-8 pt-5 text-quest-soot">
        <button
          type="button"
          aria-label={`Close ${title}`}
          onClick={onClose}
          className="absolute right-3 top-3 flex h-11 w-11 items-center justify-center rounded-full bg-quest-lapis-deep"
        >
          <X aria-hidden="true" size={22} />
        </button>
        <h2 className="font-quest-title text-3xl text-quest-lapis">{title}</h2>
        {subtitle ? <p className="mb-3 font-quest text-base italic text-[#5b5242]">{subtitle}</p> : null}
        {children}
      </div>
    </div>
  );
}
