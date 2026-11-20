import type { CampaignPhase } from '../api/types';
import { phaseToPath } from './phase';

describe('phaseToPath', () => {
  const cases: [CampaignPhase, string][] = [
    ['setup', '/quest/play'],
    ['play', '/quest/play'],
    ['commit', '/quest/commit'],
    ['timeskip', '/quest/outcome'],
    ['reveal', '/quest/outcome'],
    ['debrief', '/quest/debrief'],
    ['reflect', '/quest/reflect'],
    ['company', '/quest/reveal'],
    ['xp', '/quest/xp'],
    ['done', '/quest/interests'],
  ];
  it.each(cases)('%s -> %s', (phase, path) => {
    expect(phaseToPath(phase)).toBe(path);
  });
});
