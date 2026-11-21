import { describe, expect, it } from 'vitest';
import { formatGold } from './gold';

describe('formatGold', () => {
  it('groups thousands, rounds to whole numbers and appends gp', () => {
    expect(formatGold(1000)).toBe('1,000 gp');
    expect(formatGold(607.51)).toBe('608 gp');
    expect(formatGold(0)).toBe('0 gp');
  });
});
