import { readDb, writeDb } from '../api/fixtures/db';
import { fixtureResponse, resetFixtureDb } from '../api/fixtures';
import type { CampaignPhase, CommitRequest, HeroClass } from '../api/types';

/** Fixture-mode hero plus an active campaign in the given phase (test helper). */
export function seedCampaign(opts: {
  phase: CampaignPhase;
  heroClass?: HeroClass;
  decision?: CommitRequest;
  offersSpread?: boolean;
}): void {
  resetFixtureDb();
  fixtureResponse('POST', '/hero', { name: 'Lena', class: opts.heroClass ?? 'analyst' });
  fixtureResponse('POST', '/campaigns', { interests: ['Gaming'] });
  const db = readDb();
  if (!db.campaign) throw new Error('campaign not seeded');
  writeDb({
    ...db,
    decision: opts.decision ?? null,
    campaign: { ...db.campaign, phase: opts.phase, offers_spread: opts.offersSpread ?? true },
  });
}

export const investDecision: CommitRequest = {
  evidence: 'The debt figures worry me a lot',
  forecast_pct: 40,
  confidence: 'medium',
};
