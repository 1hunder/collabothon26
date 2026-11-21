import { formatPct, formatSigned } from './commit';
import { formatGold } from './gold';

describe('whole-number formatting', () => {
  it('rounds money to whole gold pieces', () => {
    expect(formatGold(607.51)).toBe('608 gp');
    expect(formatGold(1000)).toBe('1,000 gp');
    expect(formatSigned(-392.49)).toBe('−392 gp');
  });
  it('rounds percentages to whole numbers', () => {
    expect(formatPct(-39.2)).toBe('−39%');
    expect(formatPct(5.9)).toBe('+6%');
    expect(formatPct(0)).toBe('0%');
  });
});
