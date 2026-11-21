import { formatStoryDay, formatStoryNumber } from './storyNumber';

describe('storyNumber', () => {
  it('groups plain numbers up to 10,000 without suffixes', () => {
    expect(formatStoryNumber(1250)).toBe('1,250');
    expect(formatStoryNumber(10000)).toBe('10,000');
    expect(formatStoryNumber(1250)).not.toMatch(/[kmbKMB]/);
  });
  it('is always a whole number', () => {
    expect(formatStoryNumber(607.51)).toBe('608');
    expect(formatStoryNumber(31.4)).toBe('31');
  });
  it('throws above 10,000', () => {
    expect(() => formatStoryNumber(10001)).toThrow(RangeError);
    expect(() => formatStoryNumber(Number.NaN)).toThrow(RangeError);
  });
  it('formats Day N', () => {
    expect(formatStoryDay(84)).toBe('Day 84');
  });
});
