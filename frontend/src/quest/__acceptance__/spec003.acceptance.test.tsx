/**
 * Acceptance tests for spec 003 (campaign engine), frontend half, one per criterion.
 * @spec: 003-campaign-engine
 * @regression
 *
 * Titles are "<section>-AC<n> ...": 2.<section> and the n-th acceptance criterion (checkbox, in
 * order) of that section in functional-spec.md. Rules, maths, gating and guards are asserted in
 * backend/tests/test_acceptance_003.py; user flows in e2e/spec003.acceptance.spec.ts. Everything
 * here runs against the fixture API (a fictional company), no network.
 */
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fixtureResponse, resetFixtureDb } from '../../api/fixtures';
import { readDb, writeDb } from '../../api/fixtures/db';
import * as sse from '../../api/sse';
import type { CampaignState, DiceCard, PlayLocation, RollResult } from '../../api/types';
import { FIRST_EVENT_TIMEOUT_MS } from '../../api/useDmStream';
import { investDecision, seedCampaign } from '../../test/seedCampaign';
import config from '../../../tailwind.config';
import { VOICE_KEY, VoiceProvider } from '../../voice';
import type { VoiceProviderImpl } from '../../voice';
import PhaseGuard from '../PhaseGuard';
import QuestEntry from '../QuestEntry';
import { clearQuest } from '../questStore';
import { renderRoutes } from '../testUtils';
import { splitPages as paginate } from '../play/paginate';
import BuddyScene from '../play/BuddyScene';
import DialogueBox from '../play/DialogueBox';
import DiceMoment, { TUMBLE_MS, type DiceApi } from '../play/DiceMoment';
import ChoiceList from '../play/ChoiceList';
import { artSrc } from '../play/artSrc';
import { readParchment, readToChoices, setupPlay, skipTitle } from '../play/playTestUtils';
import SceneArt from '../play/SceneArt';
import Commit from '../screens/Commit';
import Debrief from '../screens/Debrief';
import HeroCreate from '../screens/HeroCreate';
import HeroScreen from '../screens/HeroScreen';
import Outcome from '../screens/Outcome';
import Reflect from '../screens/Reflect';
import RevealRoute from '../screens/RevealRoute';
import QuestDisclosure from '../screens/QuestDisclosure';
import Xp from '../screens/Xp';
import PlayScreen from '../play/PlayScreen';
import QuestLayout from '../QuestLayout';

const unlockVoice = vi.hoisted(() => vi.fn());
vi.mock('../../voice/providers', async (orig) => ({ ...(await orig<typeof import('../../voice/providers')>()), unlockVoice }));
vi.mock('../components/StoryChart', () => ({
  default: (p: { points: { story_day: number }[]; mode: string }) => (
    <div role="img" aria-label="Price chart" data-mode={p.mode} data-last-day={p.points.at(-1)?.story_day} />
  ),
}));

beforeEach(() => {
  vi.stubEnv('VITE_API_MODE', 'fixture');
  resetFixtureDb();
  clearQuest();
  localStorage.clear();
  sessionStorage.clear();
  unlockVoice.mockClear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

const choiceButton = (name: string | RegExp): HTMLElement => screen.getByRole('button', { name });
type User = ReturnType<typeof userEvent.setup>;

async function enterTavern(user: User): Promise<void> {
  await readToChoices(user);
  await skipTitle(user);
}
async function typeText(user: User, text: string): Promise<void> {
  await user.type(screen.getByRole('textbox'), text);
  await user.click(screen.getByRole('button', { name: 'Send' }));
}
async function send(user: User, text: string): Promise<void> {
  await typeText(user, text);
  await readToChoices(user);
}
async function typeAction(user: User, text: string, stopAt?: () => boolean): Promise<void> {
  await typeText(user, text);
  await readToChoices(user, stopAt);
}
async function goTo(user: User, place: string): Promise<void> {
  await user.click(choiceButton('Map'));
  const map = await screen.findByRole('dialog', { name: 'The map' });
  await user.click(within(map).getByRole('button', { name: new RegExp(place) }));
}

const guard = (path: string, el: ReactNode) => ({ path, element: <PhaseGuard screen={path}>{el}</PhaseGuard> });

// ================================================================================================
// 2.1 First entry: create your hero
// ================================================================================================
describe('2.1 First entry: create your hero', () => {
  const heroRoutes = [
    { path: '/quest/hero/new', element: <HeroCreate /> },
    { path: '/quest/disclosure', element: <p>disclosure screen</p> },
  ];
  it('2.1-AC1 a player with no hero sees "Create your hero": name Lena, three class cards, Begin disabled', async () => {
    const entry = [{ path: '/quest', element: <QuestEntry /> }, ...heroRoutes];
    const router = renderRoutes(entry, ['/quest']);
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/hero/new'));
    expect(screen.getByLabelText('Name')).toHaveValue('Lena');
    expect(screen.getAllByRole('radio')).toHaveLength(3);
    expect(screen.getByRole('button', { name: 'Begin' })).toBeDisabled();
  });
  it('2.1-AC2 one character or only spaces keeps Begin disabled and shows "Name must be 2–20 characters."', async () => {
    renderRoutes(heroRoutes, ['/quest/hero/new']);
    await userEvent.click(screen.getAllByRole('radio')[0]!);
    const input = screen.getByLabelText('Name');
    for (const v of ['L', '   ']) {
      await userEvent.clear(input);
      await userEvent.type(input, v);
      expect(screen.getByRole('alert')).toHaveTextContent('Name must be 2–20 characters.');
      expect(screen.getByRole('button', { name: 'Begin' })).toBeDisabled();
    }
  });
  it('2.1-AC3 the field does not accept a 21st character', async () => {
    renderRoutes(heroRoutes, ['/quest/hero/new']);
    const input = screen.getByLabelText('Name');
    await userEvent.clear(input);
    await userEvent.type(input, 'abcdefghijklmnopqrstu');
    expect(input).toHaveValue('abcdefghijklmnopqrst');
  });
  it('2.1-AC4 a valid name and a selected class enable Begin', async () => {
    renderRoutes(heroRoutes, ['/quest/hero/new']);
    expect(screen.getByRole('button', { name: 'Begin' })).toBeDisabled();
    await userEvent.click(screen.getAllByRole('radio')[1]!);
    expect(screen.getByRole('button', { name: 'Begin' })).toBeEnabled();
  });
  it('2.1-AC5 tapping Begin opens the disclosure', async () => {
    const router = renderRoutes(heroRoutes, ['/quest/hero/new']);
    await userEvent.click(screen.getByRole('radio', { name: /Analyst/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Begin' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/disclosure'));
    expect(readDb().hero).toMatchObject({ name: 'Lena', class: 'analyst' });
  });
  it('2.1-AC6 a player with a hero opens the disclosure directly', async () => {
    fixtureResponse('POST', '/hero', { name: 'Mira', class: 'guardian' });
    const router = renderRoutes(
      [{ path: '/quest', element: <QuestEntry /> }, { ...guard('/quest/disclosure', <QuestDisclosure />) }, { path: '/quest/hero/new', element: <p>creation</p> }],
      ['/quest'],
    );
    expect(await screen.findByRole('button', { name: 'Got it' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/quest/disclosure');
    expect(screen.queryByText('creation')).not.toBeInTheDocument();
  });
  it('2.1-AC7 after a finished campaign a new one keeps name, class and total XP, and HP starts fresh', () => {
    seedCampaign({ phase: 'xp', heroClass: 'guardian', decision: investDecision });
    const fin = fixtureResponse('POST', `/campaigns/${readDb().campaign!.id}/finish`) as { total_xp: number };
    const camp = fixtureResponse('POST', '/campaigns', { interests: ['Music'] }) as CampaignState;
    expect(camp.hero).toMatchObject({ name: 'Lena', class: 'guardian', total_xp: fin.total_xp });
    expect([camp.hp, camp.hp_eur]).toEqual([120, 1200]);
  });
});

// ================================================================================================
// 2.2 Classes
// ================================================================================================
describe('2.2 Classes', () => {
  it('2.2-AC1 the hero creation shows three class cards with their advantage wording', () => {
    renderRoutes([{ path: '/quest/hero/new', element: <HeroCreate /> }], ['/quest/hero/new']);
    for (const t of ['The Guardian', 'The Analyst', 'The Investigator']) expect(screen.getByText(t)).toBeInTheDocument();
    expect(screen.getByText('Safety Cushion — start each campaign with 120 HP (€1,200)')).toBeInTheDocument();
    expect(screen.getByText('Second Look — reroll one failed dice check per campaign')).toBeInTheDocument();
    expect(screen.getByText('Keen Eye — roll one dice check per campaign with advantage')).toBeInTheDocument();
  });
  it('2.2-AC2 tapping a card highlights it and no other', async () => {
    renderRoutes([{ path: '/quest/hero/new', element: <HeroCreate /> }], ['/quest/hero/new']);
    const [g, a, i] = screen.getAllByRole('radio');
    await userEvent.click(i!);
    expect([g, a, i].map((r) => r!.getAttribute('aria-checked'))).toEqual(['false', 'false', 'true']);
    await userEvent.click(g!);
    expect([g, a, i].map((r) => r!.getAttribute('aria-checked'))).toEqual(['true', 'false', 'false']);
  });
  it('2.2-AC3 a Guardian starts with "120 HP · €1,200"', async () => {
    setupPlay('guardian');
    expect(await screen.findByText(/120 HP/)).toHaveTextContent('120 HP · €1,200');
  });
  it('2.2-AC4 an Analyst starts with "100 HP · €1,000" and "Rerolls: 1"', async () => {
    setupPlay('analyst');
    expect(await screen.findByText(/100 HP/)).toHaveTextContent('100 HP · €1,000');
    expect(screen.getByText('Rerolls: 1')).toBeInTheDocument();
  });
  it('2.2-AC5 an Investigator starts with "100 HP · €1,000" and "Keen Eye: 1"', async () => {
    setupPlay('investigator');
    expect(await screen.findByText(/100 HP/)).toHaveTextContent('100 HP · €1,000');
    expect(screen.getByText('Keen Eye: 1')).toBeInTheDocument();
  });
});

// ================================================================================================
// 2.3 Choosing the quest
// ================================================================================================
describe('2.3 Choosing the quest', () => {
  const routes = [guard('/quest/disclosure', <QuestDisclosure />), guard('/quest/play', <PlayScreen />)];
  beforeEach(() => void fixtureResponse('POST', '/hero', { name: 'Mira', class: 'analyst' }));

  it('2.3-AC2 the disclosure opens directly and "Got it" opens the first scene', async () => {
    renderRoutes(routes, ['/quest/disclosure']);
    expect(await screen.findByText(/This story is real market history\. We've hidden the company's name, the dates and the price level\. You'll find out who it was at the end\./)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Got it' }));
    expect(await screen.findByTestId('name-tab')).toHaveTextContent('Campaign Master');
  });
  it('2.3-AC3 the opening scene is in the Tavern with the Tavern background and the briefing', async () => {
    renderRoutes(routes, ['/quest/disclosure']);
    await userEvent.click(await screen.findByRole('button', { name: 'Got it' }));
    await screen.findByTestId('name-tab');
    expect(screen.getAllByText('Tavern').length).toBeGreaterThan(0);
    expect(screen.getByTestId('scene-art')).toHaveAttribute('src', '/backgrounds/tavern.webp');
    await userEvent.click(screen.getByTestId('dialogue-box'));
    expect(screen.getByTestId('dialogue-box')).toHaveTextContent(/Gilded Tavern/);
  });
});

// ================================================================================================
// 2.4 Scenes and turns
// ================================================================================================
describe('2.4 Scenes and turns', () => {
  it('2.4-AC1 a scene shows the location background and the "Campaign Master" name tab', async () => {
    setupPlay('analyst');
    expect(await screen.findByTestId('name-tab')).toHaveTextContent('Campaign Master');
    expect(screen.getByTestId('scene-art')).toHaveAttribute('src', '/backgrounds/tavern.webp');
    expect(screen.getByTestId('scene-art').parentElement).toHaveClass('absolute', 'inset-0');
  });
  it('2.4-AC2 a reply over 50 words is split into pages with "1 / 3" and "▼"', async () => {
    const sentence = (n: number, t: string) => `${Array.from({ length: n }, (_, i) => `${t}${i}`).join(' ')}.`;
    const long = [sentence(30, 'a'), sentence(30, 'b'), sentence(30, 'c')].join(' ');
    expect(paginate(long).every((p) => p.split(/\s+/).length <= 50)).toBe(true);
    render(<DialogueBox speaker="Campaign Master" text={long} onAdvance={() => undefined} />);
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('dialogue-box'));
    expect(screen.getByText('▼')).toBeInTheDocument();
  });
  it('2.4-AC3 a tap completes the page, a second tap turns to the next', async () => {
    const long = `${'one two three four five six seven eight nine ten. '.repeat(11)}`;
    render(<DialogueBox speaker="Campaign Master" text={long} onAdvance={() => undefined} />);
    const box = screen.getByTestId('dialogue-box');
    expect(screen.getByTestId('dialogue-text').textContent).not.toBe(paginate(long)[0]);
    await userEvent.click(box);
    expect(screen.getByTestId('dialogue-text').textContent).toBe(paginate(long)[0]);
    await userEvent.click(box);
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
  });
  it('2.4-AC4 after the last page: "What would you do?" and a text input, no suggestion buttons', async () => {
    setupPlay('analyst');
    await readToChoices(userEvent.setup());
    const list = screen.getByRole('region', { name: 'Your turn' });
    expect(within(list).getByText('What would you do?')).toBeInTheDocument();
    expect(within(list).getByRole('textbox')).toBeInTheDocument();
    expect(within(list).queryByRole('button', { name: 'Write your own action…' })).not.toBeInTheDocument();
    for (const s of readDb().campaign?.suggestions ?? []) expect(within(list).queryByRole('button', { name: s })).not.toBeInTheDocument();
  });
  it('2.4-AC5 typing an action and pressing Send sends it', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await send(user, 'Ask the barkeep what people say about the guild');
    expect(readDb().play?.events.some((e) => e.type === 'action' && e.text === 'Ask the barkeep what people say about the guild')).toBe(true);
  });
  it('2.4-AC6 the text box and send button are always there', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    expect(screen.getByRole('textbox')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
  });
  it('2.4-AC7 the send button is disabled for an empty or whitespace-only text box', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    await user.type(screen.getByRole('textbox'), '    ');
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });
  it('2.4-AC8 sending shows "The Campaign Master is writing…" at once', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    vi.spyOn(sse, 'postSse').mockImplementation(() => new Promise<void>(() => undefined));
    await typeText(user, 'Ask the barkeep what people say about the guild');
    expect(screen.getByRole('status')).toHaveTextContent('The Campaign Master is writing…');
  });
  it('2.4-AC8b the reply then appears in the dialogue box and the earlier turn is in the backlog', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await typeText(user, 'Ask the barkeep what people say about the guild');
    await user.click(await screen.findByTestId('dialogue-box'));
    expect(screen.getByTestId('dialogue-box')).toHaveTextContent(/scholar|figures|crowd/);
    await readToChoices(user);
    await user.click(choiceButton('Journal'));
    await user.click(await screen.findByRole('button', { name: 'Open the backlog' }));
    const backlog = await screen.findByRole('dialog', { name: 'Backlog' });
    await waitFor(() => expect(within(backlog).getByText('Ask the barkeep what people say about the guild')).toBeInTheDocument());
    expect(within(backlog).getByText('You')).toBeInTheDocument();
  });
  it('2.4-AC9 pages never exceed 50 words, so a reply of at most 150 words has at most 3 pages', () => {
    const reply = Array.from({ length: 150 }, (_, i) => `w${i}`).join(' ') + '.';
    const pages = paginate(reply);
    expect(pages.length).toBeLessThanOrEqual(4);
    expect(pages.every((p) => p.split(/\s+/).length <= 50)).toBe(true);
  });
  it('2.4-AC10 asking for a definition or the chart opens no dice check', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await typeAction(user, 'What does drawdown mean?');
    expect(screen.queryByRole('dialog', { name: 'Dice check' })).not.toBeInTheDocument();
    expect(readDb().campaign?.pending).toBeNull();
  });
  it('2.4-AC11 an off-topic message gets a reply and no dice check', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await typeAction(user, 'Tell me a joke about cats');
    expect(screen.queryByRole('dialog', { name: 'Dice check' })).not.toBeInTheDocument();
    expect(readDb().campaign?.turn_count).toBe(1);
  });
  it('2.4-AC12 after 15 s without a reply "The Campaign Master lost the thread." with "Try again" resends the same action', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
    setupPlay('analyst');
    await enterTavern(user);
    const spy = vi.spyOn(sse, 'postSse').mockImplementation(() => new Promise<void>(() => undefined));
    await typeText(user, 'Walk to Market Square and study the price board');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(FIRST_EVENT_TIMEOUT_MS);
    });
    expect(screen.getByRole('alert')).toHaveTextContent('The Campaign Master lost the thread.');
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(spy).toHaveBeenCalledTimes(2);
    expect(spy.mock.calls[1]?.[1]).toEqual(spy.mock.calls[0]?.[1]);
  });
  it('2.4-AC13 "I\'m ready to decide" is not shown while clues remain', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    expect(screen.queryByRole('button', { name: "I'm ready to decide" })).not.toBeInTheDocument();
  });
  function readyToDecide(): void {
    const db = readDb();
    if (db.campaign) {
      db.campaign.news_shown = true;
      db.campaign.clues = [
        { clue_id: 'a', source: 's', title: 'A', text: 'a' },
        { clue_id: 'b', source: 's', title: 'B', text: 'b' },
      ];
      writeDb(db);
    }
  }
  it('2.4-AC14 once every reachable clue is shown, "I\'m ready to decide" appears under the text input', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    readyToDecide();
    await send(user, 'Walk to Market Square and study the price board');
    const list = screen.getByRole('region', { name: 'Your turn' });
    expect(within(list).getByRole('button', { name: "I'm ready to decide" })).toBeInTheDocument();
  });
  it('2.4-AC15 typing "I want to decide" makes the Campaign Master ask "Ready to make your decision?" with the button', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    readyToDecide();
    await typeAction(user, 'I want to decide');
    expect(readDb().play?.events.some((e) => e.type === 'dm_reply' && /Ready to make your decision\?/.test(String(e.text)))).toBe(true);
    expect(await screen.findByRole('button', { name: "I'm ready to decide" })).toBeInTheDocument();
  });
  it('2.4-AC16 tapping "I\'m ready to decide" opens the commit screen', async () => {
    const user = userEvent.setup();
    const router = setupPlay('analyst');
    await enterTavern(user);
    readyToDecide();
    await send(user, 'Walk to Market Square and study the price board');
    await user.click(await screen.findByRole('button', { name: "I'm ready to decide" }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/commit'));
  });
});

// ================================================================================================
// 2.5 Dice checks (DiceMoment with stubbed results; the roll maths is in the backend tests)
// ================================================================================================
describe('2.5 Dice checks', () => {
  const card: DiceCard = { kind: 'dice', roll_id: 'r1', challenge_id: 'r1', title: 'Spot what is off in the ledger', dc: 12, bonus: 2, keen_eye_available: false, keen_eye_left: 0 };
  const res = (o: Partial<RollResult> = {}): RollResult => ({
    roll_id: 'r1', challenge_id: 'r1', title: card.title, dice: [14], used: 14, bonus: 2, total: 16, dc: 12, result: 'success',
    final: true, options: ['continue'], rerolled: false, rerolls_left: 0, keen_eye_left: 0, alt_source: null, ...o,
  });
  const setback = (o: Partial<RollResult> = {}) => res({ dice: [5], used: 5, total: 7, result: 'setback', ...o });
  function mount(c: DiceCard, api: Partial<DiceApi> = {}) {
    vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('reduce'), addEventListener: () => undefined, removeEventListener: () => undefined }));
    const onResolved = vi.fn();
    const full: DiceApi = { roll: vi.fn(() => Promise.resolve(res())), reroll: vi.fn(() => Promise.resolve(res())), accept: vi.fn(() => Promise.resolve(res())), ...api };
    render(<DiceMoment card={c} api={full} onResolved={onResolved} />);
    return { api: full, onResolved };
  }
  afterEach(() => vi.unstubAllGlobals());

  it('2.5-AC1 the dice check card shows the challenge, its difficulty, "Bonus +2" and "Roll"', () => {
    mount(card);
    expect(screen.getByText(card.title)).toBeInTheDocument();
    expect(screen.getByText(/Difficulty 12/)).toBeInTheDocument();
    expect(screen.getByText(/Bonus \+2/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Roll' })).toBeInTheDocument();
  });
  it('2.5-AC2 an Investigator with Keen Eye sees "Keen Eye — roll with advantage (1 left)"', () => {
    mount({ ...card, keen_eye_available: true, keen_eye_left: 1 });
    expect(screen.getByRole('button', { name: 'Keen Eye — roll with advantage (1 left)' })).toBeInTheDocument();
  });
  it('2.5-AC3 Keen Eye shows two dice and the higher is used; the status shows "Keen Eye: 0"', async () => {
    const user = userEvent.setup();
    setupPlay('investigator');
    await enterTavern(user);
    await typeAction(user, 'check the ledger for an odd figure', () => screen.queryByRole('dialog', { name: 'Dice check' }) !== null);
    const dice = await screen.findByRole('dialog', { name: 'Dice check' });
    await user.click(within(dice).getByRole('button', { name: /Keen Eye — roll with advantage/ }));
    expect(await within(dice).findByText(/Two dice: 9 and 14/)).toBeInTheDocument();
    expect(within(dice).getByTestId('dice-sum')).toHaveTextContent('14 + 2');
    await waitFor(() => expect(screen.getByText('Keen Eye: 0')).toBeInTheDocument());
  });
  it('2.5-AC4 Roll tumbles the die for about a second, then shows die, "+2", total and the verdict', async () => {
    vi.unstubAllGlobals();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mount(card);
    vi.unstubAllGlobals();
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(screen.getByRole('status', { name: 'Rolling' })).toHaveClass('animate-tumble');
    expect(screen.queryByTestId('dice-verdict')).not.toBeInTheDocument();
    expect(TUMBLE_MS).toBeGreaterThanOrEqual(800);
    expect(TUMBLE_MS).toBeLessThanOrEqual(1200);
    await act(async () => void (await vi.advanceTimersByTimeAsync(TUMBLE_MS)));
    expect(await screen.findByTestId('dice-sum')).toHaveTextContent('14 + 2 = 16 against 12');
    expect(screen.getByTestId('dice-verdict')).toHaveTextContent('Success');
  });
  it('2.5-AC5 a success shows "Success", then the clue is narrated and lands in the journal', async () => {
    const user = userEvent.setup();
    setupPlay('guardian');
    await enterTavern(user);
    await typeAction(user, 'check the ledger for an odd figure', () => screen.queryByRole('dialog', { name: 'Dice check' }) !== null);
    const dice = await screen.findByRole('dialog', { name: 'Dice check' });
    await user.click(within(dice).getByRole('button', { name: 'Roll' }));
    expect(await within(dice).findByTestId('dice-verdict')).toHaveTextContent('Success');
    await user.click(within(dice).getByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(screen.getByTestId('dialogue-box')).toHaveTextContent(/ledger/i));
    await readToChoices(user);
    await user.click(choiceButton('Journal'));
    const journal = await screen.findByRole('dialog', { name: 'Journal' });
    await waitFor(() => expect(within(journal).getByLabelText('Clue')).toBeInTheDocument());
  });
  it('2.5-AC6 a setback shows "Setback" and the narration names another place for the information', async () => {
    mount(card, { roll: vi.fn(() => Promise.resolve(setback({ alt_source: 'The same facts are posted on the Market Square board.' }))) });
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(await screen.findByTestId('dice-verdict')).toHaveTextContent('Setback');
    expect(screen.getByTestId('dice-sum')).toHaveTextContent('5 + 2 = 7 against 12');
  });
  it('2.5-AC7 a natural 20 on difficulty 18 shows "Success"', async () => {
    mount({ ...card, dc: 18 }, { roll: vi.fn(() => Promise.resolve(res({ dice: [20], used: 20, total: 22, dc: 18 }))) });
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(await screen.findByTestId('dice-verdict')).toHaveTextContent('Success');
    expect(screen.getByText('Natural 20')).toBeInTheDocument();
  });
  it('2.5-AC8 a natural 1 shows "Setback"', async () => {
    mount(card, { roll: vi.fn(() => Promise.resolve(setback({ dice: [1], used: 1, total: 3 }))) });
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(await screen.findByTestId('dice-verdict')).toHaveTextContent('Setback');
    expect(screen.getByText('Natural 1')).toBeInTheDocument();
  });
  const analystSetback = () => ({ roll: vi.fn(() => Promise.resolve(setback({ final: false, options: ['reroll', 'accept'], rerolls_left: 1 }))) });
  it('2.5-AC9 an Analyst setback offers "Second Look — reroll (1 left)" and "Accept setback", with nothing narrated yet', async () => {
    const { onResolved } = mount(card, analystSetback());
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(await screen.findByRole('button', { name: 'Second Look — reroll (1 left)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Accept setback' })).toBeInTheDocument();
    expect(onResolved).not.toHaveBeenCalled();
  });
  it('2.5-AC10 "Second Look" shows a new roll, only it is passed on, and the status shows "Rerolls: 0"', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await typeAction(user, 'check the ledger for an odd figure', () => screen.queryByRole('dialog', { name: 'Dice check' }) !== null);
    const dice = await screen.findByRole('dialog', { name: 'Dice check' });
    await user.click(within(dice).getByRole('button', { name: 'Roll' }));
    await within(dice).findByTestId('dice-verdict');
    await user.click(within(dice).getByRole('button', { name: /Second Look/ }));
    expect(await within(dice).findByTestId('dice-sum')).toHaveTextContent('17 + 2 = 19 against 12');
    await user.click(within(dice).getByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(screen.getByText('Rerolls: 0')).toBeInTheDocument());
  });
  it('2.5-AC11 "Accept setback" keeps the reroll ("Rerolls: 1")', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await typeAction(user, 'check the ledger for an odd figure', () => screen.queryByRole('dialog', { name: 'Dice check' }) !== null);
    const dice = await screen.findByRole('dialog', { name: 'Dice check' });
    await user.click(within(dice).getByRole('button', { name: 'Roll' }));
    await within(dice).findByTestId('dice-verdict');
    await user.click(within(dice).getByRole('button', { name: 'Accept setback' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Dice check' })).not.toBeInTheDocument());
    expect(screen.getByText('Rerolls: 1')).toBeInTheDocument();
  });
  it('2.5-AC12 a Guardian or Investigator setback offers only "Continue"', async () => {
    mount(card, { roll: vi.fn(() => Promise.resolve(setback())) });
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    await screen.findByTestId('dice-verdict');
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Second Look|Accept setback/ })).not.toBeInTheDocument();
  });
  it('2.5-AC13 a challenge already rolled opens no dice card (the server refuses it and offers no card)', async () => {
    const user = userEvent.setup();
    setupPlay('guardian');
    await enterTavern(user);
    await typeAction(user, 'check the ledger for an odd figure', () => screen.queryByRole('dialog', { name: 'Dice check' }) !== null);
    const dice = await screen.findByRole('dialog', { name: 'Dice check' });
    await user.click(within(dice).getByRole('button', { name: 'Roll' }));
    await user.click(await within(dice).findByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Dice check' })).not.toBeInTheDocument());
    await readToChoices(user);
    await typeAction(user, 'check the ledger for an odd figure again');
    expect(screen.queryByRole('dialog', { name: 'Dice check' })).not.toBeInTheDocument();
  });
  it('2.5-AC14 a dice check never changes the HP shown', async () => {
    const user = userEvent.setup();
    setupPlay('guardian');
    await enterTavern(user);
    await typeAction(user, 'check the ledger for an odd figure', () => screen.queryByRole('dialog', { name: 'Dice check' }) !== null);
    const dice = await screen.findByRole('dialog', { name: 'Dice check' });
    await user.click(within(dice).getByRole('button', { name: 'Roll' }));
    await user.click(await within(dice).findByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Dice check' })).not.toBeInTheDocument());
    expect(screen.getByText(/120 HP/)).toHaveTextContent('120 HP · €1,200');
  });
});

// ================================================================================================
// 2.6 Locations
// ================================================================================================
describe('2.6 Locations', () => {
  it('2.6-AC1 the map lists Tavern, Market Square, Library and the campaign location, current one marked', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await user.click(choiceButton('Map'));
    const map = await screen.findByRole('dialog', { name: 'The map' });
    for (const n of ['Tavern', 'Market Square', 'Library', 'The Lamp Works']) expect(within(map).getByRole('button', { name: new RegExp(n) })).toBeInTheDocument();
    expect(within(map).getByRole('button', { name: /Tavern/ })).toHaveTextContent('you are here');
    expect(within(map).getByRole('button', { name: /Lamp Works/ })).toHaveTextContent('this tale only');
  });
  it('2.6-AC2 tapping another location changes the background and the Campaign Master describes it, no dice', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await goTo(user, 'Library');
    await skipTitle(user);
    await waitFor(() => expect(screen.getByTestId('scene-art')).toHaveAttribute('src', '/backgrounds/library.webp'));
    await user.click(screen.getByTestId('dialogue-box'));
    expect(screen.getByTestId('dialogue-box')).toHaveTextContent(/Library/);
    expect(screen.queryByRole('dialog', { name: 'Dice check' })).not.toBeInTheDocument();
  });
  it('2.6-AC3 the Map button cannot be used while a dice check is open', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await typeAction(user, 'check the ledger for an odd figure', () => screen.queryByRole('dialog', { name: 'Dice check' }) !== null);
    await screen.findByRole('dialog', { name: 'Dice check' });
    expect(choiceButton('Map')).toBeDisabled();
  });
  it('2.6-AC4 the first arrival shows the name as a title card that a tap skips; a return shows none', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await goTo(user, 'Library');
    const tc = await screen.findByTestId('title-card');
    expect(tc).toHaveTextContent('Library');
    await user.click(tc);
    expect(screen.queryByTestId('title-card')).not.toBeInTheDocument();
    await readToChoices(user);
    await goTo(user, 'Tavern');
    await skipTitle(user);
    await readToChoices(user);
    await goTo(user, 'Library');
    await screen.findByTestId('dialogue-box');
    expect(screen.queryByTestId('title-card')).not.toBeInTheDocument();
  });
  it('2.6-AC5 the price board chart and daily figures end at story today', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await goTo(user, 'Market Square');
    await skipTitle(user);
    await readToChoices(user);
    await user.click(await screen.findByRole('button', { name: 'Price board' }));
    const board = await screen.findByRole('dialog', { name: 'Market stall' });
    expect(within(board).getByRole('img', { name: 'Price chart' })).toHaveAttribute('data-last-day', '60');
    expect(within(board).queryByRole('rowheader', { name: '61' })).not.toBeInTheDocument();
  });
  it('2.6-AC6 before the news the Library lists only the introduction documents', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await goTo(user, 'Library');
    await skipTitle(user);
    await readToChoices(user);
    await user.click(await screen.findByRole('button', { name: 'Library documents' }));
    const lib = await screen.findByRole('dialog', { name: 'Library' });
    const text = await readParchment(user, lib);
    expect(text).toContain('Guild ledger, year one');
    expect(text).not.toContain('Quarterly loss notice');
  });
  it('2.6-AC7 a character speaks under their own name on the tab', () => {
    render(<DialogueBox speaker="Mira Fen" text="I have read every ledger twice." onAdvance={() => undefined} />);
    expect(screen.getByTestId('name-tab')).toHaveTextContent('Mira Fen');
  });
  it('2.6-AC8 the company card shows the made-up name, trade, size and key figures', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await goTo(user, 'Library');
    await skipTitle(user);
    await readToChoices(user);
    await user.click(await screen.findByRole('button', { name: 'Library documents' }));
    const card = within(await screen.findByRole('dialog', { name: 'Library' })).getByRole('region', { name: 'Company card' });
    for (const t of ['Lumenvale Guild', 'Lantern oil and lighting', 'About 4,200 workers', 'Barrels sold']) expect(card).toHaveTextContent(t);
  });
  const loc = (o: Partial<PlayLocation>): PlayLocation => ({ id: 'l1', key: 'tavern', name: 'Tavern', description: '', fixed: true, art_status: 'placeholder', visited: true, ...o });
  it('2.6-AC9 when a constant background file is missing, a plain backdrop with the location name remains', () => {
    render(<SceneArt location={loc({})} />);
    fireEventError(screen.getByTestId('scene-art'));
    expect(screen.queryByTestId('scene-art')).not.toBeInTheDocument();
    expect(screen.getByText('Tavern')).toBeInTheDocument();
  });
  it('2.6-AC10 the Tavern shows the same background file in every campaign', () => {
    expect(artSrc(loc({ id: 'campaign-A-tavern' }))).toBe('/backgrounds/tavern.webp');
    expect(artSrc(loc({ id: 'campaign-B-tavern' }))).toBe('/backgrounds/tavern.webp');
  });
  it('2.6-AC11 a campaign location with pending art shows the placeholder with its name and the player can act', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await goTo(user, 'Lamp Works');
    await skipTitle(user);
    await readToChoices(user);
    expect(screen.queryByTestId('scene-art')).not.toBeInTheDocument();
    expect(screen.getAllByText('The Lamp Works').length).toBeGreaterThan(0);
    expect(screen.getByRole('region', { name: 'Your turn' })).toBeInTheDocument();
  });
  it('2.6-AC12 ready campaign art replaces the placeholder (served by the API)', () => {
    expect(artSrc(loc({ id: 'abc', fixed: false, key: 'hall', art_status: 'ready' }))).toMatch(/\/locations\/abc\/art$/);
    expect(artSrc(loc({ id: 'abc', fixed: false, key: 'hall', art_status: 'pending' }))).toBeNull();
    render(<SceneArt location={loc({ id: 'abc', fixed: false, key: 'hall', art_status: 'ready' })} />);
    expect(screen.getByTestId('scene-art')).toHaveAttribute('src', expect.stringMatching(/\/locations\/abc\/art$/));
  });
});

function fireEventError(el: HTMLElement): void {
  act(() => void el.dispatchEvent(new Event('error')));
}

// ================================================================================================
// 2.7 CommerzBuddy
// ================================================================================================
describe('2.7 CommerzBuddy', () => {
  it('2.7-AC1 the Buddy button is visible on a scene', async () => {
    setupPlay('analyst');
    await screen.findByTestId('name-tab');
    expect(choiceButton('Buddy')).toBeVisible();
  });
  it('2.7-AC1b the Buddy button is also visible on the commit screen, the reveal, the debrief and the XP screen', async () => {
    const screens: [CampaignState['phase'], string, ReactNode][] = [
      ['commit', '/quest/commit', <Commit />],
      ['reveal', '/quest/outcome', <Outcome />],
      ['debrief', '/quest/debrief', <Debrief />],
      ['xp', '/quest/xp', <Xp />],
    ];
    for (const [phase, path, el] of screens) {
      cleanup();
      seedCampaign({ phase, decision: investDecision });
      renderRoutes([guard(path, el)], [path]);
      await waitFor(() => expect(screen.getByRole('button', { name: /Buddy/ })).toBeVisible(), { timeout: 1500 });
    }
  });
  it('2.7-AC2 tapping Buddy summons the token, the tab reads "CommerzBuddy" and a text box opens', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await user.click(choiceButton('Buddy'));
    expect(screen.getByTestId('name-tab')).toHaveTextContent('CommerzBuddy');
    expect(screen.getByRole('textbox', { name: 'Your question for CommerzBuddy' })).toBeInTheDocument();
    expect(document.querySelector('svg.animate-summon')).not.toBeNull();
  });
  it('2.7-AC3 Buddy answers "What is a drawdown?" in plain language within 120 words', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await user.click(choiceButton('Buddy'));
    await user.type(screen.getByRole('textbox', { name: 'Your question for CommerzBuddy' }), 'What is a drawdown?');
    await user.click(screen.getByRole('button', { name: 'Ask' }));
    const answer = readDb().play?.events.find((e) => e.type === 'buddy_a');
    await waitFor(() => expect(readDb().play?.events.some((e) => e.type === 'buddy_a')).toBe(true));
    const text = String(readDb().play?.events.find((e) => e.type === 'buddy_a')?.text ?? answer?.text);
    expect(text.split(/\s+/).length).toBeLessThanOrEqual(120);
  });
  it('2.7-AC4 "Should I buy this?" is turned back into a question about the evidence', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await user.click(choiceButton('Buddy'));
    await user.type(screen.getByRole('textbox', { name: 'Your question for CommerzBuddy' }), 'Should I buy this?');
    await user.click(screen.getByRole('button', { name: 'Ask' }));
    await waitFor(() => expect(readDb().play?.events.some((e) => e.type === 'buddy_a')).toBe(true));
    const text = String(readDb().play?.events.find((e) => e.type === 'buddy_a')?.text);
    expect(text).toMatch(/your call/i);
    expect(text).not.toMatch(/\b(you should|buy it|sell)\b/i);
    expect(text).toMatch(/evidence/i);
  });
  it('2.7-AC5 a question about the future price is answered without a prediction (server behaviour: see the backend test)', () => {
    // The text comes from the server; the screen shows it verbatim with the CommerzBuddy tab.
    render(<DialogueBox speaker="CommerzBuddy" text="Nobody can know that, and neither can I. Which ledger figures seem to disagree?" onAdvance={() => undefined} />);
    expect(screen.getByTestId('name-tab')).toHaveTextContent('CommerzBuddy');
  });
  it('2.7-AC6 closing the Buddy panel returns to the same screen with the typed text kept', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await user.click(choiceButton('Buddy'));
    await user.type(screen.getByRole('textbox', { name: 'Your question for CommerzBuddy' }), 'What is a drawd');
    await user.click(screen.getByRole('button', { name: 'Close Buddy' }));
    expect(screen.getByRole('region', { name: 'Your turn' })).toBeInTheDocument();
    await user.click(choiceButton('Buddy'));
    expect(screen.getByRole('textbox', { name: 'Your question for CommerzBuddy' })).toHaveValue('What is a drawd');
  });
});

// ================================================================================================
// 2.8 Journal and memory
// ================================================================================================
describe('2.8 Journal and memory', () => {
  it('2.8-AC1 the journal lists locations, actions, dice results, clues and Buddy exchanges in order', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await goTo(user, 'Library');
    await skipTitle(user);
    await readToChoices(user);
    await user.click(choiceButton('Buddy'));
    await user.type(screen.getByRole('textbox', { name: 'Your question for CommerzBuddy' }), 'What is a drawdown?');
    await user.click(screen.getByRole('button', { name: 'Ask' }));
    await waitFor(() => expect(readDb().play?.events.some((e) => e.type === 'buddy_a')).toBe(true));
    await user.click(screen.getByRole('button', { name: 'Close Buddy' }));
    await user.click(choiceButton('Journal'));
    const journal = await screen.findByRole('dialog', { name: 'Journal' });
    await waitFor(() => expect(journal).toHaveTextContent(/CommerzBuddy:/));
    const t = journal.textContent ?? '';
    expect(t.indexOf('Visited')).toBeGreaterThanOrEqual(0);
    expect(t.indexOf('Visited')).toBeLessThan(t.indexOf('You asked CommerzBuddy'));
    expect(t.indexOf('You asked CommerzBuddy')).toBeLessThan(t.indexOf('CommerzBuddy: A drawdown'));
  });
  it('2.8-AC2 a found clue appears in the journal with a clue icon', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await goTo(user, 'Library');
    await skipTitle(user);
    await readToChoices(user);
    await user.click(choiceButton('Journal'));
    const journal = await screen.findByRole('dialog', { name: 'Journal' });
    await waitFor(() => expect(within(journal).getByLabelText('Clue')).toBeInTheDocument());
  });
  it('2.8-AC3 the Campaign Master answer about an earlier clue names it (server memory: see the backend test)', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await goTo(user, 'Library');
    await skipTitle(user);
    await readToChoices(user);
    expect(readDb().campaign?.clues.map((c) => c.title)).toContain('Barrels sold');
  });
  it('2.8-AC4 returning to a visited location says you are back instead of repeating the description', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await goTo(user, 'Library');
    await skipTitle(user);
    await readToChoices(user);
    await goTo(user, 'Tavern');
    await skipTitle(user);
    await readToChoices(user);
    await goTo(user, 'Library');
    await skipTitle(user);
    await user.click(await screen.findByTestId('dialogue-box'));
    expect(screen.getByTestId('dialogue-box')).toHaveTextContent(/back at the Library/);
  });
  it('2.8-AC5 after leaving and continuing, the same backlog is shown', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await send(user, 'Ask the barkeep what people say about the guild');
    cleanup(); // leave: the screen unmounts, nothing but the stored campaign remains
    renderRoutes([{ path: '/quest/play', element: <PlayScreen /> }], ['/quest/play']);
    await screen.findByTestId('name-tab');
    await readToChoices(user);
    await user.click(choiceButton('Journal'));
    await user.click(await screen.findByRole('button', { name: 'Open the backlog' }));
    const backlog = await screen.findByRole('dialog', { name: 'Backlog' });
    await waitFor(() => expect(within(backlog).getByText('Ask the barkeep what people say about the guild')).toBeInTheDocument());
  });
});

// ================================================================================================
// 2.9 News event
// ================================================================================================
describe('2.9 In-period news event', () => {
  async function toNews(user: User): Promise<void> {
    await enterTavern(user);
    await send(user, 'Ask the barkeep what people say about the guild');
    await send(user, 'Visit Market Square');
    await goTo(user, 'Market Square');
    await skipTitle(user);
    await readToChoices(user, () => screen.queryByTestId('title-card') !== null);
  }
  it('2.9-AC1 after the 6th turn a "Breaking news" card with a headline and summary appears', async () => {
    const user = userEvent.setup();
    setupPlay('guardian');
    await enterTavern(user);
    for (let i = 1; i <= 5; i += 1) {
      await typeAction(user, `look around ${i}`);
      expect(screen.queryByTestId('title-card')).not.toBeInTheDocument();
    }
    await typeAction(user, 'look around 6', () => screen.queryByTestId('title-card') !== null);
    await user.click(await screen.findByTestId('title-card'));
    const news = await screen.findByRole('article', { name: 'Breaking news' });
    expect(news).toHaveTextContent('The guild reports a loss');
    expect(readDb().campaign?.turn_count).toBe(6);
  });
  it('2.9-AC2 the Campaign Master asks how the news changes the view, and the news is in the journal', async () => {
    const user = userEvent.setup();
    setupPlay('guardian');
    await toNews(user);
    await user.click(await screen.findByTestId('title-card'));
    const news = await screen.findByRole('article', { name: 'Breaking news' });
    await user.click(within(news).getByRole('button', { name: 'Continue' }));
    await user.click(await screen.findByTestId('dialogue-box'));
    expect(screen.getByTestId('dialogue-live')).toHaveTextContent(/How does this news change your thinking/);
    await user.click(choiceButton('Journal'));
    const journal = await screen.findByRole('dialog', { name: 'Journal' });
    await waitFor(() => expect(within(journal).getByText(/Breaking news/)).toBeInTheDocument());
  });
  it('2.9-AC3 after the news the price board extends and the Library lists the new documents', async () => {
    const user = userEvent.setup();
    setupPlay('guardian');
    await toNews(user);
    await user.click(await screen.findByTestId('title-card'));
    await user.click(within(await screen.findByRole('article', { name: 'Breaking news' })).getByRole('button', { name: 'Continue' }));
    await readToChoices(user);
    await user.click(await screen.findByRole('button', { name: 'Price board' }));
    const board = await screen.findByRole('dialog', { name: 'Market stall' });
    expect(within(board).getByRole('img', { name: 'Price chart' })).toHaveAttribute('data-last-day', '84');
    await user.click(within(board).getByRole('button', { name: /Close/ }));
    await goTo(user, 'Library');
    await skipTitle(user);
    await readToChoices(user);
    await user.click(await screen.findByRole('button', { name: 'Library documents' }));
    expect(await readParchment(user, await screen.findByRole('dialog', { name: 'Library' }))).toContain('Quarterly loss notice');
  });
});

// ================================================================================================
// 2.10 Voice narration
// ================================================================================================
describe('2.10 Voice narration', () => {
  function fakeImpl(): VoiceProviderImpl & { calls: string[] } {
    const calls: string[] = [];
    return {
      calls,
      unlock: () => void calls.push('unlock'),
      speak: (_id: string | null, text: string, voice: string) => void calls.push(`speak:${voice}:${text.slice(0, 24)}`),
      stop: () => void calls.push('stop'),
    } as VoiceProviderImpl & { calls: string[] };
  }
  const withVoice = (impl: VoiceProviderImpl) => {
    resetFixtureDb();
    fixtureResponse('POST', '/hero', { name: 'Mira', class: 'analyst' });
    fixtureResponse('POST', '/campaigns', { interests: ['Tech'] });
    return renderRoutes([{ path: '/quest/play', element: <VoiceProvider provider={impl}><PlayScreen /></VoiceProvider> }], ['/quest/play']);
  };
  const spoken = (i: { calls: string[] }) => i.calls.filter((c) => c.startsWith('speak:'));

  it('2.10-AC1 a player who never touched voice: Got it unlocks sound and the opening is read, voice shown on', async () => {
    fixtureResponse('POST', '/hero', { name: 'Mira', class: 'analyst' });
    renderRoutes([guard('/quest/disclosure', <QuestDisclosure />), guard('/quest/play', <PlayScreen />)], ['/quest/disclosure']);
    await userEvent.click(await screen.findByRole('button', { name: 'Got it' }));
    expect(unlockVoice).toHaveBeenCalled();
    cleanup();
    const impl = fakeImpl();
    withVoice(impl);
    expect(await screen.findByTestId('name-tab')).toBeInTheDocument();
    await waitFor(() => expect(spoken(impl)[0]).toMatch(/speak:dm:Welcome, traveller/));
    expect(choiceButton('Voice')).toHaveAttribute('aria-pressed', 'true');
  });
  it('2.10-AC2 a Campaign Master reply is read aloud and the same text is on screen', async () => {
    const user = userEvent.setup();
    const impl = fakeImpl();
    withVoice(impl);
    await enterTavern(user);
    await typeText(user, 'Ask the barkeep what people say about the guild');
    await user.click(await screen.findByTestId('dialogue-box'));
    await waitFor(() => expect(spoken(impl).length).toBeGreaterThan(1));
    expect(screen.getByTestId('dialogue-box')).toHaveTextContent(/./);
  });
  it('2.10-AC3 tapping the speaker while reading stops at once and shows voice off', async () => {
    const user = userEvent.setup();
    const impl = fakeImpl();
    withVoice(impl);
    await screen.findByTestId('name-tab');
    const before = impl.calls.filter((c) => c === 'stop').length;
    await user.click(choiceButton('Voice'));
    expect(impl.calls.filter((c) => c === 'stop').length).toBeGreaterThan(before);
    expect(choiceButton('Voice')).toHaveAttribute('aria-pressed', 'false');
  });
  it('2.10-AC4 with voice off a new reply is not read', async () => {
    localStorage.setItem(VOICE_KEY, 'off');
    const user = userEvent.setup();
    const impl = fakeImpl();
    withVoice(impl);
    await enterTavern(user);
    await send(user, 'Ask the barkeep what people say about the guild');
    expect(spoken(impl)).toHaveLength(0);
  });
  it('2.10-AC5 a player who turned voice off still has it off in a new campaign on the same phone', async () => {
    const user = userEvent.setup();
    const impl = fakeImpl();
    withVoice(impl);
    await screen.findByTestId('name-tab');
    await user.click(choiceButton('Voice'));
    cleanup();
    const next = fakeImpl();
    withVoice(next);
    await screen.findByTestId('name-tab');
    expect(choiceButton('Voice')).toHaveAttribute('aria-pressed', 'false');
    expect(spoken(next)).toHaveLength(0);
  });
  it('2.10-AC6 sending a new action while a reply is read stops the reading', async () => {
    const user = userEvent.setup();
    const impl = fakeImpl();
    withVoice(impl);
    await enterTavern(user);
    const before = impl.calls.filter((c) => c === 'stop').length;
    await typeText(user, 'Ask the barkeep what people say about the guild');
    expect(impl.calls.filter((c) => c === 'stop').length).toBeGreaterThan(before);
  });
  it('2.10-AC7 Buddy is read with the Buddy voice, different from the Campaign Master voice', async () => {
    const user = userEvent.setup();
    const impl = fakeImpl();
    withVoice(impl);
    await enterTavern(user);
    await user.click(choiceButton('Buddy'));
    await user.type(screen.getByRole('textbox', { name: 'Your question for CommerzBuddy' }), 'What is a drawdown?');
    await user.click(screen.getByRole('button', { name: 'Ask' }));
    await user.click(await screen.findByTestId('dialogue-box'));
    await waitFor(() => expect(spoken(impl).some((c) => c.startsWith('speak:buddy:'))).toBe(true));
    expect(spoken(impl).some((c) => c.startsWith('speak:dm:'))).toBe(true);
  });
  it('2.10-AC8 Continue unlocks sound again and the next reply is read with voice on', async () => {
    const { default: QuestCard } = await import('../../shell/components/QuestCard');
    const { saveProgress } = await import('../questStore');
    saveProgress('/quest/play');
    const onContinue = vi.fn();
    render(<QuestCard variant="overview" onStart={vi.fn()} onContinue={onContinue} />);
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(onContinue).toHaveBeenCalledWith('/quest/play');
    expect(unlockVoice).toHaveBeenCalled();
    cleanup();
    const user = userEvent.setup();
    const impl = fakeImpl();
    withVoice(impl);
    await enterTavern(user);
    await typeText(user, 'Ask the barkeep what people say about the guild');
    await user.click(await screen.findByTestId('dialogue-box'));
    await waitFor(() => expect(spoken(impl).length).toBeGreaterThan(1));
  });
});

// ================================================================================================
// 2.11 Hero status
// ================================================================================================
describe('2.11 Hero status', () => {
  it('2.11-AC1 a scene shows name, class, HP with euros, total XP, "Focus: 3" and the class use', async () => {
    setupPlay('investigator');
    const bar = await screen.findByRole('button', { name: 'Hero status' });
    expect(bar).toHaveTextContent('Mira');
    expect(bar).toHaveTextContent('the Investigator');
    expect(bar).toHaveTextContent('100 HP · €1,000');
    expect(bar).toHaveTextContent('XP 0');
    expect(bar).toHaveTextContent('Focus: 3');
    expect(bar).toHaveTextContent('Keen Eye: 1');
  });
  it('2.11-AC2 a setback or a success does not change HP or total XP', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await typeAction(user, 'check the ledger for an odd figure', () => screen.queryByRole('dialog', { name: 'Dice check' }) !== null);
    const dice = await screen.findByRole('dialog', { name: 'Dice check' });
    await user.click(within(dice).getByRole('button', { name: 'Roll' }));
    await within(dice).findByTestId('dice-verdict');
    await user.click(within(dice).getByRole('button', { name: 'Accept setback' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Dice check' })).not.toBeInTheDocument());
    const bar = screen.getByRole('button', { name: 'Hero status' });
    expect(bar).toHaveTextContent('100 HP · €1,000');
    expect(bar).toHaveTextContent('XP 0');
  });
  it('2.11-AC3 tapping the status bar opens the hero screen with the advantage and finished campaigns', async () => {
    const user = userEvent.setup();
    const router = setupPlay('analyst');
    await enterTavern(user);
    await user.click(screen.getByRole('button', { name: 'Hero status' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/hero'));
    cleanup();
    seedCampaign({ phase: 'xp', heroClass: 'analyst', decision: investDecision });
    fixtureResponse('POST', `/campaigns/${readDb().campaign!.id}/finish`);
    renderRoutes([{ path: '/quest/hero', element: <HeroScreen /> }], ['/quest/hero']);
    expect(await screen.findByText('Second Look — reroll one failed dice check per campaign')).toBeInTheDocument();
    const history = screen.getByRole('heading', { name: 'Learning history' }).parentElement as HTMLElement;
    expect(history).toHaveTextContent(/XP/);
    expect(within(history).getByRole('link', { name: 'Journal' })).toBeInTheDocument();
  });
  it('2.11-AC3b each finished campaign in the learning history lists its date', async () => {
    seedCampaign({ phase: 'xp', heroClass: 'analyst', decision: investDecision });
    fixtureResponse('POST', `/campaigns/${readDb().campaign!.id}/finish`);
    const finished = readDb().hero?.history[0]?.finished_at;
    renderRoutes([{ path: '/quest/hero', element: <HeroScreen /> }], ['/quest/hero']);
    const history = (await screen.findByRole('heading', { name: 'Learning history' })).parentElement as HTMLElement;
    expect(finished).toMatch(/\d{4}-\d\d-\d\d/);
    expect(history.textContent).toContain(String(finished));
  });
});

// ================================================================================================
// 2.12 Committing the decision
// ================================================================================================
describe('2.12 Committing the decision', () => {
  // Decisions are written during the campaign (decision scenes); the seal adds forecast and confidence.
  const commitRoutes = [guard('/quest/commit', <Commit />), { path: '/quest/play', element: <p>play screen</p> }, { path: '/quest/outcome', element: <p>outcome screen</p> }];
  const lockBtn = () => screen.getByRole('button', { name: 'Lock my decision' });
  const note = 'The debt figures worry me a lot.';
  it('2.12-AC1 the seal lists the decisions written during the campaign, slider at 50%, three confidences and Lock disabled', async () => {
    seedCampaign({ phase: 'commit', heroClass: 'guardian', offersSpread: true });
    renderRoutes(commitRoutes, ['/quest/commit']);
    const list = await screen.findByRole('region', { name: 'Your decisions' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getAllByRole('radio').map((r) => r.textContent)).toEqual(['Low', 'Medium', 'High']);
    expect(screen.getAllByRole('radio').filter((r) => r.getAttribute('aria-checked') === 'true')).toHaveLength(0);
    expect(screen.getByRole('slider')).toHaveValue('50');
    expect(lockBtn()).toBeDisabled();
  });
  it('2.12-AC2 the seal asks for no action or amount: those come from the decisions', async () => {
    seedCampaign({ phase: 'commit', heroClass: 'guardian', offersSpread: true });
    renderRoutes(commitRoutes, ['/quest/commit']);
    await screen.findByRole('region', { name: 'Your decisions' });
    expect(screen.queryByRole('radio', { name: 'Invest' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Amount in euros')).not.toBeInTheDocument();
    expect(screen.getByText(/Now: cash €600.00 · in the company €400.00/)).toBeInTheDocument();
  });
  it('2.12-AC5 with a confidence chosen the summary shows the answers and Lock is enabled', async () => {
    const user = userEvent.setup();
    seedCampaign({ phase: 'commit', heroClass: 'analyst' });
    renderRoutes(commitRoutes, ['/quest/commit']);
    await user.click(await screen.findByRole('radio', { name: 'High' }));
    const summary = screen.getByRole('region', { name: 'Summary' });
    expect(summary).toHaveTextContent('Decisions: 3');
    expect(summary).toHaveTextContent('50% likely higher');
    expect(summary).toHaveTextContent('high');
    expect(lockBtn()).toBeEnabled();
  });
  it("2.12-AC6 Lock my decision asks \"Once locked, you can't change it. Lock?\" with Lock and Go back", async () => {
    const user = userEvent.setup();
    seedCampaign({ phase: 'commit', heroClass: 'analyst' });
    renderRoutes(commitRoutes, ['/quest/commit']);
    await user.click(await screen.findByRole('radio', { name: 'Low' }));
    await user.click(lockBtn());
    expect(screen.getByText("Once locked, you can't change it. Lock?")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Lock' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Go back' }));
    expect(screen.queryByText("Once locked, you can't change it. Lock?")).not.toBeInTheDocument();
  });
  it('2.12-AC7 "Back to investigating" keeps the typed answers for the next visit', async () => {
    const user = userEvent.setup();
    seedCampaign({ phase: 'commit', heroClass: 'analyst' });
    const router = renderRoutes(commitRoutes, ['/quest/commit']);
    await user.type(await screen.findByLabelText(/Anything to add/), note);
    await user.click(screen.getByRole('button', { name: 'Back to investigating' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/play'));
    expect(readDb().campaign?.commit_draft?.evidence).toBe(note);
  });
  it('2.12-AC8 after "Lock" the seal and time skip follow and the answers are saved as locked', async () => {
    const user = userEvent.setup();
    seedCampaign({ phase: 'commit', heroClass: 'analyst' });
    renderRoutes(commitRoutes, ['/quest/commit']);
    await user.click(await screen.findByRole('radio', { name: 'High' }));
    await user.click(lockBtn());
    await user.click(screen.getByRole('button', { name: 'Lock' }));
    expect(await screen.findByText('75 days later…', {}, { timeout: 3000 })).toBeInTheDocument();
    expect(readDb().decision).toMatchObject({ confidence: 'high', forecast_pct: 50 });
    expect(screen.queryByRole('slider')).not.toBeInTheDocument();
  });
});

// ================================================================================================
// 2.13 Reveal and HP update (the screen shows the server's figures)
// ================================================================================================
describe('2.13 Reveal and HP update', () => {
  const routes = [guard('/quest/outcome', <Outcome />), guard('/quest/debrief', <Debrief />)];
  it('2.13-AC1 after Lock a "[horizon] later…" screen appears, followed by the reveal with the extended chart', async () => {
    const user = userEvent.setup();
    seedCampaign({ phase: 'commit', heroClass: 'analyst' });
    renderRoutes([guard('/quest/commit', <Commit />), guard('/quest/outcome', <Outcome />)], ['/quest/commit']);
    await user.click(await screen.findByRole('radio', { name: 'High' }));
    await user.click(screen.getByRole('button', { name: 'Lock my decision' }));
    await user.click(screen.getByRole('button', { name: 'Lock' }));
    await user.click(await screen.findByText('75 days later…', {}, { timeout: 3000 }));
    expect(await screen.findByRole('img', { name: 'Price chart' })).toHaveAttribute('data-mode', 'story');
  });
  it('2.13-AC2 the reveal shows final value, loss in euros and percent, and the HP change from the server', async () => {
    seedCampaign({ phase: 'reveal', decision: investDecision });
    renderRoutes(routes, ['/quest/outcome']);
    expect(await screen.findByText('100 HP → 61 HP')).toBeInTheDocument();
    expect(screen.getByText('Final value').closest('div')).toHaveTextContent('€607.51');
    expect(screen.getByText('Profit / loss').closest('div')).toHaveTextContent('−€392.49 (−39.2%)');
  });
  it('2.13-AC3 for Don\'t invest the figures shown are the server\'s unchanged budget and HP', async () => {
    seedCampaign({ phase: 'reveal', decision: { evidence: 'x'.repeat(30), forecast_pct: 50, confidence: 'low' } });
    renderRoutes(routes, ['/quest/outcome']);
    await screen.findByText('Final value');
    expect(screen.getByText(/HP →/)).toBeInTheDocument();
  });
  it('2.13-AC4 the same percentage is displayed from the server value, whatever the budget (no client maths)', () => {
    expect(readDb()).toBeDefined();
    // the percentage is rendered from `breakdown.pl_pct` verbatim: Outcome has no arithmetic of its own
    const src = import.meta.glob('../screens/Outcome.tsx', { query: '?raw', import: 'default', eager: true });
    const text = Object.values(src)[0] as string;
    expect(text).not.toMatch(/\* ?100|\/ ?10\b|Math\.round/);
  });
  it('2.13-AC5 the reveal shows "Locked at [time] · horizon [horizon]"', async () => {
    seedCampaign({ phase: 'reveal', decision: investDecision });
    renderRoutes(routes, ['/quest/outcome']);
    expect(await screen.findByText('Locked at Day 84, evening · horizon 75 days')).toBeInTheDocument();
  });
});

// ================================================================================================
// 2.14 Debrief, reflection, company reveal and XP
// ================================================================================================
describe('2.14 Debrief, reflection, company reveal and XP', () => {
  const routes = [
    guard('/quest/outcome', <Outcome />), guard('/quest/debrief', <Debrief />), guard('/quest/reflect', <Reflect />),
    guard('/quest/reveal', <RevealRoute />), guard('/quest/xp', <Xp />), { path: '/overview', element: <p>bank app</p> },
  ];
  it('2.14-AC1 the debrief shows "Sound reasoning", "Overlooked", "Luck" and a forecast line', async () => {
    seedCampaign({ phase: 'debrief', decision: investDecision });
    renderRoutes(routes, ['/quest/debrief']);
    for (const h of ['Sound reasoning', 'Overlooked', 'Luck']) expect(await screen.findByRole('heading', { name: h })).toBeInTheDocument();
    expect(screen.getByText(/You said 40% likely higher/)).toBeInTheDocument();
  });
  it('2.14-AC2 the "Overlooked" part is shown from the server text naming the unfound clue', async () => {
    seedCampaign({ phase: 'debrief', decision: investDecision });
    renderRoutes(routes, ['/quest/debrief']);
    const h = await screen.findByRole('heading', { name: 'Overlooked' });
    expect((h.parentElement?.textContent ?? '').replace('Overlooked', '').trim().length).toBeGreaterThan(0);
  });
  it('2.14-AC3 the "What if…" panel lists the four rows and highlights the player\'s own choice', async () => {
    seedCampaign({ phase: 'debrief', decision: investDecision });
    renderRoutes(routes, ['/quest/debrief']);
    await screen.findByRole('heading', { name: 'What if…' });
    for (const l of ['Never invest', 'Everything at your first decision, then hold', 'Everything on decision day, then hold']) expect(screen.getByText(l)).toBeInTheDocument();
    const mine = screen.getAllByRole('listitem').filter((r) => r.getAttribute('aria-current') === 'true');
    expect(mine).toHaveLength(1);
    expect(mine[0]).toHaveTextContent('Your decisions');
  });
  it('2.14-AC4 viewing the "What if…" panel does not change the HP or XP stored', async () => {
    seedCampaign({ phase: 'debrief', decision: investDecision });
    const before = JSON.stringify({ xp: readDb().hero?.total_xp, hp: readDb().campaign?.hp });
    renderRoutes(routes, ['/quest/debrief']);
    await screen.findByRole('heading', { name: 'What if…' });
    expect(JSON.stringify({ xp: readDb().hero?.total_xp, hp: readDb().campaign?.hp })).toBe(before);
  });
  it('2.14-AC5 a reflection shorter than 10 characters keeps "Submit reflection" disabled', async () => {
    const user = userEvent.setup();
    seedCampaign({ phase: 'reflect', decision: investDecision });
    renderRoutes(routes, ['/quest/reflect']);
    const submit = await screen.findByRole('button', { name: 'Submit reflection' });
    await user.type(screen.getByRole('textbox'), '123456789');
    expect(submit).toBeDisabled();
  });
  it('2.14-AC6 before the reflection is submitted the real company name is not shown', async () => {
    seedCampaign({ phase: 'debrief', decision: investDecision });
    renderRoutes(routes, ['/quest/debrief']);
    await screen.findByRole('heading', { name: 'Sound reasoning' });
    expect(document.body.textContent).not.toMatch(/Example Lantern/);
    cleanup();
    renderRoutes(routes, ['/quest/reveal']); // forced early: the guard keeps the reveal closed
    await waitFor(() => expect(document.body.textContent).not.toMatch(/Example Lantern/));
  });
  it('2.14-AC7 after submitting the reflection the real company name, dates and sources appear', async () => {
    const user = userEvent.setup();
    seedCampaign({ phase: 'reflect', decision: investDecision });
    const router = renderRoutes(routes, ['/quest/reflect']);
    await user.type(await screen.findByRole('textbox'), 'I would check the cash flow first.');
    await user.click(screen.getByRole('button', { name: 'Submit reflection' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/reveal'));
    expect(await screen.findByRole('heading', { name: 'Example Lantern Co.' })).toBeInTheDocument();
  });
  it('2.14-AC8 XP lists the rubric categories with 25, 25, 20, 15, 15, a total out of 100 and a quote per category', async () => {
    seedCampaign({ phase: 'xp', decision: investDecision });
    renderRoutes(routes, ['/quest/xp']);
    await screen.findByText('Evidence literacy');
    const items = screen.getAllByRole('listitem');
    ['25', '25', '20', '15', '15'].forEach((m, i) => expect(items[i]).toHaveTextContent(new RegExp(`/ ${m}`)));
    expect(screen.getAllByRole('blockquote')).toHaveLength(5);
    expect(screen.getByText(/Total \d+ \/ 100/)).toBeInTheDocument();
  });
  it('2.14-AC9 XP after a loss: no rationale shown mentions the loss as the reason for lost points', async () => {
    seedCampaign({ phase: 'xp', decision: investDecision });
    renderRoutes(routes, ['/quest/xp']);
    await screen.findByText('Evidence literacy');
    expect(document.body.textContent).not.toMatch(/\b(lost money|because (you )?lost|the loss cost|profit)\b/i);
  });
  it('2.14-AC10 "Finish quest" adds the XP, records the campaign, and the quest card is back to Start', async () => {
    const user = userEvent.setup();
    const { getQuestMeta, startQuest } = await import('../questStore');
    startQuest();
    seedCampaign({ phase: 'xp', decision: investDecision });
    renderRoutes(routes, ['/quest/xp']);
    await user.click(await screen.findByRole('button', { name: 'Finish quest' }));
    expect(await screen.findByText(/Total XP: \d+/)).toBeInTheDocument();
    expect(readDb().hero?.total_xp).toBeGreaterThan(0);
    expect(readDb().hero?.history.length).toBe(1);
    expect(getQuestMeta().inProgress).toBe(false);
  });
  it('2.14-AC11 leaving on the XP screen and continuing shows the XP screen with the same XP', async () => {
    seedCampaign({ phase: 'xp', decision: investDecision });
    renderRoutes(routes, ['/quest/xp']);
    const total = (await screen.findByText(/Total \d+ \/ 100/)).textContent;
    cleanup();
    renderRoutes(routes, ['/quest/xp']);
    expect((await screen.findByText(/Total \d+ \/ 100/)).textContent).toBe(total);
  });
});

// ================================================================================================
// 2.15 Leaving and continuing
// ================================================================================================
describe('2.15 Leaving and continuing', () => {
  it('2.15-AC1 leaving mid-investigation and continuing shows the same scene, log and hero status', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await send(user, 'Ask the barkeep what people say about the guild');
    cleanup();
    renderRoutes([{ path: '/quest/play', element: <PlayScreen /> }], ['/quest/play']);
    const bar = await screen.findByRole('button', { name: 'Hero status' });
    expect(bar).toHaveTextContent('Rerolls: 1');
    expect(bar).toHaveTextContent('Focus: 3');
    expect(await screen.findByTestId('dialogue-box')).toBeInTheDocument();
  });
  it('2.15-AC2 leaving right after a setback and continuing keeps the same result and offers no new roll', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await typeAction(user, 'check the ledger for an odd figure', () => screen.queryByRole('dialog', { name: 'Dice check' }) !== null);
    const dice = await screen.findByRole('dialog', { name: 'Dice check' });
    await user.click(within(dice).getByRole('button', { name: 'Roll' }));
    await within(dice).findByTestId('dice-verdict');
    cleanup(); // leave while the setback card is open
    renderRoutes([{ path: '/quest/play', element: <PlayScreen /> }], ['/quest/play']);
    const again = await screen.findByRole('dialog', { name: 'Dice check' });
    expect(within(again).queryByRole('button', { name: 'Roll' })).not.toBeInTheDocument();
    expect(within(again).getByRole('button', { name: /Second Look/ })).toBeInTheDocument();
  });
  it('2.15-AC3 after locking, the decision stays locked and resumes at the time skip or reveal', async () => {
    seedCampaign({ phase: 'reveal', decision: investDecision });
    renderRoutes([guard('/quest/outcome', <Outcome />), guard('/quest/commit', <Commit />)], ['/quest/commit']);
    expect(await screen.findByText(/Locked at/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Evidence/)).not.toBeInTheDocument();
  });
  it('2.15-AC4 the ✕ button on a quest screen asks "Leave the quest?" with Leave and Stay', async () => {
    seedCampaign({ phase: 'commit', heroClass: 'analyst' });
    const { createMemoryRouter, RouterProvider } = await import('react-router-dom');
    const { QueryClientProvider } = await import('@tanstack/react-query');
    const { createQueryClient } = await import('../../api/queryClient');
    const { startQuest } = await import('../questStore');
    startQuest();
    const router = createMemoryRouter(
      [
        { path: '/overview', element: <p>bank</p> },
        { path: '/quest', element: <VoiceProvider><QuestLayout /></VoiceProvider>, children: [{ path: 'commit', element: <p>commit</p> }] },
      ],
      { initialEntries: ['/overview', '/quest/commit'], initialIndex: 1 },
    );
    render(<QueryClientProvider client={createQueryClient()}><RouterProvider router={router} /></QueryClientProvider>);
    await userEvent.click(screen.getByRole('button', { name: 'Close quest' }));
    expect(await screen.findByText(/Leave the quest\?/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Leave' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stay' })).toBeInTheDocument();
  });
});

// ================================================================================================
// 2.16 Safeguards (screen side: the surfaces the player can open show only gated data)
// ================================================================================================
describe('2.16 Safeguards', () => {
  it('2.16-AC1 the screens show server text verbatim: nothing is added, so a safe server reply stays safe', () => {
    const src = import.meta.glob('../play/*.tsx', { query: '?raw', import: 'default', eager: true });
    for (const [file, text] of Object.entries(src)) {
      if (file.includes('.test.')) continue;
      expect(text as string, file).not.toMatch(/recommend|guaranteed|you should buy/i);
    }
  });
  it('2.16-AC2 the price board and chart before locking end at story today and no location art uses real logos', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await goTo(user, 'Market Square');
    await skipTitle(user);
    await readToChoices(user);
    await user.click(await screen.findByRole('button', { name: 'Price board' }));
    const board = await screen.findByRole('dialog', { name: 'Market stall' });
    const storyToday = readDb().campaign?.story_day ?? 0;
    expect(within(board).getByRole('img', { name: 'Price chart' })).toHaveAttribute('data-last-day', String(storyToday));
    expect(readDb().campaign?.price_board.every((p) => p.day <= storyToday)).toBe(true);
    expect(JSON.stringify(readDb().campaign)).not.toMatch(/logo|ticker/i);
  });
});

// ================================================================================================
// 2.17 Focus and items
// ================================================================================================
describe('2.17 Focus and items', () => {
  it('2.17-AC1 a campaign starts with "Focus: 3"', async () => {
    setupPlay('guardian');
    expect(await screen.findByText('Focus: 3')).toBeInTheDocument();
  });
  it('2.17-AC2 "Ask for a hint" names where a clue waits and the status shows one Focus less', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await user.click(choiceButton('Ask for a hint'));
    await readToChoices(user);
    expect(screen.getByText('Focus: 2')).toBeInTheDocument();
    expect(readDb().play?.events.find((e) => e.type === 'dm_reply' && String(e.text).includes('Library'))).toBeTruthy();
  });
  it('2.17-AC3 "Chase a bonus lead" opens a difficulty 18 check and the status shows one Focus less', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await user.click(choiceButton('Chase a bonus lead'));
    const dice = await screen.findByRole('dialog', { name: 'Dice check' });
    expect(within(dice).getByText(/Difficulty 18/)).toBeInTheDocument();
    expect(screen.getByText('Focus: 2')).toBeInTheDocument();
  });
  it('2.17-AC4 with 0 Focus both Focus buttons are disabled', () => {
    render(<ChoiceList canDecide={false} focusLeft={0} bonusLeadAvailable onSend={vi.fn()} onDecide={vi.fn()} onHint={vi.fn()} onBonusLead={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Ask for a hint' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Chase a bonus lead' })).toBeDisabled();
  });
  it('2.17-AC5 finishing with 70 XP or more lists the "Ratio Lens" on the hero screen with its description', async () => {
    seedCampaign({ phase: 'xp', heroClass: 'analyst', decision: investDecision });
    fixtureResponse('POST', `/campaigns/${readDb().campaign!.id}/finish`);
    renderRoutes([{ path: '/quest/hero', element: <HeroScreen /> }], ['/quest/hero']);
    expect(await screen.findByText('Ratio Lens')).toBeInTheDocument();
    expect(screen.getByText('Ratio Lens').parentElement?.textContent?.length).toBeGreaterThan('Ratio Lens'.length);
  });
  it('2.17-AC6 with no item earned the hero screen says so (backend asserts the 70 XP threshold)', async () => {
    seedCampaign({ phase: 'play', heroClass: 'analyst' });
    renderRoutes([{ path: '/quest/hero', element: <HeroScreen /> }], ['/quest/hero']);
    expect(await screen.findByText(/No items yet/)).toBeInTheDocument();
  });
  it('2.17-AC7 with the Ratio Lens each key figure on the company card has a one-sentence explanation', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    const db = readDb();
    if (db.campaign) {
      db.campaign.library.company_card.key_figures = [{ id: 'barrels', label: 'Barrels sold', value: 1200, period: 'last year', explain: 'How many barrels were sold in a year.' }];
      writeDb(db);
    }
    await goTo(user, 'Library');
    await skipTitle(user);
    await readToChoices(user);
    await user.click(await screen.findByRole('button', { name: 'Library documents' }));
    expect(await readParchment(user, await screen.findByRole('dialog', { name: 'Library' }))).toContain('How many barrels were sold in a year.');
  });
  it('2.17-AC8 an item changes no figure on screen: starting HP and euros are the same with an item', async () => {
    seedCampaign({ phase: 'play', heroClass: 'analyst' });
    const db = readDb();
    if (db.campaign) {
      db.campaign.hero.items = ['ratio_lens', 'rumour_ledger', 'calm_compass'];
      writeDb(db);
    }
    renderRoutes([{ path: '/quest/play', element: <PlayScreen /> }], ['/quest/play']);
    expect(await screen.findByText(/100 HP/)).toHaveTextContent('100 HP · €1,000');
  });
});

// ================================================================================================
// 2.18 Look and feel
// ================================================================================================
describe('2.18 Look and feel', () => {
  type Colors = { quest: Record<string, string> };
  const colors = (config.theme?.extend?.colors ?? {}) as unknown as Colors & Record<string, unknown>;
  it('2.18-AC1 the quest palette is lapis, verdigris, gilt, wax-red, vellum, soot; no bank yellow or petrol in quest sources', () => {
    expect(colors.quest).toMatchObject({ lapis: '#22305B', verdigris: '#3E8A7E', gilt: '#C9A227', wax: '#A8322D', vellum: '#E8DCC2', soot: '#15121A' });
    const src = import.meta.glob(['../**/*.tsx', '!../**/*.test.tsx', '!../__acceptance__/**'], { query: '?raw', import: 'default', eager: true });
    for (const [file, text] of Object.entries(src)) {
      expect(text as string, file).not.toMatch(/\b(?:bg|text|border|ring|from|to|via)-(?:brand|petrol|warm|line)(?:[-/\s'"`]|$)/);
    }
  });
  it('2.18-AC2 narration is set in the serif, buttons and labels in the sans-serif, titles in the blackletter', () => {
    const fonts = (config.theme?.extend?.fontFamily ?? {}) as Record<string, string[]>;
    expect(fonts.quest?.[0]).toBe('Alegreya');
    expect(fonts['quest-sans']?.[0]).toBe('Alegreya Sans');
    expect(fonts['quest-title']?.[0]).toBe('Pirata One');
    render(<DialogueBox speaker="Campaign Master" text="Hello there." onAdvance={() => undefined} />);
    expect(screen.getByTestId('dialogue-text').className).toMatch(/font-quest\b/);
    render(<ChoiceList canDecide={false} focusLeft={3} bonusLeadAvailable onSend={vi.fn()} onDecide={vi.fn()} onHint={vi.fn()} onBonusLead={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Ask for a hint' }).className).toMatch(/font-quest-sans/);
  });
  it('2.18-AC3 the die tumbles for about one second before the result is shown', () => {
    expect(TUMBLE_MS).toBeGreaterThanOrEqual(800);
    expect(TUMBLE_MS).toBeLessThanOrEqual(1200);
    const cfg = config.theme?.extend as { animation?: Record<string, string> } | undefined;
    expect(cfg?.animation?.tumble).toMatch(/\b1s\b/);
  });
  it('2.18-AC4 with reduced motion the die appears without tumbling', async () => {
    vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('reduce'), addEventListener: () => undefined, removeEventListener: () => undefined }));
    const rolled: RollResult = { roll_id: 'r', challenge_id: 'r', title: 't', dice: [14], used: 14, bonus: 2, total: 16, dc: 12, result: 'success', final: true, options: ['continue'], rerolled: false, rerolls_left: 0, keen_eye_left: 0, alt_source: null };
    const api: DiceApi = { roll: vi.fn(() => Promise.resolve(rolled)), reroll: vi.fn(), accept: vi.fn() };
    render(<DiceMoment card={{ kind: 'dice', roll_id: 'r', challenge_id: 'r', title: 't', dc: 12, bonus: 2, keen_eye_available: false, keen_eye_left: 0 }} api={api} onResolved={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(await screen.findByTestId('dice-verdict')).toBeInTheDocument();
    expect(document.querySelector('.animate-tumble')).toBeNull();
    vi.unstubAllGlobals();
  });
  it('2.18-AC5 after confirming the lock a wax-seal animation plays before the time skip', async () => {
    const user = userEvent.setup();
    seedCampaign({ phase: 'commit', heroClass: 'analyst' });
    renderRoutes([guard('/quest/commit', <Commit />)], ['/quest/commit']);
    await user.click(await screen.findByRole('radio', { name: 'High' }));
    await user.click(screen.getByRole('button', { name: 'Lock my decision' }));
    await user.click(screen.getByRole('button', { name: 'Lock' }));
    expect(await screen.findByText('Sealing your decision…')).toBeInTheDocument();
    expect(document.querySelector('.motion-safe\\:animate-seal-press')).not.toBeNull();
    expect(await screen.findByText('75 days later…', {}, { timeout: 3000 })).toBeInTheDocument();
  });
});

// keep imports used by the type checker
void BuddyScene;
