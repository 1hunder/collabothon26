import { formatEur, formatPct, formatSigned } from './commit';

describe('whole-number formatting', () => {
  it('rounds money to whole euros', () => {
    expect(formatEur(607.51)).toBe('€608');
    expect(formatEur(1000)).toBe('€1,000');
    expect(formatSigned(-392.49)).toBe('−€392');
  });
  it('rounds percentages to whole numbers', () => {
    expect(formatPct(-39.2)).toBe('−39%');
    expect(formatPct(5.9)).toBe('+6%');
    expect(formatPct(0)).toBe('0%');
  });
});
