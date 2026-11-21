import { describe, expect, it } from 'vitest';
import { formatGold } from './gold';

describe('formatGold', () => {
  it('groups thousands and appends gp', () => {
    expect(formatGold(1000)).toBe('1,000 gp');
    expect(formatGold(607.51)).toBe('607.51 gp');
    expect(formatGold(0)).toBe('0 gp');
  });
});
