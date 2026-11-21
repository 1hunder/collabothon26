import type { DiceCard, NewsCard } from '../../api/types';

const str = (v: unknown, fallback = ''): string => (typeof v === 'string' ? v : fallback);
const int = (v: unknown, fallback = 0): number => (typeof v === 'number' ? v : fallback);

/** Accepts both `kind` (SSE card event) and `type` (JSON responses) as the discriminator. */
export function normalizeCard(raw: Record<string, unknown>): DiceCard | NewsCard | null {
  const kind = raw.kind ?? raw.type;
  if (kind === 'dice') {
    const challengeId = str(raw.challenge_id, str(raw.roll_id));
    return {
      kind: 'dice',
      roll_id: str(raw.roll_id, challengeId),
      challenge_id: challengeId,
      title: str(raw.title, 'A dice check'),
      dc: int(raw.dc),
      bonus: int(raw.bonus, 2),
      keen_eye_available: raw.keen_eye_available === true,
      keen_eye_left: int(raw.keen_eye_left),
    };
  }
  if (kind === 'news') {
    return {
      kind: 'news',
      headline: str(raw.headline),
      summary: str(raw.summary),
      time_skip_label: str(raw.time_skip_label),
      story_day: int(raw.story_day),
    };
  }
  return null;
}
