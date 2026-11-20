// Fixture storage shared by the fixture handlers (fixture mode only; never used against the real API).
import type { CampaignState, CommitRequest, Hero } from '../types';

/** Thrown by fixture handlers to simulate a non-2xx response. */
export class FixtureHttpError extends Error {
  readonly status: number;
  constructor(status: number) {
    super(`Fixture HTTP ${status}`);
    this.name = 'FixtureHttpError';
    this.status = status;
  }
}

// Campaign fixtures keep their state in memory and mirror it to localStorage so reloads behave
// like a persistent backend. Fixture mode only; never used against the real API.
const FIXTURE_KEY = 'fq.fixture.v1';
export const classHp = { guardian: 120, analyst: 100, investigator: 100 } as const;

/** Server-side bookkeeping the public campaign state does not carry (play slice). */
export interface FixtureEvent {
  seq: number;
  type: string;
  [field: string]: unknown;
}

export interface FixtureRoll {
  /** dice of the first roll and of the Second Look reroll */
  first: number[];
  second: number[];
  rerolled: boolean;
}

export interface FixturePlay {
  events: FixtureEvent[];
  rolls: Record<string, FixtureRoll>;
  /** stored SSE scripts keyed by path and client_msg_id, so "Try again" is idempotent */
  replays: Record<string, string>;
}

export interface FixtureDb {
  hero: Hero | null;
  campaign: CampaignState | null;
  decision?: CommitRequest | null;
  play?: FixturePlay;
}

let memoryDb: FixtureDb = { hero: null, campaign: null };

export function readDb(): FixtureDb {
  try {
    const raw = window.localStorage.getItem(FIXTURE_KEY);
    if (raw !== null) return JSON.parse(raw) as FixtureDb;
  } catch {
    // fall back to memory
  }
  return memoryDb;
}

export function writeDb(db: FixtureDb): void {
  memoryDb = db;
  try {
    window.localStorage.setItem(FIXTURE_KEY, JSON.stringify(db));
  } catch {
    // memory copy is enough
  }
}

/** Test helper: forget fixture hero and campaign. */
export function resetFixtureDb(): void {
  writeDb({ hero: null, campaign: null });
}

