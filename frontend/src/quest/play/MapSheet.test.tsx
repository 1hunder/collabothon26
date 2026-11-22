import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { PlayLocation } from '../../api/types';
import MapSheet from './MapSheet';

const loc = (over: Partial<PlayLocation>): PlayLocation => ({
  id: 'x', key: 'x', name: 'X', description: '', fixed: true, art_status: 'ready', visited: true, ...over,
});

const village = [
  loc({ id: 't', key: 'tavern', name: 'Tavern' }),
  loc({ id: 'm', key: 'market_square', name: 'Market Square' }),
  loc({ id: 'l', key: 'library', name: 'Library' }),
];

const docks = (over: Partial<PlayLocation> = {}): PlayLocation =>
  loc({ id: 'd', key: 'docks', name: 'The Docks Warehouse', fixed: false, generated: true, visited: false, ...over });

describe('MapSheet', () => {
  it('puts the fixed buildings on the map and marks where the player is', async () => {
    const onMove = vi.fn();
    render(<MapSheet locations={village} currentId="t" disabled={false} onMove={onMove} onClose={() => undefined} />);
    expect(screen.getByRole('button', { name: /Tavern/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Tavern/ })).toHaveAttribute('aria-current', 'location');
    await userEvent.click(screen.getByRole('button', { name: 'Library' }));
    expect(onMove).toHaveBeenCalledWith(expect.objectContaining({ key: 'library' }));
  });

  it('locks every building while a dice check is open', () => {
    render(<MapSheet locations={village} currentId="t" disabled onMove={() => undefined} onClose={() => undefined} />);
    expect(screen.getByRole('button', { name: 'Library' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Market Square' })).toBeDisabled();
  });

  it('reveals tale-only places under "Other locations" with the new marker', async () => {
    render(<MapSheet locations={[...village, docks()]} currentId="t" disabled={false} onMove={() => undefined} onClose={() => undefined} />);
    expect(screen.queryByRole('button', { name: /Docks Warehouse/ })).not.toBeInTheDocument();
    const other = screen.getByRole('button', { name: /Other locations/ });
    expect(other).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(other);
    expect(other).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: /Docks Warehouse/ })).toHaveTextContent('new');
  });

  it('opens the list already when the player stands in a tale-only place, Tavern stays reachable', () => {
    render(
      <MapSheet
        locations={[...village, docks({ npc: { id: 'n', name: 'Orrin Vale', role: 'harbour clerk' } })]}
        currentId="d"
        disabled={false}
        onMove={() => undefined}
        onClose={() => undefined}
      />,
    );
    expect(screen.getByRole('button', { name: /Tavern/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: /Docks Warehouse/ })).toBeDisabled();
  });

  it('says so when the tale has no other places yet', async () => {
    render(<MapSheet locations={village} currentId="t" disabled={false} onMove={() => undefined} onClose={() => undefined} />);
    await userEvent.click(screen.getByRole('button', { name: /Other locations/ }));
    expect(screen.getByText(/No other roads/)).toBeInTheDocument();
  });
});
