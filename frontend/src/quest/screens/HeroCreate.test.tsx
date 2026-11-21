import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fixtureResponse, resetFixtureDb } from '../../api/fixtures';
import { renderRoutes } from '../testUtils';
import { validateName } from '../lib/heroName';
import PhaseGuard from '../PhaseGuard';
import { HERO_CLASS_PATH } from '../setupNavigation';
import HeroCreate from './HeroCreate';

beforeEach(() => {
  vi.stubEnv('VITE_API_MODE', 'fixture');
  resetFixtureDb();
});
afterEach(() => vi.unstubAllEnvs());

function setup() {
  return renderRoutes(
    [
      { path: '/quest/hero/new', element: <HeroCreate /> },
      { path: '/quest/disclosure', element: <p>disclosure screen</p> },
    ],
    ['/quest/hero/new'],
  );
}

describe('validateName', () => {
  it('accepts 2-20 trimmed characters', () => {
    expect(validateName('Lena')).toBeNull();
    expect(validateName("  Anne-Marie O'Neil ")).toBeNull();
    expect(validateName('a'.repeat(20))).toBeNull();
  });
  it('rejects too short, only spaces, too long and odd characters', () => {
    expect(validateName('L')).toBe('length');
    expect(validateName('    ')).toBe('length');
    expect(validateName('a'.repeat(21))).toBe('length');
    expect(validateName('Lena!')).toBe('characters');
  });
});

describe('HeroCreate', () => {
  it('starts with Lena, three class cards and a disabled Begin', () => {
    setup();
    expect(screen.getByLabelText('Name')).toHaveValue('Lena');
    expect(screen.getAllByRole('radio')).toHaveLength(3);
    expect(screen.getByText('Safety Cushion — start each campaign with 120 HP (€1,200)')).toBeInTheDocument();
    expect(screen.getByText('Second Look — reroll one failed dice check per campaign')).toBeInTheDocument();
    expect(screen.getByText('Keen Eye — roll one dice check per campaign with advantage')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Begin' })).toBeDisabled();
  });

  it('shows the error and keeps Begin disabled for one character or only spaces', async () => {
    setup();
    await userEvent.click(screen.getByRole('radio', { name: /Guardian/ }));
    const input = screen.getByLabelText('Name');
    await userEvent.clear(input);
    await userEvent.type(input, 'L');
    expect(screen.getByRole('alert')).toHaveTextContent('Name must be 2–20 characters.');
    expect(screen.getByRole('button', { name: 'Begin' })).toBeDisabled();
    await userEvent.clear(input);
    await userEvent.type(input, '   ');
    expect(screen.getByRole('alert')).toHaveTextContent('Name must be 2–20 characters.');
    expect(screen.getByRole('button', { name: 'Begin' })).toBeDisabled();
  });

  it('does not accept a 21st character', async () => {
    setup();
    const input = screen.getByLabelText('Name');
    await userEvent.clear(input);
    await userEvent.type(input, 'abcdefghijklmnopqrstu');
    expect(input).toHaveValue('abcdefghijklmnopqrst');
  });

  it('highlights only the selected class and enables Begin', async () => {
    setup();
    const guardian = screen.getByRole('radio', { name: /Guardian/ });
    const analyst = screen.getByRole('radio', { name: /Analyst/ });
    await userEvent.click(analyst);
    expect(analyst).toHaveAttribute('aria-checked', 'true');
    expect(guardian).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('button', { name: 'Begin' })).toBeEnabled();
  });

  it('wraps keyboard selection and moves focus to the centered class', async () => {
    setup();
    screen.getByRole('radio', { name: /Guardian/ }).focus();
    await userEvent.keyboard('{ArrowRight}{ArrowRight}');
    const analyst = screen.getByRole('radio', { name: /Analyst/ });
    expect(analyst).toBeChecked();
    expect(analyst).toHaveFocus();
    expect(analyst).toHaveAttribute('data-position', 'center');
  });

  it('Begin creates the hero and opens the disclosure', async () => {
    const router = setup();
    await userEvent.click(screen.getByRole('radio', { name: /Investigator/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Begin' }));
    expect(await screen.findByText('disclosure screen')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/quest/disclosure');
  });

  it('lets a returning hero select a different class before the next game', async () => {
    const hero = fixtureResponse('POST', '/hero', { name: 'Mira', class: 'guardian' });
    const router = renderRoutes(
      [
        { path: HERO_CLASS_PATH, element: <PhaseGuard screen={HERO_CLASS_PATH}><HeroCreate chooseClass /></PhaseGuard> },
        { path: '/quest/disclosure', element: <p>disclosure screen</p> },
      ],
      [HERO_CLASS_PATH],
    );
    expect(await screen.findByRole('heading', { name: 'Choose your class' })).toBeInTheDocument();
    expect(screen.getByLabelText('Name')).toHaveValue('Mira');
    expect(screen.getByRole('radio', { name: /Guardian/ })).toBeChecked();
    await userEvent.click(screen.getByRole('radio', { name: /Analyst/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByText('disclosure screen')).toBeInTheDocument();
    expect(router.state.location.state).toMatchObject({ chooseClass: true });
    expect(fixtureResponse('GET', '/hero')).toEqual({ ...hero as object, class: 'analyst' });
  });
});
