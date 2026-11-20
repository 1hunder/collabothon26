import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Investments from './Investments';
import StartDepot from './StartDepot';
import { ToastProvider } from '../Toast';

function setup(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ToastProvider>
        <Routes>
          <Route path="/investments" element={<Investments />} />
          <Route path="/investments/startdepot" element={<StartDepot />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe('StartDepot', () => {
  it('renders all required texts and buttons', () => {
    setup('/investments/startdepot');
    expect(screen.getByText('€0.00')).toBeInTheDocument();
    expect(screen.getByText("You don't have any investments yet.")).toBeInTheDocument();
    for (const t of [
      'No custody fees up to €20,000 depot value',
      'Savings plans from €25 a month',
      'For pupils, students and trainees',
    ]) {
      expect(screen.getByText(t)).toBeInTheDocument();
    }
    expect(screen.getByRole('heading', { name: 'Practise before you invest' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start your first quest' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Set up savings plan' })).toBeInTheDocument();
  });

  it('Set up savings plan shows the toast', async () => {
    setup('/investments/startdepot');
    await userEvent.click(screen.getByRole('button', { name: 'Set up savings plan' }));
    expect(screen.getByText('Not available in this demo.')).toBeInTheDocument();
  });
});

describe('Investments', () => {
  it('entry shows StartDepot with €0.00 and navigates to StartDepot', async () => {
    setup('/investments');
    const entry = screen.getByRole('button', { name: /StartDepot/ });
    expect(entry).toHaveTextContent('€0.00');
    await userEvent.click(entry);
    expect(screen.getByText("You don't have any investments yet.")).toBeInTheDocument();
  });
});
