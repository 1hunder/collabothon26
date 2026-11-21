/**
 * Tap targets painted into the constant backgrounds (each picture has one object with a gold glow).
 * Rects are in IMAGE percent (0-100 of the picture's own width and height), measured on the shipped
 * webp files, so they follow the art however the stage crops it.
 */

export type HotspotTarget = 'library' | 'market';

export interface ImageRect {
  /** left edge, percent of image width */
  x: number;
  /** top edge, percent of image height */
  y: number;
  /** width, percent of image width */
  w: number;
  /** height, percent of image height */
  h: number;
}

export interface Hotspot {
  target: HotspotTarget;
  label: string;
  rect: ImageRect;
}

export interface SceneHotspotConfig {
  /** natural size of the shipped background, in pixels */
  natural: { width: number; height: number };
  hotspots: readonly Hotspot[];
}

/** Keyed by PlayLocation.key of the fixed locations. */
export const sceneHotspots: Readonly<Record<string, SceneHotspotConfig>> = {
  library: {
    natural: { width: 941, height: 1671 },
    // glowing books on the left bookshelves
    hotspots: [{ target: 'library', label: "Read the guild's records", rect: { x: 0, y: 6, w: 40, h: 40 } }],
  },
  market_square: {
    natural: { width: 941, height: 1670 },
    // the glowing stall on the left: canopy, scales, chest
    hotspots: [{ target: 'market', label: 'Visit the market stall', rect: { x: 0, y: 22, w: 34, h: 46 } }],
  },
};

export interface Size {
  width: number;
  height: number;
}

export interface PxRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * Where an image-percent rect lands on screen when the picture fills `box` with
 * `object-fit: cover; object-position: 50% 50%`. The result is clamped to the box.
 */
export function coverRect(box: Size, natural: Size, rect: ImageRect): PxRect {
  const scale = Math.max(box.width / natural.width, box.height / natural.height);
  const shownW = natural.width * scale;
  const shownH = natural.height * scale;
  const offX = (box.width - shownW) / 2;
  const offY = (box.height - shownH) / 2;
  const left = Math.max(0, offX + (rect.x / 100) * shownW);
  const top = Math.max(0, offY + (rect.y / 100) * shownH);
  const right = Math.min(box.width, offX + ((rect.x + rect.w) / 100) * shownW);
  const bottom = Math.min(box.height, offY + ((rect.y + rect.h) / 100) * shownH);
  return { left, top, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
}
