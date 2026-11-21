import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import DialogueBox from './DialogueBox';

const sentence = (n: number, tag: string): string => `${Array.from({ length: n }, (_, i) => `${tag}${i}`).join(' ')}.`;
const long = [sentence(30, 'a'), sentence(30, 'b'), sentence(30, 'c')].join(' ');

describe('DialogueBox', () => {
  it('splits a long reply into pages of at most 50 words with a page count and a marker', async () => {
    render(<DialogueBox speaker="Campaign Master" text={long} onAdvance={() => undefined} />);
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('dialogue-box'));
    expect(screen.getByTestId('dialogue-text').textContent?.split(' ').length).toBeLessThanOrEqual(50);
    expect(screen.getByText('▼')).toBeInTheDocument();
  });

  it('a tap completes the page, a second tap turns to the next, the last tap advances', async () => {
    const onAdvance = vi.fn();
    render(<DialogueBox speaker="Campaign Master" text={long} onAdvance={onAdvance} />);
    const box = screen.getByTestId('dialogue-box');
    expect(screen.getByTestId('dialogue-text').textContent).not.toBe(sentence(30, 'a'));
    await userEvent.click(box);
    expect(screen.getByTestId('dialogue-text')).toHaveTextContent(sentence(30, 'a'));
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    await userEvent.click(box);
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    await userEvent.click(box); // complete page 2
    await userEvent.click(box); // page 3
    expect(screen.getByText('3 / 3')).toBeInTheDocument();
    expect(onAdvance).not.toHaveBeenCalled();
    await userEvent.click(box); // complete page 3
    await userEvent.click(box); // past the last page
    expect(onAdvance).toHaveBeenCalledTimes(1);
  });

  it('announces a page only once it is complete and reports each page to the voice hook', async () => {
    const onPageShown = vi.fn();
    render(<DialogueBox speaker="Campaign Master" text={long} onAdvance={() => undefined} onPageShown={onPageShown} />);
    const live = screen.getByTestId('dialogue-live');
    expect(live).toHaveAttribute('aria-live', 'polite');
    expect(live).toHaveTextContent('');
    await userEvent.click(screen.getByTestId('dialogue-box'));
    expect(live).toHaveTextContent(sentence(30, 'a'));
    expect(onPageShown).toHaveBeenCalledWith(expect.stringContaining('a0'), 'dm', null);
    await userEvent.click(screen.getByTestId('dialogue-box'));
    expect(onPageShown).toHaveBeenCalledTimes(2);
  });

  it('plays the server audio once for the whole multi-page reply and not again per page', async () => {
    const onPageShown = vi.fn();
    render(<DialogueBox speaker="Campaign Master" text={long} audioTextId={7} onAdvance={() => undefined} onPageShown={onPageShown} />);
    const box = screen.getByTestId('dialogue-box');
    await userEvent.click(box);
    await userEvent.click(box);
    await userEvent.click(box);
    expect(onPageShown).toHaveBeenCalledTimes(1);
    expect(onPageShown).toHaveBeenCalledWith(long, 'dm', 7);
  });

  it('uses the gilt tab for the Campaign Master and the verdigris tab for CommerzBuddy', () => {
    const { rerender } = render(<DialogueBox speaker="Campaign Master" text="Hello." onAdvance={() => undefined} />);
    expect(screen.getByTestId('name-tab')).toHaveClass('bg-quest-gilt');
    rerender(<DialogueBox speaker="CommerzBuddy" text="Hello." onAdvance={() => undefined} />);
    expect(screen.getByTestId('name-tab')).toHaveClass('bg-quest-verdigris-light');
  });

  it('shows a character name on the tab', () => {
    render(<DialogueBox speaker="Mira the scholar" text="Hello." onAdvance={() => undefined} />);
    expect(screen.getByTestId('name-tab')).toHaveTextContent('Mira the scholar');
  });

  it('shows the writing indicator while there is no text yet', () => {
    render(<DialogueBox speaker="Campaign Master" text="" writing final={false} onAdvance={() => undefined} />);
    expect(screen.getByRole('status')).toHaveTextContent('The Campaign Master is writing…');
  });

  it('does not advance past the last page while the reply is still streaming', async () => {
    const onAdvance = vi.fn();
    render(<DialogueBox speaker="Campaign Master" text="Streaming so far." final={false} onAdvance={onAdvance} />);
    await userEvent.click(screen.getByTestId('dialogue-box'));
    await userEvent.click(screen.getByTestId('dialogue-box'));
    expect(onAdvance).not.toHaveBeenCalled();
  });
});
