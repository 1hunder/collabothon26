import type { Interest } from '../api/types';

/**
 * The personal quest the player picked on the Finance Quest card, carried to "Find my quest".
 * Session-scoped: a stale pick never outlives the browser tab. Falls back to memory when storage
 * is unavailable.
 */
export interface QuestPick {
  scenarioId: string;
  category: string;
  categoryLabel: string;
}

const KEY = 'fq.pick.v1';
let memory: QuestPick | null = null;

const CATEGORY_INTEREST: Record<string, Interest> = {
  music: 'Music',
  sportswear: 'Fashion',
  fashion: 'Fashion',
  mobility: 'Mobility',
  food_delivery: 'Tech',
  gaming: 'Gaming',
};

export function interestFor(category: string): Interest | null {
  return CATEGORY_INTEREST[category] ?? null;
}

export function setQuestPick(pick: QuestPick | null): void {
  memory = pick;
  try {
    if (pick) window.sessionStorage.setItem(KEY, JSON.stringify(pick));
    else window.sessionStorage.removeItem(KEY);
  } catch {
    // memory fallback already set
  }
}

export function getQuestPick(): QuestPick | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (raw === null) return memory;
    const v = JSON.parse(raw) as Partial<QuestPick>;
    if (typeof v.scenarioId === 'string' && typeof v.category === 'string' && typeof v.categoryLabel === 'string') {
      return { scenarioId: v.scenarioId, category: v.category, categoryLabel: v.categoryLabel };
    }
  } catch {
    // corrupt or unavailable: fall through
  }
  return memory;
}
