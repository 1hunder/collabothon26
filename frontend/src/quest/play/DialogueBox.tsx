import { useEffect, useMemo, useRef, useState } from 'react';
import type { SpeakerKind } from '../../api/types';
import { splitPages } from './paginate';
import { useTypewriter } from './useTypewriter';

export type VoiceKind = 'dm' | 'buddy' | 'veteran';

export const BUDDY_NAME = 'CommerzBuddy';
export const DM_NAME = 'Campaign Master';
export const VETERAN_NAME = 'Brannoc';

export interface DialogueBoxProps {
  speaker: string;
  /** npc: a character of the scene (verdigris tab). Left out, the speaker name decides. */
  speakerKind?: SpeakerKind;
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
  /** Server audio id of the whole reply; played once, across all pages (even while streaming). */
  audioTextId?: number | string | null;
  /** The reply's whole stored text, known before it has streamed: what the voice reads. */
  audioText?: string | null;
  /** Swipe down on the box opens the backlog. */
  onSwipeDown?: () => void;
  /**
   * Coming back to a reply already read ("Read again"): open on its last page, show every page
   * at once and stay silent.
   */
  revisit?: boolean;
}

const SWIPE_PX = 40;

export default function DialogueBox({
  speaker,
  speakerKind,
  text,
  final = true,
  writing = false,
  writingLabel = 'The Campaign Master is writing…',
  instant = false,
  onAdvance,
  onPageShown,
  audioTextId = null,
  audioText = null,
  onSwipeDown,
  revisit = false,
}: DialogueBoxProps): React.JSX.Element {
  const pages = useMemo(() => splitPages(text), [text]);
  const [index, setIndex] = useState(() => (revisit ? Math.max(0, pages.length - 1) : 0));
  // The furthest page reached: a page read before shows at once when the player goes back to it.
  const [reached, setReached] = useState(index);
  const last = index >= pages.length - 1;
  const page = pages[Math.min(index, pages.length - 1)] ?? '';
  const { shown, complete } = useTypewriter(page.length, String(index), instant || revisit || index < reached);
  const done = shown >= page.length && page.length > 0;
  const canAdvance = done && (!last || final);
  const isBuddy = speaker === BUDDY_NAME;
  const voice: VoiceKind = isBuddy ? 'buddy' : speaker === VETERAN_NAME ? 'veteran' : 'dm';

  const spoken = useRef<number>(-1);
  const pageReady = final || !last;
  useEffect(() => {
    if (revisit || page === '') return;
    // Server audio covers the whole reply: start it once, as soon as its id is known (the server
    // sends it with the first word, its synthesis already running), and let it run across pages.
    if (audioTextId != null) {
      if (spoken.current >= 0) return;
      spoken.current = 0;
      onPageShown?.(audioText ?? pages.join(' '), voice, audioTextId);
      return;
    }
    // Browser voice page by page, only once the reply is complete: a page spoken while streaming
    // would be cut short, and would block the server audio the finished reply brings.
    if (!final || !pageReady) return;
    if (spoken.current === index) return;
    spoken.current = index;
    onPageShown?.(page, voice, null);
  }, [index, page, pages, pageReady, voice, onPageShown, final, audioTextId, audioText, revisit]);

  const goTo = (i: number): void => {
    setIndex(i);
    setReached((r) => Math.max(r, i));
  };
  const tap = (): void => {
    if (!done) complete();
    else if (!last) goTo(index + 1);
    else if (final) onAdvance();
  };
  const back = (): void => {
    if (index > 0) goTo(index - 1);
  };

  const touchY = useRef<number | null>(null);

  if (text === '' && writing) {
    return (
      <section className="relative mx-3 rounded-[14px_14px_18px_18px] bg-quest-lapis/95 px-5 pb-8 pt-6 shadow-[inset_0_0_0_1px_rgba(201,162,39,0.55),inset_0_0_0_5px_#161F3D,inset_0_0_0_6px_rgba(201,162,39,0.22)]">
        <NameTab speaker={speaker} kind={speakerKind} />
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
        if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowRight') {
          e.preventDefault();
          tap();
        } else if (e.key === 'ArrowLeft') {
          e.preventDefault();
          back();
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
      <NameTab speaker={speaker} kind={speakerKind} />
      <p data-testid="dialogue-text" aria-hidden="true" className="min-h-[4.5em] font-quest text-[19px] leading-normal text-quest-vellum">
        {page.slice(0, shown)}
      </p>
      {/* One announcement per completed page, never the letter-by-letter reveal. */}
      <p data-testid="dialogue-live" aria-live="polite" className="sr-only">
        {done && pageReady ? page : ''}
      </p>
      {pages.length > 1 ? (
        <span className="absolute bottom-1.5 left-3 flex items-center gap-1 font-quest-sans text-[13px] text-quest-vellum-dim">
          {index > 0 ? (
            <button
              type="button"
              aria-label="Previous page"
              onClick={(e) => {
                e.stopPropagation(); // a tap on the box itself goes forward
                back();
              }}
              onKeyDown={(e) => e.stopPropagation()}
              className="flex h-8 min-w-8 items-center justify-center rounded-full text-quest-gilt hover:bg-quest-gilt/15"
            >
              ◀
            </button>
          ) : (
            <span aria-hidden="true" className="min-w-2" />
          )}
          <span>
            {index + 1} / {pages.length}
          </span>
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

function NameTab({ speaker, kind }: { speaker: string; kind?: SpeakerKind }): React.JSX.Element {
  const buddy = speaker === BUDDY_NAME;
  const npc = kind === 'npc';
  return (
    <span
      data-testid="name-tab"
      data-kind={npc ? 'npc' : undefined}
      className={`absolute -top-[15px] left-[18px] rounded-[4px_4px_4px_0] px-3.5 pb-1 pt-[3px] font-quest text-base font-bold tracking-[0.02em] ${
        npc ? 'bg-quest-verdigris text-quest-vellum' : buddy ? 'bg-quest-verdigris-light text-quest-soot' : speaker === VETERAN_NAME ? 'bg-quest-wax-light text-quest-soot' : 'bg-quest-gilt text-quest-soot'
      }`}
    >
      {speaker}
    </span>
  );
}
