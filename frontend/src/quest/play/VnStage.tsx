import { useEffect, useRef } from 'react';
import type { PlayLocation } from '../../api/types';
import SceneArt from './SceneArt';

interface VnStageProps {
  location: PlayLocation | undefined;
  /** Show the "Exploring new horizons" loading scene instead of the art. */
  exploring?: boolean;
  /** Hero status along the top (leaves room for the quest layout's close button). */
  status: React.ReactNode;
  /** Contextual button row under the status (price board, documents). */
  chips?: React.ReactNode;
  dock: React.ReactNode;
  /** Tap targets over the art (below the status and dialogue layers). */
  hotspots?: React.ReactNode;
  /** Sheets, dice, title and news cards: absolutely positioned over the stage. */
  overlays?: React.ReactNode;
  /** Dialogue box or choices, stacked above the dock. */
  children: React.ReactNode;
}

/** Keeps the dock visible above the iOS keyboard: --vvh follows the visual viewport. */
function useVisualViewportHeight(): void {
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const update = (): void => {
      document.documentElement.style.setProperty('--vvh', `${vv.height}px`);
    };
    update();
    vv.addEventListener('resize', update);
    return () => {
      vv.removeEventListener('resize', update);
      document.documentElement.style.removeProperty('--vvh');
    };
  }, []);
}

/**
 * Publishes the dock's height as --dock-h on the stage, so a full-screen overlay (the map) can
 * stop right above the dock and leave Map, Journal and Voice usable.
 */
function useDockHeight(stage: React.RefObject<HTMLDivElement | null>, dock: React.RefObject<HTMLDivElement | null>): void {
  useEffect(() => {
    const s = stage.current;
    const d = dock.current;
    if (!s || !d) return;
    const update = (): void => s.style.setProperty('--dock-h', `${d.offsetHeight}px`);
    update();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(update);
    ro.observe(d);
    return () => ro.disconnect();
  }, [stage, dock]);
}

/** The visual-novel scene: a full-height stack of art, status, dialogue or choices, and the dock. */
export default function VnStage({ location, exploring, status, chips, hotspots, dock, overlays, children }: VnStageProps): React.JSX.Element {
  useVisualViewportHeight();
  const stageRef = useRef<HTMLDivElement>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  useDockHeight(stageRef, dockRef);
  return (
    <div
      ref={stageRef}
      data-testid="vn-stage"
      style={{ height: 'var(--vvh, 100dvh)' }}
      className="fixed left-1/2 top-0 z-10 w-full max-w-[430px] -translate-x-1/2 overflow-hidden bg-quest-lapis-deep font-quest text-quest-vellum"
    >
      <SceneArt location={location} exploring={exploring} />
      {hotspots}
      <header className="pointer-events-none absolute inset-x-0 top-0 z-[5] [&_button]:pointer-events-auto px-5 pt-[calc(0.75rem+env(safe-area-inset-top))]">
        {status}
        {chips ? <div className="mt-2 flex gap-2">{chips}</div> : null}
      </header>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[6] [&>*]:pointer-events-auto flex flex-col justify-end gap-2 pb-1 pt-5">
        {children}
        <div ref={dockRef}>{dock}</div>
      </div>
      {overlays}
    </div>
  );
}
