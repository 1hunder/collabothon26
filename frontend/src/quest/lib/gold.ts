/** The quest's one currency label: gold pieces ("gp"). Every rendered amount in the quest goes through here. */
export const GOLD_SHORT = 'gp';
export const GOLD_LONG = 'gold pieces';

/** Whole grouped number (1,250), no currency. Money is never shown with decimals. */
export function formatGoldNumber(n: number): string {
  return Math.round(n).toLocaleString('en-US');
}

/** "1,250 gp". */
export function formatGold(n: number): string {
  return `${formatGoldNumber(n)} ${GOLD_SHORT}`;
}
