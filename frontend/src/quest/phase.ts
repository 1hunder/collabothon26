import type { CampaignPhase } from '../api/types';

/** The single mapping from a server campaign phase to its quest route. */
export function phaseToPath(phase: CampaignPhase): string {
  switch (phase) {
    case 'setup':
    case 'play':
      return '/quest/play';
    case 'commit':
      return '/quest/commit';
    case 'timeskip':
    case 'reveal':
      return '/quest/outcome';
    case 'debrief':
      return '/quest/debrief';
    case 'reflect':
      return '/quest/reflect';
    case 'company':
      return '/quest/reveal';
    case 'xp':
      return '/quest/xp';
    case 'done':
      return '/quest/disclosure';
  }
}
