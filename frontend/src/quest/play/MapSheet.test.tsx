import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { PlayLocation } from '../../api/types';
import MapSheet from './MapSheet';

const loc = (over: Partial<PlayLocation>): PlayLocation => ({
  id: 'x', key: 'x', name: 'X', description: '', fixed: true, art_status: 'ready', visited: true, ...over,
});

describe('MapSheet', () => {
  it('marks an unvisited generated place as new and keeps the Tavern reachable', () => {
    render(
      <MapSheet
        locations={[
          loc({ id: 't', key: 'tavern', name: 'Tavern' }),
          loc({ id: 'd', key: 'docks', name: 'The Docks Warehouse', fixed: false, generated: true, visited: false, npc: { id: 'n', name: 'Orrin Vale', role: 'harbour clerk' } }),
        ]}
        currentId="d"
        disabled={false}
        onMove={() => undefined}
        onClose={() => undefined}
      />,
    );
    expect(screen.getByRole('button', { name: /Tavern/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: /Docks Warehouse/ })).toBeDisabled();
  });

  it('shows the new marker when the player is elsewhere', () => {
    render(
      <MapSheet
        locations={[
          loc({ id: 't', key: 'tavern', name: 'Tavern' }),
          loc({ id: 'd', key: 'docks', name: 'The Docks Warehouse', fixed: false, generated: true, visited: false }),
        ]}
        currentId="t"
        disabled={false}
        onMove={() => undefined}
        onClose={() => undefined}
      />,
    );
    expect(screen.getByRole('button', { name: /Docks Warehouse/ })).toHaveTextContent('new');
  });
});
