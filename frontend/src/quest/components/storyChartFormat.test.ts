import { afterEach, expect, it, vi } from 'vitest';
import { formatRealDate, formatRealTick } from './storyChartFormat';

afterEach(() => vi.unstubAllGlobals());

it('formats real dates in English whatever the browser language', () => {
  vi.stubGlobal('navigator', { ...navigator, language: 'uk-UA', languages: ['uk-UA'] });
  expect(formatRealTick('2001-10-15')).toBe('Oct 2001');
  expect(formatRealTick('2001-12-03')).toBe('Dec 2001');
  expect(formatRealDate('2001-10-15')).toBe('15 Oct 2001');
});
