import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Die3D from './Die3D';

describe('Die3D', () => {
  it('names the rolled number and draws all twenty faces', () => {
    const { container } = render(<Die3D value={17} />);
    expect(screen.getByRole('img', { name: 'Twenty-sided die showing 17' })).toBeInTheDocument();
    const numbers = Array.from(container.querySelectorAll('b')).map((b) => Number(b.textContent));
    expect(numbers.sort((a, b) => a - b)).toEqual(Array.from({ length: 20 }, (_, i) => i + 1));
  });

  it('says it is rolling while there is no result yet', () => {
    render(<Die3D value={null} />);
    expect(screen.getByRole('img', { name: 'Twenty-sided die, rolling' })).toBeInTheDocument();
  });
});
