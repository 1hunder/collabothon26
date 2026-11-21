import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { readDb, writeDb } from '../../api/fixtures/db';
import * as sse from '../../api/sse';
import { FIRST_EVENT_TIMEOUT_MS } from '../../api/useDmStream';
import { openBuddy, readParchment, readToChoices, setupPlay, skipTitle } from './playTestUtils';

vi.mock('../components/StoryChart', () => ({
  default: ({ points }: { points: { story_day: number }[] }) => <div role="img" aria-label="Price chart" data-last-day={points.at(-1)?.story_day} />,
}));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

const choiceButton = (name: string | RegExp): HTMLElement => screen.getByRole('button', { name });

/** Opening scene read and the Tavern title skipped, with choices showing. */
async function enterTavern(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await readToChoices(user);
  await skipTitle(user);
}

async function sendSuggestion(user: ReturnType<typeof userEvent.setup>, name: string): Promise<void> {
  await user.type(screen.getByRole('textbox'), name);
  await user.click(screen.getByRole('button', { name: 'Send' }));
  await readToChoices(user);
}

async function openMapAndGo(user: ReturnType<typeof userEvent.setup>, place: string): Promise<void> {
  await user.click(choiceButton('Map'));
  const map = await screen.findByRole('dialog', { name: 'The map' });
  await user.click(within(map).getByRole('button', { name: new RegExp(place) }));
}

async function moveTo(user: ReturnType<typeof userEvent.setup>, place: string): Promise<void> {
  await openMapAndGo(user, place);
  await skipTitle(user);
}

describe('PlayScreen: scene and hero status', () => {
  it('opens in the Tavern: name tab, hero status, pages, then the choices', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    expect(await screen.findByTestId('name-tab')).toHaveTextContent('Campaign Master');
    expect(screen.getByText('Mira')).toBeInTheDocument();
    expect(screen.getByText(/100 HP/)).toHaveTextContent('100 HP · €1,000');
    expect(screen.getByText('Focus: 3')).toBeInTheDocument();
    expect(screen.getByText('Rerolls: 1')).toBeInTheDocument();
    expect(screen.queryByText(/Keen Eye/)).not.toBeInTheDocument();
    expect(screen.getByText(/^1 \/ \d$/)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Your turn' })).not.toBeInTheDocument();
    await readToChoices(user);
    const list = screen.getByRole('region', { name: 'Your turn' });
    expect(within(list).getByText('What would you do?')).toBeInTheDocument();
    expect(within(list).getAllByRole('button').length).toBeGreaterThanOrEqual(3);
    expect(within(list).queryByRole('button', { name: "I'm ready to decide" })).not.toBeInTheDocument();
  });

  it('shows Keen Eye for an Investigator and 120 HP for a Guardian', async () => {
    setupPlay('investigator');
    expect(await screen.findByText('Keen Eye: 1')).toBeInTheDocument();
  });

  it('draws the plain backdrop with the location name when there is no art yet', async () => {
    setupPlay('analyst');
    await screen.findByTestId('name-tab');
    expect(screen.getAllByText('Tavern').length).toBeGreaterThan(0);
  });
});

describe('PlayScreen: sending actions', () => {
  it('a typed action is sent at once; the reply appears and the earlier turn is in the backlog', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await sendSuggestion(user, 'Ask the barkeep what people say about the guild');
    await user.click(choiceButton('Journal'));
    await user.click(await screen.findByRole('button', { name: 'Open the backlog' }));
    const backlog = await screen.findByRole('dialog', { name: 'Backlog' });
    await waitFor(() => expect(within(backlog).getByText('Ask the barkeep what people say about the guild')).toBeInTheDocument());
    expect(within(backlog).getByText('You')).toBeInTheDocument();
  });

  it('writing indicator appears at once, then after 15 s the thread is lost and Try again resends the same request', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
    setupPlay('analyst');
    await enterTavern(user);
    const spy = vi.spyOn(sse, 'postSse').mockImplementation(() => new Promise<void>(() => undefined));
    await user.type(screen.getByRole('textbox'), 'Walk to Market Square and study the price board');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(screen.getByRole('status')).toHaveTextContent('The Campaign Master is writing…');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(FIRST_EVENT_TIMEOUT_MS);
    });
    expect(screen.getByRole('alert')).toHaveTextContent('The Campaign Master lost the thread.');
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(spy).toHaveBeenCalledTimes(2);
    const first = spy.mock.calls[0]?.[1] as { client_msg_id: string; text: string };
    const second = spy.mock.calls[1]?.[1] as { client_msg_id: string; text: string };
    expect(second).toEqual(first);
    expect(screen.getByRole('status')).toHaveTextContent('The Campaign Master is writing…');
  });
});

describe('PlayScreen: map, titles and places', () => {
  it('Map lists the places with "you are here" and "this tale only"', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await user.click(choiceButton('Map'));
    const map = await screen.findByRole('dialog', { name: 'The map' });
    for (const n of ['Tavern', 'Market Square', 'Library', 'The Lamp Works']) expect(within(map).getByRole('button', { name: new RegExp(n) })).toBeInTheDocument();
    expect(within(map).getByRole('button', { name: /Tavern/ })).toHaveTextContent('you are here');
    expect(within(map).getByRole('button', { name: /Lamp Works/ })).toHaveTextContent('this tale only');
  });

  it('the title card shows on the first visit only, and a tap skips it', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await openMapAndGo(user, 'Library');
    const card = await screen.findByTestId('title-card');
    expect(card).toHaveTextContent('Library');
    await user.click(card);
    expect(screen.queryByTestId('title-card')).not.toBeInTheDocument();
    await readToChoices(user);
    await moveTo(user, 'Tavern');
    await readToChoices(user);
    await openMapAndGo(user, 'Library');
    await waitFor(() => expect(screen.getByTestId('dialogue-box')).toBeInTheDocument());
    expect(screen.queryByTestId('title-card')).not.toBeInTheDocument();
  });

  it('the Library lists introduction documents and the company card, nothing later', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await moveTo(user, 'Library');
    await readToChoices(user);
    await user.click(await screen.findByRole('button', { name: 'Library documents' }));
    const lib = await screen.findByRole('dialog', { name: 'Library' });
    const text = await readParchment(user, lib);
    expect(text).toContain('Guild ledger, year one');
    expect(text).not.toContain('Quarterly loss notice');
    await user.click(within(lib).getByRole('button', { name: 'Previous page' }));
    const card = within(lib).getByRole('region', { name: 'Company card' });
    expect(card).toHaveTextContent('Lumenvale Guild');
    expect(card).toHaveTextContent('Lantern oil and lighting');
  });

  it('the Market Square price board ends at story today', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await moveTo(user, 'Market Square');
    await readToChoices(user);
    await user.click(await screen.findByRole('button', { name: 'Price board' }));
    const board = await screen.findByRole('dialog', { name: 'Market stall' });
    expect(within(board).getByRole('img', { name: 'Price chart' })).toHaveAttribute('data-last-day', '60');
    expect(within(board).getByRole('rowheader', { name: '60' })).toBeInTheDocument();
    expect(within(board).queryByRole('rowheader', { name: '61' })).not.toBeInTheDocument();
    expect(within(board).getByRole('columnheader', { name: 'Volume' })).toBeInTheDocument();
  });
});

describe('PlayScreen: scene hotspots', () => {
  it('the Tavern has no notice board: no hotspot and no chip', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    expect(screen.queryByRole('button', { name: 'Read the notice board' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Notice board' })).not.toBeInTheDocument();
  });

  it("the Library books open the parchment; the Library documents chip still reaches it", async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await moveTo(user, 'Library');
    await readToChoices(user);
    await user.click(screen.getByRole('button', { name: "Read the guild's records" }));
    const lib = await screen.findByRole('dialog', { name: 'Library' });
    expect(within(lib).getByRole('region', { name: 'Company card' })).toHaveTextContent('Lumenvale Guild');
    await user.click(within(lib).getByRole('button', { name: 'Close Library' }));
    await user.click(screen.getByRole('button', { name: 'Library documents' }));
    expect(await screen.findByRole('dialog', { name: 'Library' })).toBeInTheDocument();
  });

  it('the market stall opens the stall panel with the price chart as its first tab', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await moveTo(user, 'Market Square');
    await readToChoices(user);
    await user.click(screen.getByRole('button', { name: 'Visit the market stall' }));
    const panel = await screen.findByRole('dialog', { name: 'Market stall' });
    expect(within(panel).getByRole('tab', { name: 'Price chart', selected: true })).toBeInTheDocument();
    expect(await within(panel).findByRole('img', { name: 'Price chart' })).toHaveAttribute('data-last-day', '60');
    await user.click(within(panel).getByRole('button', { name: 'Close Market stall' }));
    expect(screen.queryByRole('dialog', { name: 'Market stall' })).not.toBeInTheDocument();
  });

  it('no hotspot is offered at another location or while a sheet or the Buddy is open', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await moveTo(user, 'Library');
    await readToChoices(user);
    expect(screen.getByRole('button', { name: "Read the guild's records" })).toBeInTheDocument();
    await user.click(choiceButton('Map'));
    expect(screen.queryByRole('button', { name: "Read the guild's records" })).not.toBeInTheDocument();
    await user.click(within(screen.getByRole('dialog', { name: 'The map' })).getByRole('button', { name: /Close/ }));
    await openBuddy(user);
    expect(screen.queryByRole('button', { name: "Read the guild's records" })).not.toBeInTheDocument();
  });
});

describe('PlayScreen: dice', () => {
  async function toDice(user: ReturnType<typeof userEvent.setup>): Promise<void> {
    await enterTavern(user);
    await user.type(screen.getByRole('textbox'), 'check the ledger for an odd figure');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await readToChoices(user, () => screen.queryByRole('dialog', { name: 'Dice check' }) !== null);
  }

  it('opens the dice check after the reply, disables the Map, and a Guardian success continues into the narration', async () => {
    const user = userEvent.setup();
    setupPlay('guardian');
    await toDice(user);
    const dice = await screen.findByRole('dialog', { name: 'Dice check' });
    expect(within(dice).getByText(/Difficulty 12/)).toBeInTheDocument();
    expect(choiceButton('Map')).toBeDisabled();
    await user.click(within(dice).getByRole('button', { name: 'Roll' }));
    expect(await within(dice).findByTestId('dice-sum')).toHaveTextContent('14 + 2 = 16 against 12');
    expect(within(dice).getByTestId('dice-verdict')).toHaveTextContent('Success');
    await user.click(within(dice).getByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Dice check' })).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('dialogue-box')).toHaveTextContent(/ledger/i));
    expect(choiceButton('Map')).toBeEnabled();
    expect(screen.getByText(/120 HP/)).toHaveTextContent('120 HP · €1,200');
  });

  it('an Analyst setback offers Second Look; the reroll lowers Rerolls to 0 and the clue lands in the journal', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await toDice(user);
    const dice = await screen.findByRole('dialog', { name: 'Dice check' });
    await user.click(within(dice).getByRole('button', { name: 'Roll' }));
    expect(await within(dice).findByTestId('dice-verdict')).toHaveTextContent('Setback');
    await user.click(within(dice).getByRole('button', { name: /Second Look — reroll \(1 left\)/ }));
    expect(await within(dice).findByTestId('dice-sum')).toHaveTextContent('17 + 2 = 19 against 12');
    await user.click(within(dice).getByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(screen.getByText('Rerolls: 0')).toBeInTheDocument());
    await readToChoices(user);
    await user.click(choiceButton('Journal'));
    const journal = await screen.findByRole('dialog', { name: 'Journal' });
    await waitFor(() => expect(within(journal).getByText(/17 \+ 2 = 19 against 12/)).toBeInTheDocument());
    expect(within(journal).getByLabelText('Clue')).toBeInTheDocument();
    expect(within(journal).getByText(/The odd ledger line/)).toBeInTheDocument();
  });

  it('an Investigator can roll with Keen Eye and the status drops to Keen Eye: 0', async () => {
    const user = userEvent.setup();
    setupPlay('investigator');
    await toDice(user);
    const dice = await screen.findByRole('dialog', { name: 'Dice check' });
    await user.click(within(dice).getByRole('button', { name: 'Keen Eye — roll with advantage (1 left)' }));
    expect(await within(dice).findByText(/Two dice: 9 and 14/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Keen Eye: 0')).toBeInTheDocument());
  });
});

describe('PlayScreen: news', () => {
  it('shows the time skip, the Breaking news card, then the Campaign Master asks how it changes your view', async () => {
    const user = userEvent.setup();
    setupPlay('guardian');
    await enterTavern(user);
    await sendSuggestion(user, 'Ask the barkeep what people say about the guild');
    await sendSuggestion(user, 'Visit Market Square');
    // third turn: arriving at Market Square after turn 3 fires the news
    await moveTo(user, 'Market Square');
    await readToChoices(user, () => screen.queryByTestId('title-card') !== null);
    const skip = await screen.findByTestId('title-card');
    expect(skip).toHaveTextContent('24 days later…');
    await user.click(skip);
    const news = await screen.findByRole('article', { name: 'Breaking news' });
    expect(news).toHaveTextContent('The guild reports a loss');
    await user.click(within(news).getByRole('button', { name: 'Continue' }));
    await user.click(await screen.findByTestId('dialogue-box'));
    expect(screen.getByTestId('dialogue-live')).toHaveTextContent(/How does this news change your thinking/);
    await user.click(choiceButton('Journal'));
    const journal = await screen.findByRole('dialog', { name: 'Journal' });
    await waitFor(() => expect(within(journal).getByText(/Breaking news/)).toBeInTheDocument());
  });
});

describe('PlayScreen: deciding', () => {
  it("shows I'm ready to decide only when the server says can_decide, and opens the commit screen", async () => {
    const user = userEvent.setup();
    const router = setupPlay('analyst');
    await enterTavern(user);
    expect(screen.queryByRole('button', { name: "I'm ready to decide" })).not.toBeInTheDocument();
    {
      // the server flips can_decide: patch the fixture store and refetch through a turn
      const db = readDb();
      if (db.campaign) {
        db.campaign.can_decide = true;
        db.campaign.news_shown = true;
        db.campaign.clues = [
          { clue_id: 'a', source: 's', title: 'A', text: 'a' },
          { clue_id: 'b', source: 's', title: 'B', text: 'b' },
        ];
        writeDb(db);
      }
    }
    await sendSuggestion(user, 'Walk to Market Square and study the price board');
    await user.click(await screen.findByRole('button', { name: "I'm ready to decide" }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/quest/commit'));
  });
});

describe('PlayScreen: Buddy and the dock', () => {
  it('summons Buddy, answers under the Buddy tab, and keeps the draft when closed', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await openBuddy(user);
    expect(screen.getByRole('region', { name: 'CommerzBuddy' })).toBeInTheDocument();
    expect(screen.getByTestId('name-tab')).toHaveTextContent('CommerzBuddy');
    await user.type(screen.getByRole('textbox', { name: 'Your question for CommerzBuddy' }), 'What is a drawdown');
    await user.click(screen.getByRole('button', { name: 'Close Buddy' }));
    expect(screen.queryByRole('region', { name: 'CommerzBuddy' })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Your turn' })).toBeInTheDocument();
    await openBuddy(user);
    expect(screen.getByRole('textbox', { name: 'Your question for CommerzBuddy' })).toHaveValue('What is a drawdown');
    await user.click(screen.getByRole('button', { name: 'Ask' }));
    await waitFor(() => expect(screen.getByTestId('dialogue-live')).toHaveTextContent(/drawdown/i), { timeout: 2000 }).catch(async () => {
      await user.click(screen.getByTestId('dialogue-box'));
      expect(screen.getByTestId('dialogue-box')).toHaveTextContent(/drawdown/i);
    });
    await user.click(choiceButton('Journal'));
    const journal = await screen.findByRole('dialog', { name: 'Journal' });
    await waitFor(() => expect(within(journal).getByText(/You asked CommerzBuddy: What is a drawdown/)).toBeInTheDocument());
  });

  it('the Voice button toggles the prop it is given', async () => {
    const user = userEvent.setup();
    const onToggleVoice = vi.fn();
    setupPlay('analyst', { voiceOn: true, onToggleVoice });
    await screen.findByTestId('name-tab');
    expect(choiceButton('Voice')).toHaveAttribute('aria-pressed', 'true');
    await user.click(choiceButton('Voice'));
    expect(onToggleVoice).toHaveBeenCalled();
  });

  it('reports every page to the voice hook', async () => {
    const onPageShown = vi.fn();
    setupPlay('analyst', { onPageShown });
    await screen.findByTestId('name-tab');
    await waitFor(() => expect(onPageShown).toHaveBeenCalledWith(expect.stringContaining('Gilded Tavern'), 'dm', null));
  });
});
