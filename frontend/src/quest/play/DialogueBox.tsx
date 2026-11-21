import { useEffect, useMemo, useRef, useState } from 'react';
import { splitPages } from './paginate';
import { useTypewriter } from './useTypewriter';

export type VoiceKind = 'dm' | 'buddy';

export const BUDDY_NAME = 'CommerzBuddy';
export const DM_NAME = 'Campaign Master';

export interface DialogueBoxProps {
  speaker: string;
  /** The reply so far; it grows while it streams in. */
  text: string;
  /** False while the reply is still arriving. */
  final?: boolean;
  /** Show the writing indicator while there is no text yet. */
  writing?: boolean;
  writingLabel?: string;
  /** Show the whole page at once (resumed turns, tests). */
  instant?: boolean;
  /** Tapped past the last page: the choices take over. */
  onAdvance: () => void;
  /**
   * VOICE HOOK: called once for every page when it starts to show, with the page text and which
   * voice reads it. The voice module (src/voice) plugs in here; this component stays silent.
   */
  onPageShown?: (text: string, voice: VoiceKind, audioTextId?: number | string | null) => void;
  /** Server audio id of the whole reply; played once, across all pages. */
  audioTextId?: number | string | null;
  /** Swipe down on the box opens the backlog. */
  onSwipeDown?: () => void;
}

const SWIPE_PX = 40;

export default function DialogueBox({
  speaker,
  text,
  final = true,
  writing = false,
  writingLabel = 'The Campaign Master is writing…',
  instant = false,
  onAdvance,
  onPageShown,
  audioTextId = null,
  onSwipeDown,
}: DialogueBoxProps): React.JSX.Element {
  const pages = useMemo(() => splitPages(text), [text]);
  const [index, setIndex] = useState(0);
  const last = index >= pages.length - 1;
  const page = pages[Math.min(index, pages.length - 1)] ?? '';
  const { shown, complete } = useTypewriter(page.length, String(index), instant);
  const done = shown >= page.length && page.length > 0;
  const canAdvance = done && (!last || final);
  const isBuddy = speaker === BUDDY_NAME;
  const voice: VoiceKind = isBuddy ? 'buddy' : 'dm';

  const spoken = useRef<number>(-1);
  const pageReady = final || !last;
  useEffect(() => {
    // Nothing is spoken while the reply is still arriving: the finished reply brings its server
    // audio id, and a page already spoken by the browser voice would block that audio.
    if (!final || !pageReady || page === '') return;
    // Server audio covers the whole reply: start it once with page one and let it run across pages.
    if (final && audioTextId != null) {
      if (spoken.current >= 0) return;
      spoken.current = 0;
      onPageShown?.(pages.join(' '), voice, audioTextId);
      return;
    }
    if (spoken.current === index) return;
    spoken.current = index;
    onPageShown?.(page, voice, null);
  }, [index, page, pages, pageReady, voice, onPageShown, final, audioTextId]);

  const tap = (): void => {
    if (!done) complete();
    else if (!last) setIndex(index + 1);
    else if (final) onAdvance();
  };

  const touchY = useRef<number | null>(null);

  if (text === '' && writing) {
    return (
      <section className="relative mx-3 rounded-[14px_14px_18px_18px] bg-quest-lapis/95 px-5 pb-8 pt-6 shadow-[inset_0_0_0_1px_rgba(201,162,39,0.55),inset_0_0_0_5px_#161F3D,inset_0_0_0_6px_rgba(201,162,39,0.22)]">
        <NameTab speaker={speaker} />
        <p role="status" className="min-h-[4.5em] font-quest text-[19px] italic leading-normal text-quest-vellum-dim">
          {writingLabel}
        </p>
      </section>
    );
  }

  return (
    <section
      data-testid="dialogue-box"
      onClick={tap}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          tap();
        }
      }}
      onTouchStart={(e) => {
        touchY.current = e.touches[0]?.clientY ?? null;
      }}
      onTouchEnd={(e) => {
        const start = touchY.current;
        touchY.current = null;
        const end = e.changedTouches[0]?.clientY;
        if (start !== null && end !== undefined && end - start > SWIPE_PX) onSwipeDown?.();
      }}
      tabIndex={0}
      role="group"
      aria-label={`${speaker} says`}
      className="relative mx-3 cursor-pointer select-none rounded-[14px_14px_18px_18px] bg-quest-lapis/95 px-5 pb-9 pt-6 shadow-[inset_0_0_0_1px_rgba(201,162,39,0.55),inset_0_0_0_5px_#161F3D,inset_0_0_0_6px_rgba(201,162,39,0.22)]"
    >
      <NameTab speaker={speaker} />
      <p data-testid="dialogue-text" aria-hidden="true" className="min-h-[4.5em] font-quest text-[19px] leading-normal text-quest-vellum">
        {page.slice(0, shown)}
      </p>
      {/* One announcement per completed page, never the letter-by-letter reveal. */}
      <p data-testid="dialogue-live" aria-live="polite" className="sr-only">
        {done && pageReady ? page : ''}
      </p>
      {pages.length > 1 ? (
        <span className="absolute bottom-3 left-5 font-quest-sans text-[13px] text-quest-vellum-dim">
          {index + 1} / {pages.length}
        </span>
      ) : null}
      {canAdvance ? (
        <span aria-hidden="true" className="absolute bottom-3 right-4 animate-bob text-sm text-quest-gilt motion-reduce:animate-none">
          ▼
        </span>
      ) : null}
    </section>
  );
}

function NameTab({ speaker }: { speaker: string }): React.JSX.Element {
  const buddy = speaker === BUDDY_NAME;
  return (
    <span
      data-testid="name-tab"
      className={`absolute -top-[15px] left-[18px] rounded-[4px_4px_4px_0] px-3.5 pb-1 pt-[3px] font-quest text-base font-bold tracking-[0.02em] text-quest-soot ${
        buddy ? 'bg-quest-verdigris-light' : 'bg-quest-gilt'
      }`}
    >
      {speaker}
    </span>
  );
}
