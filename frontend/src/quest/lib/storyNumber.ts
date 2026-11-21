export const STORY_NUMBER_MAX = 10_000;

const formatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });

/**
 * Plain grouped number (e.g. 1,250). Never uses k/m/bn suffixes.
 * Policy: values with |n| > 10,000 or non-finite values THROW a RangeError,
 * because the API must never send them; failing loudly beats leaking a real-scale value.
 */
export function formatStoryNumber(n: number): string {
  if (!Number.isFinite(n) || Math.abs(n) > STORY_NUMBER_MAX) {
    throw new RangeError(`Story number out of range: ${n}`);
  }
  return formatter.format(n);
}

export function formatStoryDay(n: number): string {
  return `Day ${formatStoryNumber(Math.round(n))}`;
}
