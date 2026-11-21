import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import type { UserEvent } from '@testing-library/user-event';
import { vi } from 'vitest';
import { fixtureResponse, resetFixtureDb } from '../../api/fixtures';
import type { HeroClass } from '../../api/types';
import { clearQuest } from '../questStore';
import { renderRoutes } from '../testUtils';
import PlayScreen from './PlayScreen';

/** A fixture hero and campaign, rendered on /quest/play. */
export function setupPlay(heroClass: HeroClass = 'analyst', props: React.ComponentProps<typeof PlayScreen> = {}): ReturnType<typeof renderRoutes> {
  vi.stubEnv('VITE_API_MODE', 'fixture');
  resetFixtureDb();
  clearQuest();
  window.localStorage.clear();
  window.sessionStorage.clear();
  fixtureResponse('POST', '/hero', { name: 'Mira', class: heroClass });
  fixtureResponse('POST', '/campaigns', { interests: ['Tech'] });
  return renderRoutes(
    [
      { path: '/quest/play', element: <PlayScreen {...props} /> },
      { path: '/quest/commit', element: <p>commit screen</p> },
      { path: '/quest/hero', element: <p>hero screen</p> },
    ],
    ['/quest/play'],
  );
}

export async function openBuddy(user: UserEvent): Promise<void> {
  const mascot = screen.getByRole('button', { name: 'Chat with CommerzBuddy' });
  await user.click(mascot);
  // React falls back to the WebKit event when jsdom lacks AnimationEvent.
  const end = 'AnimationEvent' in window ? 'animationend' : 'webkitAnimationEnd';
  fireEvent(mascot.querySelector('.buddy-frames')!, new Event(end, { bubbles: true }));
}

const choices = (): HTMLElement | null => screen.queryByRole('region', { name: 'Choices' });

/** Tap through every page of the current reply until the choices appear (or an overlay opens). */
export async function readToChoices(user: UserEvent, stopAt: () => boolean = () => false): Promise<void> {
  await waitFor(() => expect(screen.queryByTestId('dialogue-box') ?? choices()).not.toBeNull());
  for (let i = 0; i < 24; i += 1) {
    if (choices() || stopAt()) return;
    const box = screen.queryByTestId('dialogue-box');
    if (box) await user.click(box);
    else await new Promise((r) => window.setTimeout(r, 10));
  }
}

export async function skipTitle(user: UserEvent): Promise<void> {
  const card = screen.queryByTestId('title-card');
  if (card) await user.click(card);
}

/** Pages through the Library parchment from the first page and returns the text of every page. */
export async function readParchment(user: UserEvent, dialog: HTMLElement): Promise<string> {
  const d = within(dialog);
  while (!(d.getByRole('button', { name: 'Previous page' }) as HTMLButtonElement).disabled) await user.click(d.getByRole('button', { name: 'Previous page' }));
  let text = '';
  for (;;) {
    text += ` ${d.getByTestId('parchment-page').textContent ?? ''}`;
    const next = d.getByRole('button', { name: 'Next page' }) as HTMLButtonElement;
    if (next.disabled) return text;
    await user.click(next);
  }
}
