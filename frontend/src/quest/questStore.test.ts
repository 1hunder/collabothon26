import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearQuest,
  finishQuest,
  getQuestMeta,
  saveProgress,
  startQuest,
  subscribe,
} from './questStore';

const KEY = 'fq.quest.v1';

describe('questStore', () => {
  beforeEach(() => {
    clearQuest();
    localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fresh state is not in progress', () => {
    expect(getQuestMeta()).toEqual({ inProgress: false, resumePath: '/quest' });
  });

  it('startQuest marks in progress at /quest', () => {
    startQuest();
    expect(getQuestMeta()).toEqual({ inProgress: true, resumePath: '/quest' });
  });

  it('saveProgress updates resumePath', () => {
    startQuest();
    saveProgress('/quest/step-2', { a: 1 });
    expect(getQuestMeta()).toEqual({ inProgress: true, resumePath: '/quest/step-2' });
  });

  it('finishQuest is not in progress', () => {
    startQuest();
    finishQuest();
    expect(getQuestMeta()).toEqual({ inProgress: false, resumePath: '/quest' });
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

  it('discards wrong version and removes the key', () => {
    localStorage.setItem(
      KEY,
      JSON.stringify({ v: 2, status: 'in_progress', lastPath: '/quest/x', savedAt: 1, state: null }),
    );
    expect(getQuestMeta()).toEqual({ inProgress: false, resumePath: '/quest' });
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
    saveProgress('/quest/mem', 1);
    expect(getQuestMeta()).toEqual({ inProgress: true, resumePath: '/quest/mem' });
    finishQuest();
    expect(getQuestMeta().inProgress).toBe(false);
  });

  it('notifies subscribers on writes until unsubscribed', () => {
    const listener = vi.fn();
    const unsubscribe = subscribe(listener);
    startQuest();
    saveProgress('/quest/a', null);
    finishQuest();
    clearQuest();
    expect(listener).toHaveBeenCalledTimes(4);
    unsubscribe();
    startQuest();
    expect(listener).toHaveBeenCalledTimes(4);
  });
});
