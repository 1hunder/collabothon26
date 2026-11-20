import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import QuestCard from './QuestCard';
import { clearQuest, getQuestMeta, saveProgress } from '../../quest/questStore';

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
      saveProgress('/quest/next', null);
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
});
