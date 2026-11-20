import { useEffect, useRef, useState } from 'react';

/** Characters revealed per second. */
const CHARS_PER_SECOND = 60;

export function prefersReducedMotion(): boolean {
  try {
    return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    return false;
  }
}

/**
 * Reveals `length` characters over time with requestAnimationFrame. `resetKey` restarts the
 * reveal (a new page); a growing `length` under the same key continues from where it was.
 * Reduced motion and `instant` show everything at once.
 */
export function useTypewriter(length: number, resetKey: string, instant: boolean): { shown: number; complete: () => void } {
  const [progress, setProgress] = useState({ key: resetKey, n: 0 });
  const skip = instant || prefersReducedMotion();
  const shown = skip ? length : progress.key === resetKey ? Math.min(progress.n, length) : 0;

  const latest = useRef(0);
  useEffect(() => {
    latest.current = shown;
  });

  useEffect(() => {
    if (skip) return;
    let pos = latest.current;
    if (pos >= length) return;
    let frame = 0;
    let last: number | null = null;
    const tick = (now: number): void => {
      const dt = last === null ? 16 : now - last;
      last = now;
      pos = Math.min(length, pos + (dt * CHARS_PER_SECOND) / 1000);
      // max(): a tap that completed the page must never be undone by a pending frame
      setProgress((prev) => ({ key: resetKey, n: prev.key === resetKey ? Math.max(prev.n, Math.floor(pos)) : Math.floor(pos) }));
      if (pos < length) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [length, resetKey, skip]);

  return { shown, complete: () => setProgress({ key: resetKey, n: length }) };
}
