import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Overview from './Overview';
import { ToastProvider } from '../Toast';

function setup() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <Overview />
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe('Overview', () => {
  it('renders elements in order with exact values', () => {
    const { container } = setup();
    const text = container.textContent ?? '';
    const order = [
      'Hello, Lena',
      '€1,240.50',
      'Transfer',
      'StartKonto',
      'DE00 0000 0000 0000 0000 00',
      'StartDepot',
      'No investments yet',
      '€0.00',
      'Cards',
      'Postbox',
      'Finance Quest',
      'Learn to invest with real market history — risk-free',
    ];
    let last = -1;
    for (const s of order) {
      const i = text.indexOf(s, last + 1);
      expect(i, s).toBeGreaterThan(last);
      last = i;
    }
  });

  it.each(['Transfer', 'Cards', 'Postbox'])('%s shows the not-available toast', async (name) => {
    setup();
    await userEvent.click(screen.getByRole('button', { name }));
    expect(screen.getByText('Not available in this demo.')).toBeInTheDocument();
  });

  it('quest card shows New and Start', () => {
    setup();
    expect(screen.getByText('New')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();
  });

  it('has no daily quest panel, only Start', () => {
    setup();
    expect(screen.queryByText(/Today's quest/)).toBeNull();
    expect(screen.queryByRole('button', { name: /Generate another quest|Regenerate/ })).toBeNull();
  });
});
