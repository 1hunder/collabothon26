import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { fixtureResponse, resetFixtureDb } from '../../api/fixtures';
import { readDb } from '../../api/fixtures/db';
import { HERO_CLASS_PATH } from '../../quest/setupNavigation';
import { ACTION_DRAFT_KEY } from '../../quest/play/useSessionDraft';
import QuestCard from './QuestCard';
import { clearQuest, getQuestMeta, saveProgress, setCampaign } from '../../quest/questStore';

describe('QuestCard', () => {
  beforeEach(() => {
    clearQuest();
    localStorage.clear();
  });
  afterEach(cleanup);

  for (const [variant, label] of [
    ['overview', 'Start'],
    ['depot', 'Start your first quest'],
  ] as const) {
    it(`${variant}: shows ${label} and starting calls startQuest then onStart`, () => {
      const onStart = vi.fn();
      render(<QuestCard variant={variant} onStart={onStart} onContinue={vi.fn()} />);
      expect(screen.queryByText('Quest in progress')).toBeNull();
      fireEvent.click(screen.getByRole('button', { name: label }));
      expect(onStart).toHaveBeenCalledTimes(1);
      expect(getQuestMeta().inProgress).toBe(true);
    });

    it(`${variant}: in progress shows the line and Continue, which resumes`, () => {
      saveProgress('/quest/next');
      const onStart = vi.fn();
      const onContinue = vi.fn();
      render(<QuestCard variant={variant} onStart={onStart} onContinue={onContinue} />);
      expect(screen.getByText('Quest in progress')).toBeTruthy();
      expect(screen.queryByRole('button', { name: label })).toBeNull();
      fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
      expect(onContinue).toHaveBeenCalledWith('/quest/next');
      expect(onStart).not.toHaveBeenCalled();
    });
  }

  it('keeps the saved quest on Cancel and starts cleanly after confirmation', async () => {
    vi.stubEnv('VITE_API_MODE', 'fixture');
    resetFixtureDb();
    const hero = fixtureResponse('POST', '/hero', { name: 'Mira', class: 'guardian' });
    fixtureResponse('POST', '/campaigns', {});
    const campaign = readDb().campaign!;
    setCampaign(campaign.id, campaign.scenario_id);
    saveProgress('/quest/play');
    sessionStorage.setItem(ACTION_DRAFT_KEY, 'old draft');

    const dialog = HTMLDialogElement.prototype;
    const methods = {
      showModal(this: HTMLDialogElement) { this.setAttribute('open', ''); },
      close(this: HTMLDialogElement) { this.removeAttribute('open'); },
    };
    Object.assign(dialog, methods);
    try {
      const onStart = vi.fn();
      render(<QuestCard variant="overview" onStart={onStart} onContinue={vi.fn()} />);
      fireEvent.click(screen.getByRole('button', { name: 'New Game' }));
      fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }));
      expect(readDb().campaign?.id).toBe(campaign.id);
      expect(getQuestMeta().resumePath).toBe('/quest/play');
      expect(onStart).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole('button', { name: 'New Game' }));
      fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Start new game' }));
      await waitFor(() => expect(onStart).toHaveBeenCalledWith(HERO_CLASS_PATH));
      expect(readDb().campaign).toBeNull();
      expect(readDb().hero).toEqual(hero);
      expect(getQuestMeta()).toMatchObject({ inProgress: true, campaignId: null, resumePath: HERO_CLASS_PATH });
      expect(sessionStorage.getItem(ACTION_DRAFT_KEY)).toBeNull();
    } finally {
      cleanup();
      Reflect.deleteProperty(dialog, 'showModal');
      Reflect.deleteProperty(dialog, 'close');
      vi.unstubAllEnvs();
      resetFixtureDb();
    }
  });
});
