import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearQuest,
  finishQuest,
  getDisclosureSeen,
  getQuestMeta,
  getScenarioId,
  markDisclosureSeen,
  saveProgress,
  setCampaign,
  startQuest,
  subscribe,
} from './questStore';

const KEY = 'fq.quest.v2';
const LEGACY = 'fq.quest.v1';

describe('questStore', () => {
  beforeEach(() => {
    clearQuest();
    localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fresh state is not in progress', () => {
    expect(getQuestMeta()).toMatchObject({ inProgress: false, resumePath: '/quest', scenarioId: null });
  });

  it('startQuest marks in progress at /quest', () => {
    startQuest();
    expect(getQuestMeta()).toMatchObject({ inProgress: true, resumePath: '/quest' });
  });

  it('saveProgress updates resumePath', () => {
    startQuest();
    saveProgress('/quest/step-2');
    expect(getQuestMeta()).toMatchObject({ inProgress: true, resumePath: '/quest/step-2' });
  });

  it('finishQuest is not in progress', () => {
    startQuest();
    finishQuest();
    expect(getQuestMeta()).toMatchObject({ inProgress: false, resumePath: '/quest' });
  });

  it('returns a stable snapshot when nothing changed', () => {
    startQuest();
    expect(getQuestMeta()).toBe(getQuestMeta());
  });

  it('discards corrupt JSON and removes the key', () => {
    localStorage.setItem(KEY, '{not json');
    expect(getQuestMeta().inProgress).toBe(false);
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it('discards another version and removes the key', () => {
    localStorage.setItem(
      KEY,
      JSON.stringify({ v: 3, status: 'in_progress', lastPath: '/quest/x', savedAt: 1 }),
    );
    expect(getQuestMeta()).toMatchObject({ inProgress: false, resumePath: '/quest' });
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it('works in memory when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    startQuest();
    saveProgress('/quest/mem');
    expect(getQuestMeta()).toMatchObject({ inProgress: true, resumePath: '/quest/mem' });
    finishQuest();
    expect(getQuestMeta().inProgress).toBe(false);
  });

  it('notifies subscribers on writes until unsubscribed', () => {
    const listener = vi.fn();
    const unsubscribe = subscribe(listener);
    startQuest();
    saveProgress('/quest/a');
    finishQuest();
    clearQuest();
    expect(listener).toHaveBeenCalledTimes(4);
    unsubscribe();
    startQuest();
    expect(listener).toHaveBeenCalledTimes(4);
  });

  it('writes the v2 record shape', () => {
    startQuest();
    setCampaign('c1', 's1');
    markDisclosureSeen();
    saveProgress('/quest/play');
    const stored = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Record<string, unknown>;
    expect(stored).toMatchObject({
      v: 2,
      status: 'in_progress',
      lastPath: '/quest/play',
      campaignId: 'c1',
      scenarioId: 's1',
      disclosureSeen: true,
    });
    expect(typeof stored.savedAt).toBe('number');
    expect(getScenarioId()).toBe('s1');
    expect(getDisclosureSeen()).toBe(true);
  });

  it('migrates a v1 record: keeps status and lastPath, nulls the campaign', () => {
    localStorage.setItem(
      LEGACY,
      JSON.stringify({ v: 1, status: 'in_progress', lastPath: '/quest/old', savedAt: 5, state: null }),
    );
    expect(getQuestMeta()).toMatchObject({
      inProgress: true,
      resumePath: '/quest/old',
      campaignId: null,
      scenarioId: null,
      disclosureSeen: false,
    });
    expect(localStorage.getItem(LEGACY)).toBeNull();
    expect(JSON.parse(localStorage.getItem(KEY) ?? '{}')).toMatchObject({ v: 2, lastPath: '/quest/old' });
  });

  it('discards an invalid v1 record', () => {
    localStorage.setItem(LEGACY, JSON.stringify({ v: 1, status: 'bogus' }));
    expect(getQuestMeta().inProgress).toBe(false);
    expect(localStorage.getItem(LEGACY)).toBeNull();
  });
});
