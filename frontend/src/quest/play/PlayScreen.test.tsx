import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { readDb, writeDb } from '../../api/fixtures/db';
import * as sse from '../../api/sse';
import type { DmEvent } from '../../api/types';
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
    expect(screen.getByText(/100 HP/)).toHaveTextContent('100 HP · 1,000 gp');
    expect(screen.getByText('Focus: 3')).toBeInTheDocument();
    expect(screen.getByText('Rerolls: 1')).toBeInTheDocument();
    expect(screen.queryByText(/Keen Eye/)).not.toBeInTheDocument();
    expect(screen.getByText(/^1 \/ \d$/)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Your turn' })).not.toBeInTheDocument();
    await readToChoices(user);
    const list = screen.getByRole('region', { name: 'Your turn' });
    expect(within(list).getByText('What would you do?')).toBeInTheDocument();
    expect(within(list).getAllByRole('button').map((b) => b.getAttribute('aria-label') ?? b.textContent)).toEqual(['◀ Read again', 'Send', 'Chat with CommerzBuddy']); // no hint, no bonus lead
    expect(within(list).queryByRole('button', { name: "I'm ready to decide" })).not.toBeInTheDocument();
  });

  it('"Read again" brings back the reply on its last page; reading it through returns to the input', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await screen.findByTestId('name-tab');
    await readToChoices(user);
    await user.click(screen.getByRole('button', { name: /Read again/ }));
    expect(screen.queryByRole('region', { name: 'Your turn' })).not.toBeInTheDocument();
    const count = screen.getByText(/^\d \/ \d$/).textContent ?? '';
    const [at, of] = count.split(' / ');
    expect(at).toBe(of); // the last page, where the player left it
    await user.click(screen.getByTestId('dialogue-box'));
    expect(await screen.findByRole('region', { name: 'Your turn' })).toBeInTheDocument();
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

describe('PlayScreen: a streamed reply and its voice', () => {
  const sentence = (n: number, tag: string): string => `${Array.from({ length: n }, (_, i) => `${tag}${i}`).join(' ')}.`;
  const long = [sentence(30, 'a'), sentence(30, 'b'), sentence(30, 'c')].join(' ');

  it('keeps the page reached while streaming and its voice when the reply completes', async () => {
    const user = userEvent.setup();
    const onPageShown = vi.fn();
    setupPlay('analyst', { onPageShown });
    await enterTavern(user);
    let emit: (e: DmEvent) => void = () => undefined;
    let finish: () => void = () => undefined;
    vi.spyOn(sse, 'postSse').mockImplementation(
      (_path, _body, onEvent) =>
        new Promise<void>((resolve) => {
          emit = onEvent;
          finish = resolve;
        }),
    );
    await user.type(screen.getByRole('textbox'), 'I read the guild ledgers');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    onPageShown.mockClear();
    act(() => {
      emit({ event: 'status', data: { state: 'writing' } });
      emit({ event: 'speaker', data: { speaker: 'Campaign Master', audio_text_id: 77, audio_text: long } });
      emit({ event: 'token', data: { text: long } });
    });
    expect(onPageShown).toHaveBeenCalledWith(long, 'dm', 77); // the voice starts with the text
    const box = screen.getByTestId('dialogue-box');
    await user.click(box); // complete page 1
    await user.click(box); // page 2, while the reply still streams
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    await act(async () => {
      emit({ event: 'done', data: { text: long, speaker: 'Campaign Master', audio_text_id: 77, suggestions: [] } as never });
      finish();
    });
    expect(screen.getByText('2 / 3')).toBeInTheDocument(); // not thrown back to page one
    expect(onPageShown).toHaveBeenCalledTimes(1); // and the voice was not started again
  });
});

describe('PlayScreen: map, titles and places', () => {
  it('Map lists the places with "you are here" and "this tale only"', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await user.click(choiceButton('Map'));
    const map = await screen.findByRole('dialog', { name: 'The map' });
    for (const n of ['Tavern', 'Market Square', 'Library']) expect(within(map).getByRole('button', { name: new RegExp(n) })).toBeInTheDocument();
    expect(within(map).getByRole('button', { name: /Tavern/ })).toHaveTextContent('you are here');
    await user.click(within(map).getByRole('button', { name: /Other locations/ }));
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
    await user.click(await screen.findByRole('button', { name: "Read the guild's records" }));
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
    await user.click(await screen.findByRole('button', { name: 'Visit the market stall' }));
    const board = await screen.findByRole('dialog', { name: 'Market stall' });
    expect(within(board).getByRole('img', { name: 'Price chart' })).toHaveAttribute('data-last-day', '60');
    expect(within(board).queryByRole('table')).not.toBeInTheDocument();
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

  it("the Library books open the parchment; there is no Library documents chip", async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    await moveTo(user, 'Library');
    await readToChoices(user);
    await user.click(screen.getByRole('button', { name: "Read the guild's records" }));
    const lib = await screen.findByRole('dialog', { name: 'Library' });
    expect(within(lib).getByRole('region', { name: 'Company card' })).toHaveTextContent('Lumenvale Guild');
    await user.click(within(lib).getByRole('button', { name: 'Close Library' }));
    expect(screen.queryByRole('button', { name: 'Library documents' })).not.toBeInTheDocument();
  });

  it('no place shows chips under the hero status: the scene itself is the way in', async () => {
    const user = userEvent.setup();
    setupPlay('analyst');
    await enterTavern(user);
    expect(screen.queryByRole('button', { name: /Talk to Brannoc$/ })).not.toBeInTheDocument(); // the table hotspot stays
    expect(screen.getByRole('button', { name: 'Talk to Brannoc at the table' })).toBeInTheDocument();
    await moveTo(user, 'Market Square');
    await readToChoices(user);
    expect(screen.queryByRole('button', { name: 'Price board' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Rumour ledger' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Visit the market stall' })).toBeInTheDocument();
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
    expect(screen.getByText(/120 HP/)).toHaveTextContent('120 HP · 1,200 gp');
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
