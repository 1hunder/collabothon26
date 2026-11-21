import type { Time } from 'lightweight-charts';

export const LOCALE = 'en-GB';
const monthYear = new Intl.DateTimeFormat(LOCALE, { month: 'short', year: 'numeric', timeZone: 'UTC' });
const fullDate = new Intl.DateTimeFormat(LOCALE, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });

function isoToDate(t: Time): Date | null {
  if (typeof t === 'string') return new Date(`${t}T00:00:00Z`);
  if (typeof t === 'number') return new Date(t * 1000);
  return new Date(Date.UTC(t.year, t.month - 1, t.day));
}

/** Date labels in English whatever the browser language is. */
export const formatRealTick = (t: Time): string => {
  const d = isoToDate(t);
  return d ? monthYear.format(d) : '';
};
export const formatRealDate = (t: Time): string => {
  const d = isoToDate(t);
  return d ? fullDate.format(d) : '';
};

