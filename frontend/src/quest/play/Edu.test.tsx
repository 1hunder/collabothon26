import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CampaignState, EduLesson, EduMoment } from '../../api/types';
import type { DmStream } from '../../api/useDmStream';
import BuddyMascot from './BuddyMascot';
import BuddyScene from './BuddyScene';
import { useEdu } from './useEdu';

const request = vi.hoisted(() => vi.fn());
vi.mock('../../api/client', async (orig) => ({ ...(await orig<typeof import('../../api/client')>()), request }));

const m = (n: number, title = `Moment ${n}`): EduMoment => ({ id: `m${n}`, concept_key: `k${n}`, title });
const lesson: EduLesson = {
  id: 'm1',
  title: "Profit isn't cash",
  what_happened: 'WH text',
  idea: 'IDEA text',
  example: 'EX text',
  takeaway: 'TAKE text',
  check: { question: 'Q?', options: ['A', 'B', 'C'], answer_index: 1 },
};
const idle: DmStream = { state: { phase: 'idle' }, send: vi.fn(), retry: vi.fn(), reset: vi.fn() };

function Harness({ initial, fresh }: { initial: EduMoment[]; fresh?: EduMoment[] }): React.JSX.Element {
  const edu = useEdu('c1');
  return (
    <>
      <BuddyMascot pending={edu.pending} poppedId={edu.poppedId} onOpenChat={() => undefined} />
      <button type="button" onClick={() => edu.announce(fresh)}>announce</button>
      <BuddyScene stream={idle} edu={edu} onClose={() => undefined} />
      <span data-testid="n">{initial.length}</span>
    </>
  );
}

function renderEdu(initial: EduMoment[], fresh?: EduMoment[]): void {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  qc.setQueryData(['campaign', 'c1'], { id: 'c1', edu: { pending: initial, pending_count: initial.length } } as CampaignState);
  render(<QueryClientProvider client={qc}><Harness initial={initial} fresh={fresh} /></QueryClientProvider>);
}

beforeEach(() => {
  request.mockReset();
  window.sessionStorage.clear();
});

describe('learning moments', () => {
  it('shows no bubbles and stays asleep with nothing pending', () => {
    renderEdu([]);
    expect(screen.queryByTestId('edu-bubble')).toBeNull();
    expect(screen.getByRole('button', { name: 'Chat with CommerzBuddy' })).toHaveAttribute('data-awake', 'false');
  });

  it('wakes with one bubble per moment, capped at three', () => {
    renderEdu([m(1), m(2), m(3), m(4)]);
    expect(screen.getAllByTestId('edu-bubble')).toHaveLength(3);
    const btn = screen.getByRole('button', { name: /3 learning moments waiting/ });
    expect(btn).toHaveAttribute('data-awake', 'true');
  });

  it('pops a new bubble when edu_new arrives', async () => {
    renderEdu([m(1)], [m(2)]);
    expect(screen.getAllByTestId('edu-bubble')).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: 'announce' }));
    const bubbles = screen.getAllByTestId('edu-bubble');
    expect(bubbles).toHaveLength(2);
    expect(bubbles[1]).toHaveAttribute('data-pop', 'true');
    expect(bubbles[0]).toHaveAttribute('data-pop', 'false');
  });

  it('offers a single moment when Buddy opens, and Later keeps it pending', async () => {
    renderEdu([m(1, "Profit isn't cash")]);
    expect(screen.getByText(/I spotted a learning moment: Profit isn't cash\. Want to take a look\?/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Later' }));
    expect(screen.getByRole('textbox', { name: 'Your question for CommerzBuddy' })).toBeInTheDocument();
    expect(screen.getAllByTestId('edu-bubble')).toHaveLength(1);
    expect(request).not.toHaveBeenCalled();
  });

  it('lists several moments and Not now dismisses one', async () => {
    request.mockResolvedValue(undefined);
    renderEdu([m(1), m(2), m(3)]);
    expect(screen.getByText('I spotted 3 learning moments. Which one first?')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Not now: Moment 2' }));
    expect(request).toHaveBeenCalledWith('POST', '/campaigns/c1/edu/m2/dismiss');
    await waitFor(() => expect(screen.getAllByTestId('edu-bubble')).toHaveLength(2));
  });

  it('Show me renders every lesson section and runs the check', async () => {
    let release: (l: EduLesson) => void = () => undefined;
    request.mockReturnValue(new Promise<EduLesson>((r) => { release = r; }));
    renderEdu([m(1)]);
    await userEvent.click(screen.getByRole('button', { name: 'Show me' }));
    expect(screen.getByText('CommerzBuddy is preparing your lesson…')).toBeInTheDocument();
    await act(async () => release(lesson));
    await screen.findByRole('heading', { name: "Profit isn't cash" });
    for (const t of ['What happened', 'The idea', 'A quick example', 'Remember']) expect(screen.getByRole('heading', { name: t })).toBeInTheDocument();
    for (const t of ['WH text', 'IDEA text', 'EX text', 'TAKE text', 'Q?']) expect(screen.getByText(t)).toBeInTheDocument();
    expect(request).toHaveBeenCalledWith('POST', '/campaigns/c1/edu/m1/lesson');
    expect(screen.queryByTestId('edu-bubble')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'A' }));
    expect(screen.getByText('Not quite. The answer is: B.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'B' })).toHaveAttribute('data-state', 'correct');
    expect(screen.getByRole('button', { name: 'A' })).toHaveAttribute('data-state', 'incorrect');
    await userEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.getByRole('textbox', { name: 'Your question for CommerzBuddy' })).toBeInTheDocument();
  });

  it('shows an error with Try again and keeps the moment pending', async () => {
    request.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce(lesson);
    renderEdu([m(1)]);
    await userEvent.click(screen.getByRole('button', { name: 'Show me' }));
    expect(await screen.findByText("Couldn't prepare this one.")).toBeInTheDocument();
    expect(screen.getAllByTestId('edu-bubble')).toHaveLength(1);
    await act(async () => userEvent.click(screen.getByRole('button', { name: 'Try again' })));
    await screen.findByRole('heading', { name: 'The idea' });
  });
});
