import { X } from 'lucide-react';
import { useCallback, useEffect, useId, useRef } from 'react';
import { useEscapeKey } from '../play/useEscapeKey';
import { useReportSheetOpen } from '../sheetOpen';

interface ParchmentSheetProps {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), textarea, select, [tabindex]:not([tabindex="-1"])';
const SWIPE_CLOSE_PX = 90;

/** A modal parchment: focus trap, Esc and the close button, swipe down on the top rod to close. */
export default function ParchmentSheet({ title, onClose, children, footer }: ParchmentSheetProps): React.JSX.Element {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const startY = useRef<number | null>(null);
  useReportSheetOpen(true);
  useEscapeKey(onClose);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>('[data-autofocus]')?.focus();
    return () => opener?.focus?.();
  }, []);

  const trap = useCallback((e: React.KeyboardEvent) => {
    if (e.key !== 'Tab' || !ref.current) return;
    const items = Array.from(ref.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    const first = items[0];
    const last = items[items.length - 1];
    if (!first || !last) return;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }, []);

  return (
    <div className="qb-scrim" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} className="qb-sheet" onKeyDown={trap}>
        <div
          className="qb-rod"
          aria-hidden="true"
          onPointerDown={(e) => {
            startY.current = e.clientY;
            e.currentTarget.setPointerCapture?.(e.pointerId);
          }}
          onPointerUp={(e) => {
            if (startY.current !== null && e.clientY - startY.current > SWIPE_CLOSE_PX) onClose();
            startY.current = null;
          }}
          onPointerCancel={() => {
            startY.current = null;
          }}
        />
        <button type="button" aria-label="Close" className="qb-x" onClick={onClose}>
          <X aria-hidden="true" size={24} />
        </button>
        <div className="qb-body">
          <h2 id={titleId} className="pr-10 font-quest-title text-3xl leading-none">{title}</h2>
          {children}
        </div>
        {footer ? <div className="qb-foot">{footer}</div> : null}
      </div>
    </div>
  );
}
