import { render, screen } from '@testing-library/react';
import type { RevealData } from '../../api/types';
import Reveal from './Reveal';

vi.mock('../components/StoryChart', () => ({
  default: (p: { mode: string; markers?: unknown[] }) => (
    <div data-testid="chart" data-mode={p.mode} data-markers={p.markers?.length ?? 0} />
  ),
}));

const data: RevealData = {
  real_name: 'Example Lantern Co.',
  ticker: 'EXLC',
  start_date: '2001-03-01',
  end_date: '2001-08-31',
  series: [{ date: '2001-03-01', price: 40 }],
  news_points: [{ story_day: 12, real_date: '2001-04-01', real_price: 43, headline: 'Press opens' }],
  what_changed: ['Company name'],
  n_guessers: 3,
};

describe('Reveal', () => {
  it('renders all elements', async () => {
    render(<Reveal data={data} />);
    expect(screen.getByRole('heading', { name: 'Example Lantern Co.' })).toBeInTheDocument();
    expect(screen.getByText(/2001-03-01 to 2001-08-31/)).toBeInTheDocument();
    expect(await screen.findByTestId('chart')).toHaveAttribute('data-mode', 'real');
    expect(screen.getByTestId('chart')).toHaveAttribute('data-markers', '1');
    expect(screen.getByText('2001-04-01')).toBeInTheDocument();
    expect(screen.getByText('43')).toBeInTheDocument();
    expect(screen.getByText('Company name')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Before you played, 3 AI testers tried to guess this company. None of them got it.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Education only/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /buy/i })).not.toBeInTheDocument();
  });

  it('omits the testers sentence when n_guessers is 0', () => {
    render(<Reveal data={{ ...data, n_guessers: 0 }} />);
    expect(screen.queryByText(/AI testers/)).not.toBeInTheDocument();
  });
});
