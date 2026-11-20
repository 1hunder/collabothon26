import type { BacklogEntry } from '../../api/types';

/** Speaker of the Market Square rumours when the server sends no explicit `rumours` list. */
const RUMOUR_SPEAKER = 'Ren Tal';

/** Rumours heard so far: the server's list when present, else what the rumour-monger said. */
export function rumoursHeard(rumours: readonly string[] | undefined, backlog: readonly BacklogEntry[]): readonly string[] {
  return rumours ?? backlog.filter((e) => e.speaker === RUMOUR_SPEAKER).map((e) => e.text);
}

export function hasRumourLedger(heroItems: readonly string[], rumours: readonly string[] | undefined): boolean {
  return rumours !== undefined || heroItems.some((i) => /rumou?r/i.test(i));
}
